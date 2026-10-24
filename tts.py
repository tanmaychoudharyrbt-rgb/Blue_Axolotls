import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

VOICES_DIR = Path("voices")


def synthesize(text, voice="en_US-lessac-medium", out_file="digest.ogg", speed=1.0):
    """Local text-to-speech with Piper. Returns the output file path."""
    model = VOICES_DIR / f"{voice}.onnx"
    if not model.exists():
        raise FileNotFoundError(
            f"Voice not found: {model}. Download it with: "
            f"cd voices && python3 -m piper.download_voices {voice}"
        )

    out = Path(out_file)
    wav = out.with_suffix(".wav")

    subprocess.run(
        [sys.executable, "-m", "piper", "-m", str(model), "-f", str(wav),
         "--length-scale", str(round(1 / speed, 3)), "--", text],
        check=True,
    )

    if out.suffix == ".wav":
        return str(wav)

    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found. Install it with: brew install ffmpeg")

    subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav), "-c:a", "libopus", "-b:a", "24k", str(out)],
        check=True, capture_output=True,
    )
    wav.unlink()
    return str(out)


def main():
    parser = argparse.ArgumentParser(description="Local text-to-speech (Piper)")
    parser.add_argument("text", nargs="?", help="Text to speak")
    parser.add_argument("--file", help="Read text from a .txt file")
    parser.add_argument("--voice", default="en_US-lessac-medium")
    parser.add_argument("--speed", type=float, default=1.0, help="1.1 = 10%% faster")
    parser.add_argument("--out", default="digest.ogg", help="digest.ogg or digest.wav")
    args = parser.parse_args()

    text = Path(args.file).read_text(encoding="utf-8") if args.file else args.text
    if not text:
        parser.error("Provide some text or use --file")

    start = time.time()
    path = synthesize(text, args.voice, args.out, args.speed)
    size_kb = Path(path).stat().st_size / 1024
    print(f"Saved: {path} ({size_kb:.0f} KB, {time.time() - start:.1f}s)")


if __name__ == "__main__":
    main()