"""Evdev-based hotkey listener for hold-to-talk and toggle modes."""

import asyncio
import glob
import logging

import evdev
import evdev.ecodes

log = logging.getLogger(__name__)


class HotkeyListener:
    def __init__(self, key_name: str, mode: str, on_start, on_stop):
        self.key_code = evdev.ecodes.ecodes[key_name]
        self.mode = mode
        self.on_start = on_start
        self.on_stop = on_stop
        self._devices: list[evdev.InputDevice] = []
        self._active = False

    async def run(self):
        paths = sorted(glob.glob("/dev/input/event*"))
        for path in paths:
            try:
                dev = evdev.InputDevice(path)
            except PermissionError:
                log.warning("Cannot open %s — add your user to the 'input' group", path)
                continue
            except OSError as exc:
                log.debug("Skipping %s: %s", path, exc)
                continue

            caps = dev.capabilities().get(evdev.ecodes.EV_KEY, [])
            if self.key_code not in caps:
                dev.close()
                continue

            log.info("Listening on %s (%s)", dev.name, dev.path)
            self._devices.append(dev)
            asyncio.ensure_future(self._read_loop(dev))

        if not self._devices:
            log.error("No input devices found with the target key")

    async def _read_loop(self, dev: evdev.InputDevice):
        try:
            async for event in dev.async_read_loop():
                if event.type != evdev.ecodes.EV_KEY:
                    continue
                if event.code != self.key_code:
                    continue
                if event.value == 2:  # repeat
                    continue

                if self.mode == "hold":
                    if event.value == 1:
                        await self.on_start()
                    elif event.value == 0:
                        await self.on_stop()
                elif self.mode == "toggle":
                    if event.value == 1:
                        if self._active:
                            await self.on_stop()
                        else:
                            await self.on_start()
                        self._active = not self._active
        except OSError:
            log.debug("Device %s disconnected", dev.path)

    def stop(self):
        for dev in self._devices:
            try:
                dev.close()
            except OSError:
                pass
        self._devices.clear()
