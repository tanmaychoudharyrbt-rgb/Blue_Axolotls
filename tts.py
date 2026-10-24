import argparse
from pathlib import Path


def speak_online(text, out_file="output.mp3", lang="en"):
    """Google TTS: natural voice, needs internet, saves an MP3."""
    from gtts import gTTS
    gTTS(text=text, lang=lang).save(out_file)
    return out_file


def speak_offline(text, out_file=None, rate=170):
    """pyttsx3: works offline, speaks aloud or saves to a file."""
    import pyttsx3
    engine = pyttsx3.init()
    engine.setProperty("rate", rate)
    if out_file:
        engine.save_to_file(text, out_file)
    else:
        engine.say(text)
    engine.runAndWait()
    return out_file


def main():
    parser = argparse.ArgumentParser(description="Text to Speech")
    parser.add_argument("text", nargs="?", help="Text to convert")
    parser.add_argument("--file", help="Read text from a .txt file")
    parser.add_argument("--engine", choices=["online", "offline"], default="online")
    parser.add_argument("--lang", default="en", help="Language code, e.g. en, hi, mr")
    parser.add_argument("--out", default="output.mp3", help="Output audio file")
    args = parser.parse_args()

    text = Path(args.file).read_text(encoding="utf-8") if args.file else args.text
    if not text:
        parser.error("Provide some text or use --file")

    if args.engine == "online":
        print("Saved:", speak_online(text, args.out, args.lang))
    else:
        speak_offline(text)
        print("Done")


if __name__ == "__main__":
    main()