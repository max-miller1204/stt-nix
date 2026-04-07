"""System tray icon using the StatusNotifierItem (SNI) D-Bus protocol."""

from __future__ import annotations

import logging
import os
import struct

from dbus_fast import BusType, PropertyAccess, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.service import ServiceInterface, dbus_property, signal

log = logging.getLogger(__name__)

ICON_SIZE = 22

STATE_COLORS: dict[str, tuple[int, int, int]] = {
    "idle": (0x80, 0x80, 0x80),
    "recording": (0xFF, 0x44, 0x44),
    "transcribing": (0x44, 0x88, 0xFF),
}


def _make_icon_pixmap(r: int, g: int, b: int) -> bytes:
    pixel = struct.pack(">BBBB", 0xFF, r, g, b)
    return pixel * (ICON_SIZE * ICON_SIZE)


def _pixmap_variant(r: int, g: int, b: int) -> list[tuple[int, int, bytes]]:
    return [(ICON_SIZE, ICON_SIZE, _make_icon_pixmap(r, g, b))]


class StatusNotifierItemInterface(ServiceInterface):
    INTERFACE_NAME = "org.kde.StatusNotifierItem"

    def __init__(self) -> None:
        super().__init__(self.INTERFACE_NAME)
        self._state = "idle"
        r, g, b = STATE_COLORS["idle"]
        self._icon_pixmap = _pixmap_variant(r, g, b)

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
        if state not in STATE_COLORS:
            return
        self._state = state
        r, g, b = STATE_COLORS[state]
        self._icon_pixmap = _pixmap_variant(r, g, b)
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
