"""Server-side text-to-speech using the macOS `say` command.

Browser speechSynthesis proved unreliable (silently no-ops on some Chrome/Mac
setups even with voices loaded), so the demo speaks through the host's own TTS.
This is fine for a local demo (the user is at the machine) and far more reliable.

Safe by construction: `say` is invoked with an argument list (no shell), so the
text can never be interpreted as a command.

Single-voice guarantee: a module-level lock plus "cancel the currently playing
utterance before starting a new one" ensures that no matter how many browser
tabs or callers hit /api/speak at once, only ONE `say` process is ever audible.
"""

from __future__ import annotations

import asyncio
import shutil

_SAY = shutil.which("say")  # None on non-macOS hosts

# Serializes speech and tracks the currently-speaking process so we can stop it
# before starting a new one. This is what prevents two overlapping voices.
_lock = asyncio.Lock()
_current: asyncio.subprocess.Process | None = None


def available() -> bool:
    return _SAY is not None


async def _stop_current() -> None:
    global _current
    proc = _current
    if proc is not None and proc.returncode is None:
        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=1.0)
        except (ProcessLookupError, TimeoutError, OSError):
            try:
                proc.kill()
            except (ProcessLookupError, OSError):
                pass
    _current = None


async def speak(text: str) -> bool:
    """Speak `text` via macOS `say`, ensuring only one voice plays at a time.

    Returns True if spoken, False if unavailable.
    """
    global _current
    if not _SAY or not text.strip():
        return False

    # Interrupt anything currently speaking so voices never overlap.
    await _stop_current()

    async with _lock:
        try:
            proc = await asyncio.create_subprocess_exec(
                _SAY, "-r", "185", text,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            _current = proc
            await proc.wait()
            return proc.returncode == 0
        except (OSError, asyncio.CancelledError):
            return False
        finally:
            if _current is proc:
                _current = None
