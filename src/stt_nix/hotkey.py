"""Evdev-based hotkey listener for hold-to-talk and toggle modes."""

import asyncio
import glob
import logging
import evdev
import evdev.ecodes

log = logging.getLogger(__name__)

_RESCAN_DELAY = 2  # seconds to wait before rescanning after a device change

# Map modifier names to all their possible keycodes
MODIFIER_KEYS = {
    "ctrl": {evdev.ecodes.KEY_LEFTCTRL, evdev.ecodes.KEY_RIGHTCTRL},
    "shift": {evdev.ecodes.KEY_LEFTSHIFT, evdev.ecodes.KEY_RIGHTSHIFT},
    "alt": {evdev.ecodes.KEY_LEFTALT, evdev.ecodes.KEY_RIGHTALT},
    "super": {evdev.ecodes.KEY_LEFTMETA, evdev.ecodes.KEY_RIGHTMETA},
}


def parse_hotkey(key_str: str) -> tuple[set[int], int]:
    """Parse a hotkey string like 'ctrl+space' into (modifier_codes, key_code)."""
    parts = [p.strip().lower() for p in key_str.split("+")]
    modifiers: set[int] = set()
    key_code = None

    for part in parts:
        if part in MODIFIER_KEYS:
            modifiers |= MODIFIER_KEYS[part]
        else:
            # Try as evdev key name in multiple forms
            upper = part.upper()
            if upper in evdev.ecodes.ecodes:
                # e.g. "KEY_RIGHTALT" passed directly
                key_code = evdev.ecodes.ecodes[upper]
            elif f"KEY_{upper}" in evdev.ecodes.ecodes:
                # e.g. "space" -> "KEY_SPACE"
                key_code = evdev.ecodes.ecodes[f"KEY_{upper}"]
            else:
                raise ValueError(f"Unknown key: {part}")

    if key_code is None:
        raise ValueError(f"No trigger key found in: {key_str}")

    return modifiers, key_code


class HotkeyListener:
    def __init__(self, key_name: str, mode: str, on_start, on_stop):
        self.modifiers, self.key_code = parse_hotkey(key_name)
        self.mode = mode
        self.on_start = on_start
        self.on_stop = on_stop
        self._devices: dict[str, evdev.InputDevice] = {}  # path -> device
        self._active = False
        self._pressed_keys: set[int] = set()
        self._rescan_pending = False
        self._inotify_task = None

    def _modifiers_held(self) -> bool:
        """Check if all required modifier groups are satisfied."""
        if not self.modifiers:
            return True
        return bool(self._pressed_keys & self.modifiers)

    def _scan_devices(self):
        """Find new input devices that have the target key and aren't already tracked."""
        new_devices = []
        paths = sorted(glob.glob("/dev/input/event*"))
        for path in paths:
            if path in self._devices:
                continue
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
            self._devices[path] = dev
            new_devices.append(dev)
        return new_devices

    async def run(self):
        new_devices = self._scan_devices()
        for dev in new_devices:
            asyncio.ensure_future(self._read_loop(dev))

        if not self._devices:
            log.error("No input devices found with the target key")

        # Watch for new devices appearing in /dev/input/
        self._inotify_task = asyncio.ensure_future(self._watch_dev_input())

    async def _watch_dev_input(self):
        """Poll for new event devices appearing in /dev/input/."""
        while True:
            await asyncio.sleep(5)
            new_devices = self._scan_devices()
            for dev in new_devices:
                log.info("New device detected: %s (%s)", dev.name, dev.path)
                asyncio.ensure_future(self._read_loop(dev))

    async def _schedule_rescan(self):
        """Debounced rescan after a device disconnects."""
        if self._rescan_pending:
            return
        self._rescan_pending = True
        await asyncio.sleep(_RESCAN_DELAY)
        self._rescan_pending = False
        new_devices = self._scan_devices()
        for dev in new_devices:
            asyncio.ensure_future(self._read_loop(dev))

    async def _read_loop(self, dev: evdev.InputDevice):
        try:
            async for event in dev.async_read_loop():
                if event.type != evdev.ecodes.EV_KEY:
                    continue
                if event.value == 2:  # repeat
                    continue

                # Track all key presses for modifier detection
                if event.value == 1:
                    self._pressed_keys.add(event.code)
                elif event.value == 0:
                    self._pressed_keys.discard(event.code)

                if self.mode == "hold":
                    if event.code == self.key_code and event.value == 1 and self._modifiers_held():
                        if not self._active:
                            self._active = True
                            await self.on_start()
                    elif self._active and event.value == 0:
                        # Stop on release of trigger key or any required modifier
                        if event.code == self.key_code or event.code in self.modifiers:
                            self._active = False
                            await self.on_stop()
                elif self.mode == "toggle":
                    if event.code == self.key_code and event.value == 1 and self._modifiers_held():
                        if self._active:
                            await self.on_stop()
                        else:
                            await self.on_start()
                        self._active = not self._active
        except OSError:
            log.info("Device disconnected: %s (%s)", dev.name, dev.path)
            self._devices.pop(dev.path, None)
            if self._active:
                self._active = False
                log.info("Cancelling active recording due to device disconnect")
                await self.on_stop()
            asyncio.ensure_future(self._schedule_rescan())

    def stop(self):
        if self._inotify_task:
            self._inotify_task.cancel()
        for dev in self._devices.values():
            try:
                dev.close()
            except OSError:
                pass
        self._devices.clear()
