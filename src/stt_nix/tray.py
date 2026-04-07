"""System tray icon using the StatusNotifierItem (SNI) D-Bus protocol."""

from __future__ import annotations

import logging
import os
import struct
import zlib

from dbus_fast import BusType, PropertyAccess
from dbus_fast.aio import MessageBus
from dbus_fast.service import ServiceInterface, dbus_property, signal

log = logging.getLogger(__name__)


def _decode_png(path: str) -> tuple[int, int, bytes]:
    """Minimal PNG decoder — returns (width, height, RGBA bytes)."""
    with open(path, "rb") as f:
        sig = f.read(8)
        assert sig == b"\x89PNG\r\n\x1a\n", "Not a PNG"

        idat_data = b""
        width = height = bit_depth = color_type = 0

        while True:
            raw = f.read(8)
            if len(raw) < 8:
                break
            length, ctype = struct.unpack(">I4s", raw)
            data = f.read(length)
            f.read(4)  # CRC

            if ctype == b"IHDR":
                width, height, bit_depth, color_type = struct.unpack(">IIbB", data[:10])
            elif ctype == b"IDAT":
                idat_data += data
            elif ctype == b"IEND":
                break

        raw_data = zlib.decompress(idat_data)

        # Only handle 8-bit RGBA (color_type=6)
        assert color_type == 6 and bit_depth == 8
        stride = width * 4 + 1  # +1 for filter byte
        pixels = bytearray()

        prev_row = bytearray(width * 4)
        for y in range(height):
            row_start = y * stride
            filt = raw_data[row_start]
            row = bytearray(raw_data[row_start + 1:row_start + stride])

            if filt == 0:  # None
                pass
            elif filt == 1:  # Sub
                for i in range(4, len(row)):
                    row[i] = (row[i] + row[i - 4]) & 0xFF
            elif filt == 2:  # Up
                for i in range(len(row)):
                    row[i] = (row[i] + prev_row[i]) & 0xFF
            elif filt == 3:  # Average
                for i in range(len(row)):
                    left = row[i - 4] if i >= 4 else 0
                    row[i] = (row[i] + (left + prev_row[i]) // 2) & 0xFF
            elif filt == 4:  # Paeth
                for i in range(len(row)):
                    a = row[i - 4] if i >= 4 else 0
                    b = prev_row[i]
                    c = prev_row[i - 4] if i >= 4 else 0
                    p = a + b - c
                    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    if pa <= pb and pa <= pc:
                        pr = a
                    elif pb <= pc:
                        pr = b
                    else:
                        pr = c
                    row[i] = (row[i] + pr) & 0xFF

            pixels.extend(row)
            prev_row = row

    return width, height, bytes(pixels)


def _rgba_to_argb(rgba: bytes, w: int, h: int, invert: bool = True) -> bytes:
    """Convert RGBA to ARGB32 big-endian (SNI pixmap format).
       If invert=True, flip dark icons to white for dark tray backgrounds."""
    buf = bytearray(w * h * 4)
    for i in range(w * h):
        si = i * 4
        r, g, b, a = rgba[si], rgba[si + 1], rgba[si + 2], rgba[si + 3]
        if invert:
            r, g, b = 255 - r, 255 - g, 255 - b
        buf[si:si + 4] = struct.pack(">BBBB", a, r, g, b)
    return bytes(buf)


def _load_icon(state: str) -> tuple[int, int, bytes]:
    """Load a state icon PNG and convert to ARGB."""
    for base in [os.path.join(os.path.dirname(__file__), "icons"),
                 os.path.join(os.path.dirname(__file__), "..", "..", "assets", "icons")]:
        path = os.path.join(base, f"{state}.png")
        if os.path.exists(path):
            break
    else:
        log.warning("Icon not found for state: %s", state)
        # Fallback: small black square
        size = 22
        px = struct.pack(">BBBB", 0xFF, 0, 0, 0)
        return size, size, px * (size * size)

    w, h, rgba = _decode_png(path)
    return w, h, _rgba_to_argb(rgba, w, h)


_ICON_CACHE: dict[str, list[tuple[int, int, bytes]]] = {}


def _pixmap(state: str) -> list[tuple[int, int, bytes]]:
    if state not in _ICON_CACHE:
        w, h, data = _load_icon(state)
        _ICON_CACHE[state] = [(w, h, data)]
    return _ICON_CACHE[state]


class StatusNotifierItemInterface(ServiceInterface):
    INTERFACE_NAME = "org.kde.StatusNotifierItem"

    def __init__(self) -> None:
        super().__init__(self.INTERFACE_NAME)
        self._state = "idle"
        self._icon_pixmap = _pixmap("idle")

    @dbus_property(access=PropertyAccess.READ)
    def Category(self) -> "s":
        return "ApplicationStatus"

    @dbus_property(access=PropertyAccess.READ)
    def Id(self) -> "s":
        return "stt-nix"

    @dbus_property(access=PropertyAccess.READ)
    def Title(self) -> "s":
        return "STT Nix"

    @dbus_property(access=PropertyAccess.READ)
    def Status(self) -> "s":
        return "Active"

    @dbus_property(access=PropertyAccess.READ)
    def IconPixmap(self) -> "a(iiay)":
        return self._icon_pixmap

    @dbus_property(access=PropertyAccess.READ)
    def ItemIsMenu(self) -> "b":
        return False

    @dbus_property(access=PropertyAccess.READ)
    def IconName(self) -> "s":
        return ""

    @dbus_property(access=PropertyAccess.READ)
    def IconThemePath(self) -> "s":
        return ""

    @dbus_property(access=PropertyAccess.READ)
    def OverlayIconName(self) -> "s":
        return ""

    @dbus_property(access=PropertyAccess.READ)
    def OverlayIconPixmap(self) -> "a(iiay)":
        return []

    @dbus_property(access=PropertyAccess.READ)
    def AttentionIconName(self) -> "s":
        return ""

    @dbus_property(access=PropertyAccess.READ)
    def AttentionIconPixmap(self) -> "a(iiay)":
        return []

    @dbus_property(access=PropertyAccess.READ)
    def AttentionMovieName(self) -> "s":
        return ""

    @dbus_property(access=PropertyAccess.READ)
    def ToolTip(self) -> "(sa(iiay)ss)":
        return ("", [], "STT Nix", "")

    @dbus_property(access=PropertyAccess.READ)
    def Menu(self) -> "o":
        return "/"

    @signal()
    def NewIcon(self) -> None:
        pass

    @signal()
    def NewTitle(self) -> None:
        pass

    @signal()
    def NewStatus(self, status: "s") -> "s":
        return status

    def update_icon(self, state: str) -> None:
        self._state = state
        self._icon_pixmap = _pixmap(state)
        self.emit_properties_changed({"IconPixmap": self._icon_pixmap})
        self.NewIcon()


class TrayIcon:
    def __init__(self) -> None:
        self._state = "idle"
        self._bus: MessageBus | None = None
        self._interface = StatusNotifierItemInterface()
        self._service_name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"

    async def start(self) -> None:
        log.info("Starting tray icon (service: %s)", self._service_name)
        self._bus = await MessageBus(bus_type=BusType.SESSION).connect()
        self._bus.export("/StatusNotifierItem", self._interface)
        await self._bus.request_name(self._service_name)

        try:
            introspection = await self._bus.introspect(
                "org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher",
            )
            proxy = self._bus.get_proxy_object(
                "org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher", introspection,
            )
            watcher = proxy.get_interface("org.kde.StatusNotifierWatcher")
            await watcher.call_register_status_notifier_item(self._service_name)
            log.info("Registered with StatusNotifierWatcher")
        except Exception:
            log.exception("Failed to register with StatusNotifierWatcher")

    def set_state(self, state: str) -> None:
        if state == self._state:
            return
        log.info("Tray state: %s -> %s", self._state, state)
        self._state = state
        self._interface.update_icon(state)

    async def stop(self) -> None:
        if self._bus is not None:
            self._bus.disconnect()
            self._bus = None
