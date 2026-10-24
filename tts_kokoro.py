"""
tts_kokoro.py — Robust TTS engine for Kokoro-FastAPI with offline Mac & Web fallback.

Priority:
  1. Kokoro-FastAPI (Docker container at localhost:8880) — speed 0.25x to 3.0x
  2. macOS native offline speech (say + afconvert) — 100% offline, zero internet, speed 0.25x to 3.0x
  3. gTTS (online Google Translate TTS) — fallback if internet available
"""

import io
import os
import time
import argparse
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple, Optional

import requests

KOKORO_BASE_URL = os.getenv("KOKORO_BASE_URL", "http://localhost:8880/v1")
KOKORO_API_KEY  = os.getenv("KOKORO_API_KEY", "not-needed")
DEFAULT_VOICE   = "af_heart"
DEFAULT_FORMAT  = "mp3"


def check_kokoro_health() -> bool:
    """Return True if the Kokoro-FastAPI Docker server is reachable."""
    try:
        r = requests.get(
            KOKORO_BASE_URL.replace("/v1", "") + "/health",
            timeout=1.5,
        )
        return r.status_code == 200
    except Exception:
        return False


# ── Engine 1: Kokoro FastAPI (Docker) ──────────────────────────────
def _kokoro_synthesize(text: str, voice: str, speed: float, fmt: str) -> bytes:
    if not (0.25 <= speed <= 3.0):
        raise ValueError(f"Speed must be 0.25–3.0, got {speed}")

    resp = requests.post(
        f"{KOKORO_BASE_URL}/audio/speech",
        json={
            "model": "kokoro",
            "input": text,
            "voice": voice,
            "speed": round(speed, 2),
            "response_format": fmt,
        },
        headers={
            "Authorization": f"Bearer {KOKORO_API_KEY}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Kokoro API error {resp.status_code}: {resp.text[:150]}")
    return resp.content


# ── Engine 2: macOS Native Offline Speech (Zero Internet, Zero Docker) ─
def _mac_say_synthesize(text: str, speed: float = 1.0) -> bytes:
    """
    Generate audio using macOS built-in `say` and `afconvert`.
    Works completely offline on Mac with variable speed (0.25x to 3.0x).
    """
    rate = max(50, min(600, int(185 * speed)))
    with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as aiff:
        aiff_path = aiff.name
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wav:
        wav_path = wav.name

    try:
        subprocess.run(["say", "-r", str(rate), "-o", aiff_path, text], check=True, capture_output=True)
        subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16", aiff_path, wav_path], check=True, capture_output=True)
        with open(wav_path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(aiff_path):
            os.remove(aiff_path)
        if os.path.exists(wav_path):
            os.remove(wav_path)


# ── Engine 3: gTTS Fallback ─────────────────────────────────────────
def _gtts_synthesize(text: str, lang: str = "en") -> Optional[bytes]:
    try:
        from gtts import gTTS
        buf = io.BytesIO()
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════
# Unified Synthesis API
# ══════════════════════════════════════════════════════════════════

def synthesize(
    text: str,
    voice: str = DEFAULT_VOICE,
    out_file: str = "digest.wav",
    speed: float = 1.0,
    fmt: str = DEFAULT_FORMAT,
) -> str:
    """
    Synthesize text to audio and save to disk.
    Auto-detects best engine with zero crashes.
    """
    out = Path(out_file)
    out.parent.mkdir(parents=True, exist_ok=True)

    audio_bytes, _ = synthesize_bytes(text, voice=voice, speed=speed, fmt=fmt)
    out.write_bytes(audio_bytes)
    return str(out)


def synthesize_bytes(
    text: str,
    voice: str = DEFAULT_VOICE,
    speed: float = 1.0,
    fmt: str = DEFAULT_FORMAT,
    lang: str = "en",
) -> Tuple[bytes, str]:
    """
    Returns (audio_bytes, engine_label).
    Never crashes: falls back smoothly from Kokoro -> Mac Offline -> gTTS.
    """
    speed = max(0.25, min(3.0, float(speed)))

    # 1. Try Kokoro-FastAPI
    if check_kokoro_health():
        try:
            data = _kokoro_synthesize(text, voice, speed, fmt)
            return data, f"Kokoro FastAPI ({speed}× speed)"
        except Exception as e:
            print(f"[warn] Kokoro synthesis failed, using local offline: {e}")

    # 2. Try macOS offline native 'say'
    try:
        data = _mac_say_synthesize(text, speed=speed)
        return data, f"Mac Local Voice ({speed}× speed)"
    except Exception as e:
        print(f"[warn] Mac say failed, trying gTTS: {e}")

    # 3. Try gTTS
    gtts_data = _gtts_synthesize(text, lang=lang)
    if gtts_data:
        return gtts_data, "Google TTS (1.0×)"

    raise RuntimeError("All audio generation engines failed. Check system audio permissions.")


def synthesize_stream(
    text: str,
    voice: str = DEFAULT_VOICE,
    speed: float = 1.0,
    fmt: str = DEFAULT_FORMAT,
    lang: str = "en",
) -> Tuple[io.BytesIO, str]:
    """
    Returns (BytesIO_buffer, engine_label) for direct Streamlit playback.
    """
    audio_bytes, engine_label = synthesize_bytes(text, voice=voice, speed=speed, fmt=fmt, lang=lang)
    return io.BytesIO(audio_bytes), engine_label


# ── CLI ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kokoro & Offline TTS")
    parser.add_argument("text", nargs="?", default="CampusSignal voice system is active.")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.check:
        print("Kokoro Online:" if check_kokoro_health() else "Kokoro Offline (Mac offline fallback ready)")
    else:
        out_path = synthesize(args.text, speed=args.speed, out_file="digest.wav")
        print(f"✅ Generated: {out_path} ({os.path.getsize(out_path)} bytes)")
