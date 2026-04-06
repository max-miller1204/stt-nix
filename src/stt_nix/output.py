import logging
import subprocess
import time

log = logging.getLogger(__name__)


def paste_text(text: str, paste_delay_ms: int = 100) -> None:
    """Paste text via clipboard: save clipboard, write text, Ctrl+V, restore."""

    # 1. Save current clipboard
    original = None
    try:
        result = subprocess.run(
            ["wl-paste", "--no-newline"],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0:
            original = result.stdout
    except Exception as e:
        log.debug("Could not read clipboard: %s", e)

    # 2. Write text to clipboard (Popen + DEVNULL to avoid blocking)
    log.debug("Writing text to clipboard")
    proc = subprocess.Popen(
        ["wl-copy", "--", text],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    proc.wait()

    # 3. Wait for clipboard to settle
    time.sleep(paste_delay_ms / 1000)

    # 4. Send Ctrl+V
    log.debug("Sending Ctrl+V")
    try:
        subprocess.run(["wtype", "-M", "ctrl", "-k", "v"], timeout=2)
    except Exception as e:
        log.error("wtype failed: %s", e)
        return

    # 5. Brief pause
    time.sleep(0.05)

    # 6. Restore original clipboard
    if original is not None:
        log.debug("Restoring clipboard")
        proc = subprocess.Popen(
            ["wl-copy", "--", original],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        proc.wait()
