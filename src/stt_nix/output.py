import logging
import subprocess
import time

log = logging.getLogger(__name__)


def paste_text(text: str, paste_delay_ms: int = 100, paste_key: str = "ctrl+v") -> None:
    """Copy text to clipboard via wl-copy, then paste via dotool."""

    # Copy text to clipboard
    log.info("Copying text to clipboard")
    proc = subprocess.Popen(
        ["wl-copy", "--", text],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    proc.wait()

    # Wait for clipboard to settle
    time.sleep(paste_delay_ms / 1000)

    # Send paste keystroke via dotool
    log.info("Sending '%s' via dotool", paste_key)
    try:
        result = subprocess.run(
            ["dotool"],
            input=f"key {paste_key}\n",
            text=True,
            capture_output=True,
            timeout=2,
        )
        if result.returncode != 0:
            log.error("dotool failed (rc=%d): %s", result.returncode, result.stderr)
        else:
            log.info("dotool succeeded")
    except Exception as e:
        log.error("dotool failed: %s", e)
