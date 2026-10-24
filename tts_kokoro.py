"""
tts_kokoro.py — Kokoro-FastAPI TTS engine (drop-in replacement for tts.py / Piper)

Requires a running Kokoro-FastAPI Docker container:
    docker run -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest   # CPU
    docker run --gpus all -p 8880:8880 ghcr.io/remsky/kokoro-fastapi:latest  # GPU

Speed range: 0.25x – 3.0x (1.0 = normal)
"""

import argparse
import io
import time
from pathlib import Path

import requests

# ──────────────────────────────────────────────
# Configuration — edit these or set via env vars
# ──────────────────────────────────────────────
KOKORO_BASE_URL = "http://localhost:8880/v1"   # Swap to cloud URL if using fal.ai / Venice AI
KOKORO_API_KEY  = "not-needed"                 # Leave as-is for local Docker; use real key for cloud
DEFAULT_VOICE   = "af_heart"                   # af_heart | af_bella | af_nicole | am_adam | am_michael
DEFAULT_FORMAT  = "mp3"                        # mp3 | wav | ogg  (Kokoro FastAPI supports all three)

# Available Kokoro voices for reference:
# American English (female): af_heart, af_bella, af_nicole, af_sarah, af_sky
# American English (male):   am_adam, am_michael
# British English (female):  bf_emma, bf_isabella
# British English (male):    bm_george, bm_lewis


def synthesize(
    text: str,
    voice: str = DEFAULT_VOICE,
    out_file: str = "digest.mp3",
    speed: float = 1.0,
    fmt: str = DEFAULT_FORMAT,
) -> str:
    """
    Send text to Kokoro-FastAPI and save the audio.

    Args:
        text:     Text to convert to speech.
        voice:    Kokoro voice ID (see list above).
        out_file: Output path (extension determines format if fmt is auto).
        speed:    Playback speed multiplier — 0.25 (slowest) to 3.0 (fastest).
        fmt:      Audio format: mp3 | wav | ogg

    Returns:
        Absolute path to the saved audio file.

    Raises:
        ValueError:   If speed is out of the 0.25–3.0 range.
        RuntimeError: If the Kokoro API returns a non-200 status.
    """
    if not (0.25 <= speed <= 3.0):
        raise ValueError(f"Speed must be between 0.25 and 3.0, got {speed}")

    out = Path(out_file)
    headers = {
        "Authorization": f"Bearer {KOKORO_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":           "kokoro",
        "input":           text,
        "voice":           voice,
        "speed":           round(speed, 2),
        "response_format": fmt,
    }

    url = f"{KOKORO_BASE_URL}/audio/speech"
    resp = requests.post(url, json=payload, headers=headers, timeout=60)

    if resp.status_code != 200:
        raise RuntimeError(
            f"Kokoro API error {resp.status_code}: {resp.text[:300]}"
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(resp.content)
    return str(out)


def synthesize_stream(
    text: str,
    voice: str = DEFAULT_VOICE,
    speed: float = 1.0,
    fmt: str = DEFAULT_FORMAT,
) -> io.BytesIO:
    """
    Like synthesize() but returns raw bytes in a BytesIO buffer — 
    useful for Streamlit's st.audio() or direct playback without saving.
    """
    if not (0.25 <= speed <= 3.0):
        raise ValueError(f"Speed must be between 0.25 and 3.0, got {speed}")

    headers = {
        "Authorization": f"Bearer {KOKORO_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":           "kokoro",
        "input":           text,
        "voice":           voice,
        "speed":           round(speed, 2),
        "response_format": fmt,
    }

    url = f"{KOKORO_BASE_URL}/audio/speech"
    resp = requests.post(url, json=payload, headers=headers, timeout=60)

    if resp.status_code != 200:
        raise RuntimeError(
            f"Kokoro API error {resp.status_code}: {resp.text[:300]}"
        )

    return io.BytesIO(resp.content)


def check_kokoro_health() -> bool:
    """Return True if the Kokoro-FastAPI server is reachable."""
    try:
        r = requests.get(f"{KOKORO_BASE_URL.replace('/v1', '')}/health", timeout=5)
        return r.status_code == 200
    except requests.exceptions.ConnectionError:
        return False


# ──────────────────────────────────────────────
# CLI helper (mirrors tts.py interface)
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Kokoro-FastAPI text-to-speech")
    parser.add_argument("text", nargs="?", help="Text to speak")
    parser.add_argument("--file",  help="Read text from a .txt file")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help=f"Kokoro voice ID (default: {DEFAULT_VOICE})")
    parser.add_argument("--speed", type=float, default=1.0, help="Speed multiplier: 0.25–3.0 (default: 1.0)")
    parser.add_argument("--out",   default="digest.mp3", help="Output file path")
    parser.add_argument("--fmt",   default=DEFAULT_FORMAT, choices=["mp3", "wav", "ogg"], help="Audio format")
    parser.add_argument("--check", action="store_true", help="Check if Kokoro server is running")
    args = parser.parse_args()

    if args.check:
        ok = check_kokoro_health()
        print("✅ Kokoro server is running!" if ok else "❌ Kokoro server is NOT reachable. Is Docker running?")
        return

    if not check_kokoro_health():
        print("⚠️  Warning: Kokoro server at", KOKORO_BASE_URL, "is not reachable.")
        print("   Start it with: docker run -p 8880:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest")
        return

    text = Path(args.file).read_text(encoding="utf-8") if args.file else args.text
    if not text:
        parser.error("Provide text directly or use --file <path>")

    start = time.time()
    path  = synthesize(text, voice=args.voice, out_file=args.out, speed=args.speed, fmt=args.fmt)
    size  = Path(path).stat().st_size / 1024
    print(f"✅ Saved: {path}  ({size:.0f} KB, {time.time() - start:.1f}s)  speed={args.speed}x")


if __name__ == "__main__":
    main()
