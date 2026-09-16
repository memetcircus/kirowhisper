"""Server-side text-to-speech using the macOS `say` command.

Browser speechSynthesis proved unreliable (silently no-ops on some Chrome/Mac
setups even with voices loaded), so the demo speaks through the host's own TTS.
This is fine for a local demo (the user is at the machine) and far more reliable.

Safe by construction: `say` is invoked with an argument list (no shell), so the
text can never be interpreted as a command.
"""

from __future__ import annotations

import asyncio
import shutil

_SAY = shutil.which("say")  # None on non-macOS hosts


def available() -> bool:
    return _SAY is not None


async def speak(text: str) -> bool:
    """Speak `text` via macOS `say`. Returns True if spoken, False if unavailable."""
    if not _SAY or not text.strip():
        return False
    try:
        proc = await asyncio.create_subprocess_exec(
            _SAY, "-r", "185", text,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        return proc.returncode == 0
    except (OSError, asyncio.CancelledError):
        return False
