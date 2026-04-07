import asyncio
import json
import logging
import os
import signal
from concurrent.futures import ThreadPoolExecutor
from enum import Enum

from .config import load_config
from .recorder import Recorder
from .transcriber import create_transcriber
from .output import paste_text

log = logging.getLogger(__name__)


class State(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"


class Daemon:
    def __init__(self):
        self.config = load_config()
        self.state = State.IDLE
        self.recorder = Recorder(
            sample_rate=self.config["audio"]["sample_rate"],
            channels=self.config["audio"]["channels"],
        )
        self.transcriber = create_transcriber(self.config)
        self.tray = None
        self.executor = ThreadPoolExecutor(max_workers=1)
        self._server = None

    def socket_path(self) -> str:
        runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        return os.path.join(runtime, "stt-nix.sock")

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            data = await asyncio.wait_for(reader.readline(), timeout=5)
            if not data:
                return
            msg = json.loads(data.decode())
            cmd = msg.get("cmd", "")
            resp = await self.handle_command(cmd)
            writer.write(json.dumps(resp).encode())
            await writer.drain()
        except Exception as e:
            log.error("Client error: %s", e)
        finally:
            writer.close()

    async def handle_command(self, cmd: str) -> dict:
        if cmd == "toggle":
            if self.state == State.IDLE:
                return await self.handle_command("start")
            elif self.state == State.RECORDING:
                return await self.handle_command("stop")
            else:
                return {"error": "busy transcribing"}

        elif cmd == "start":
            if self.state != State.IDLE:
                return {"error": f"cannot start, state is {self.state.value}"}
            self.set_state(State.RECORDING)
            self.recorder.start()
            return {"ok": True, "state": "recording"}

        elif cmd == "stop":
            if self.state != State.RECORDING:
                return {"error": f"not recording, state is {self.state.value}"}
            audio = self.recorder.stop()
            self.set_state(State.TRANSCRIBING)
            # Run transcription in thread pool (it's CPU/GPU bound)
            loop = asyncio.get_event_loop()
            try:
                text = await loop.run_in_executor(self.executor, self.transcriber.transcribe, audio)
                log.info("Transcribed: %s", text)
                if text.strip():
                    paste_delay = self.config["output"]["paste_delay_ms"]
                    await loop.run_in_executor(self.executor, paste_text, text, paste_delay)
            except Exception as e:
                log.error("Transcription failed: %s", e)
                self.set_state(State.IDLE)
                return {"error": str(e)}
            self.set_state(State.IDLE)
            return {"ok": True, "state": "idle", "text": text}

        elif cmd == "status":
            return {"state": self.state.value}

        return {"error": f"unknown command: {cmd}"}

    def set_state(self, state: State):
        self.state = state
        log.info("State -> %s", state.value)
        if self.tray:
            self.tray.set_state(state.value)

    async def start_socket_server(self):
        path = self.socket_path()
        # Clean up stale socket
        if os.path.exists(path):
            os.unlink(path)
        self._server = await asyncio.start_unix_server(self.handle_client, path=path)
        log.info("Listening on %s", path)

    async def run(self):
        await self.start_socket_server()

        # Start tray icon
        try:
            from .tray import TrayIcon
            self.tray = TrayIcon()
            asyncio.create_task(self.tray.start())
            log.info("Tray icon started")
        except Exception as e:
            log.warning("Tray icon failed to start: %s", e)

        # Start hotkey listener if enabled
        if self.config["hotkey"]["enabled"]:
            try:
                from .hotkey import HotkeyListener
                listener = HotkeyListener(
                    key_name=self.config["hotkey"]["key"],
                    mode=self.config["hotkey"]["mode"],
                    on_start=lambda: self.handle_command("start"),
                    on_stop=lambda: self.handle_command("stop"),
                )
                asyncio.create_task(listener.run())
                log.info("Hotkey listener started")
            except Exception as e:
                log.warning("Hotkey listener failed: %s", e)

        # Wait until cancelled
        stop = asyncio.Event()
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        await stop.wait()

        # Cleanup
        if self._server:
            self._server.close()
        path = self.socket_path()
        if os.path.exists(path):
            os.unlink(path)
        if self.tray:
            await self.tray.stop()
        log.info("Daemon stopped")
