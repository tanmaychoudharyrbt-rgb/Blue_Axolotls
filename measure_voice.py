import shutil
import subprocess
import time
from pathlib import Path

from voice_digest import DEMO_PAYLOADS, load_config, make_digest


def audio_duration(path):
    """Real audio length in seconds, read with ffprobe (installed with ffmpeg)."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def main():
    config = load_config()
    voices = config["voices"]
    rows = []

    for lang in ("en", "hi", "mr"):
        prefs = dict(config["user_preferences"])
        prefs["preferred_language"] = lang
        prefs["digest_mode"] = "hybrid"

        start = time.time()
        result = make_digest(DEMO_PAYLOADS[lang], prefs, voices)
        gen_time = time.time() - start

        if not result["audio_path"]:
            rows.append((lang, voices.get(lang, "-"), "FAILED", "-", "-"))
            continue

        out = Path(f"measure_{lang}.ogg")
        shutil.move(result["audio_path"], out)
        size_kb = out.stat().st_size / 1024
        rows.append((lang, voices[lang], f"{audio_duration(out):.1f}s",
                     f"{gen_time:.1f}s", f"{size_kb:.0f} KB"))

    lines = [
        "| Language | Voice | Audio length | Generation time | File size |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append("| " + " | ".join(r) + " |")
    table = "\n".join(lines)

    print("\n" + table)
    Path("measurements.md").write_text(
        "# Voice measurements\n\n"
        "Sample digest of 3 items, speed from config.yaml, measured on the "
        "development laptop.\n\n" + table + "\n",
        encoding="utf-8",
    )
    print("\nSaved to measurements.md")


if __name__ == "__main__":
    main()
