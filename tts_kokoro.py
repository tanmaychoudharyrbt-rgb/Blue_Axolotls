"""
tts_kokoro.py — Kokoro-FastAPI TTS engine with gTTS fallback.

Priority:
  1. Kokoro-FastAPI (Docker) — best quality, speed 0.25x–3.0x
  2. gTTS (Google TTS online) — fallback, works immediately, no Docker needed

Start Kokoro with Docker (optional, for better quality):
    docker run -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest
"""

import io
import time
import argparse
from pathlib import Path

import requests

# ── Kokoro config ─────────────────────────────────────────────────
KOKORO_BASE_URL = "http://localhost:8880/v1"
KOKORO_API_KEY  = "not-needed"
DEFAULT_VOICE   = "af_heart"
DEFAULT_FORMAT  = "mp3"


def check_kokoro_health() -> bool:
    """Return True if the Kokoro-FastAPI Docker server is reachable."""
    try:
        r = requests.get(
            KOKORO_BASE_URL.replace("/v1", "") + "/health",
            timeout=3,
        )
        return r.status_code == 200
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════
# Kokoro TTS  (Docker — best quality, speed control)
# ══════════════════════════════════════════════════════════════════

def _kokoro_synthesize(text: str, voice: str, speed: float, fmt: str) -> bytes:
    """Call Kokoro-FastAPI and return raw audio bytes."""
    if not (0.25 <= speed <= 3.0):
        raise ValueError(f"Speed must be 0.25–3.0, got {speed}")

    resp = requests.post(
        f"{KOKORO_BASE_URL}/audio/speech",
        json={
            "model":           "kokoro",
            "input":           text,
            "voice":           voice,
            "speed":           round(speed, 2),
            "response_format": fmt,
        },
        headers={
            "Authorization": f"Bearer {KOKORO_API_KEY}",
            "Content-Type":  "application/json",
        },
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Kokoro API {resp.status_code}: {resp.text[:200]}")
    return resp.content


# ══════════════════════════════════════════════════════════════════
# gTTS fallback  (Google TTS online — no Docker needed, works now)
# ══════════════════════════════════════════════════════════════════

def _gtts_synthesize(text: str, lang: str = "en") -> bytes:
    """
    Use gTTS (Google Text-to-Speech) as fallback.
    Works without Docker. Needs internet.
    Speed control is not supported — gTTS always speaks at normal speed.
    """
    try:
        from gtts import gTTS
    except ImportError:
        raise ImportError("Run:  pip install gTTS")

    buf = io.BytesIO()
    tts = gTTS(text=text, lang=lang, slow=False)
    tts.write_to_fp(buf)
    buf.seek(0)
    return buf.read()


# ══════════════════════════════════════════════════════════════════
# Public API — used by voice_digest.py and app.py
# ══════════════════════════════════════════════════════════════════

def synthesize(
    text: str,
    voice: str = DEFAULT_VOICE,
    out_file: str = "digest.mp3",
    speed: float = 1.0,
    fmt: str = DEFAULT_FORMAT,
) -> str:
    """
    Convert text to speech and save to file.
    Uses Kokoro if available, otherwise falls back to gTTS automatically.

    Returns the saved file path.
    """
    out = Path(out_file)
    out.parent.mkdir(parents=True, exist_ok=True)

    if check_kokoro_health():
        audio = _kokoro_synthesize(text, voice, speed, fmt)
        print(f"[TTS] Kokoro ✅  speed={speed}x  voice={voice}")
    else:
        print("[TTS] Kokoro offline → using gTTS fallback (normal speed)")
        audio = _gtts_synthesize(text)

    out.write_bytes(audio)
    return str(out)


def synthesize_stream(
    text: str,
    voice: str = DEFAULT_VOICE,
    speed: float = 1.0,
    fmt: str = DEFAULT_FORMAT,
    lang: str = "en",
) -> io.BytesIO:
    """
    Convert text to speech and return a BytesIO buffer.
    Used by Streamlit's st.audio() — no file saved.
    Uses Kokoro if available, otherwise falls back to gTTS automatically.
    """
    if check_kokoro_health():
        audio = _kokoro_synthesize(text, voice, speed, fmt)
        engine = f"Kokoro ({speed}×)"
    else:
        audio  = _gtts_synthesize(text, lang=lang)
        engine = "gTTS (fallback)"

    return io.BytesIO(audio), engine


# ══════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="Text-to-speech (Kokoro / gTTS fallback)")
    parser.add_argument("text",    nargs="?",  help="Text to speak")
    parser.add_argument("--file",              help="Read text from .txt file")
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--speed", type=float, default=1.0, help="0.25–3.0  (Kokoro only)")
    parser.add_argument("--out",   default="digest.mp3")
    parser.add_argument("--check", action="store_true", help="Check Kokoro server status")
    args = parser.parse_args()

    if args.check:
        ok = check_kokoro_health()
        print("✅ Kokoro online" if ok else "⚠️  Kokoro offline — gTTS fallback will be used")
        return

    text = Path(args.file).read_text(encoding="utf-8") if args.file else args.text
    if not text:
        parser.error("Provide text or --file")

    t    = time.time()
    path = synthesize(text, voice=args.voice, out_file=args.out, speed=args.speed)
    size = Path(path).stat().st_size / 1024
    print(f"Saved: {path}  ({size:.0f} KB, {time.time()-t:.1f}s)")


if __name__ == "__main__":
    main()
