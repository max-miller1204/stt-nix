"""Evdev-based hotkey listener for hold-to-talk and toggle modes."""

import asyncio
import glob
import logging

import evdev
import evdev.ecodes

log = logging.getLogger(__name__)

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
        self._devices: list[evdev.InputDevice] = []
        self._active = False
        self._pressed_keys: set[int] = set()

    def _modifiers_held(self) -> bool:
        """Check if all required modifier groups are satisfied."""
        if not self.modifiers:
            return True
        return bool(self._pressed_keys & self.modifiers)

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
            log.debug("Device %s disconnected", dev.path)

    def stop(self):
        for dev in self._devices:
            try:
                dev.close()
            except OSError:
                pass
        self._devices.clear()
