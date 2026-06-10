from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


INPUT_JSON = Path("facebook_videos.json")
OUTPUT_JSON = Path("facebook_video_transcripts.json")
DOWNLOAD_DIR = Path("downloads")


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load_video_links(input_file: Path) -> list[dict]:
    data = json.loads(input_file.read_text(encoding="utf-8"))
    links = data.get("links", [])
    if not isinstance(links, list):
        raise ValueError("Invalid input JSON: 'links' must be a list.")
    return links


def require_command(command: str) -> None:
    if shutil.which(command):
        return
    raise RuntimeError(f"Missing command: {command}")


def download_audio(
    url: str,
    video_id: str,
    download_dir: Path,
    cookies_from_browser: str | None,
) -> Path:
    download_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(download_dir / f"{video_id}.%(ext)s")
    audio_path = download_dir / f"{video_id}.mp3"

    if audio_path.exists():
        log_step("audio", f"cached: {audio_path}")
        return audio_path

    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--extract-audio",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "0",
        "--no-playlist",
        "--output",
        output_template,
        url,
    ]

    if cookies_from_browser:
        command[3:3] = ["--cookies-from-browser", cookies_from_browser]

    subprocess.run(command, check=True)

    if audio_path.exists():
        return audio_path

    matches = sorted(download_dir.glob(f"{video_id}.*"))
    if matches:
        return matches[0]

    raise RuntimeError(f"Audio file was not created for video: {video_id}")


def transcribe_audio(audio_path: Path, model_size: str, language: str) -> dict:
    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise RuntimeError(
            "Missing Python package: faster-whisper. "
            "Install it with: python -m pip install faster-whisper"
        ) from error

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        str(audio_path),
        language=language,
        vad_filter=True,
    )

    full_text = []
    for segment in segments:
        text = fix_mojibake(segment.text.strip())
        if text:
            full_text.append(text)

    return {
        "language": info.language,
        "language_probability": round(info.language_probability, 4),
        "text": " ".join(full_text).strip(),
    }


def fix_mojibake(text: str) -> str:
    markers = ("Ã", "Ä", "áº", "á»", "Â", "ðŸ")
    if not any(marker in text for marker in markers):
        return text

    try:
        fixed = text.encode("cp1252").decode("utf-8")
    except UnicodeError:
        return text

    return fixed if fixed else text


def log_header(total: int, model: str, language: str, output_file: Path) -> None:
    print("")
    print("Facebook Video Transcriber")
    print(f"Videos   : {total}")
    print(f"Model    : {model}")
    print(f"Language : {language}")
    print(f"Output   : {output_file}")
    print("-" * 52)


def log_video(position: int, total: int, video_id: str, url: str) -> None:
    print("")
    print(f"[{position}/{total}] {video_id}")
    print(f"  url        {url}")


def log_step(label: str, message: str) -> None:
    print(f"  {label:<10} {message}")


def log_done(text: str) -> None:
    preview = text.replace("\n", " ").strip()
    if len(preview) > 120:
        preview = preview[:117] + "..."
    log_step("done", f"{len(text)} chars")
    if preview:
        log_step("preview", preview)


def save_results(output_file: Path, results: list[dict]) -> None:
    payload = {
        "total": len(results),
        "results": results,
    }
    output_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download audio from Facebook video links and transcribe speech to text."
    )
    parser.add_argument(
        "--input",
        default=str(INPUT_JSON),
        help="Input JSON with video links. Default: facebook_videos.json",
    )
    parser.add_argument(
        "--output",
        default=str(OUTPUT_JSON),
        help="Output transcript JSON. Default: facebook_video_transcripts.json",
    )
    parser.add_argument(
        "--download-dir",
        default=str(DOWNLOAD_DIR),
        help="Audio download folder. Default: downloads",
    )
    parser.add_argument(
        "--cookies-from-browser",
        help="Browser name for yt-dlp cookies, for example: chrome, edge, firefox.",
    )
    parser.add_argument(
        "--model",
        default="small",
        help="Whisper model size for faster-whisper. Default: small",
    )
    parser.add_argument(
        "--language",
        default="vi",
        help="Speech language code. Default: vi",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of videos to process. Default: 0 means all.",
    )
    return parser.parse_args()


def run_transcribe_facebook_videos(
    input_file: Path = INPUT_JSON,
    output_file: Path = OUTPUT_JSON,
    download_dir: Path = DOWNLOAD_DIR,
    cookies_from_browser: str | None = None,
    model: str = "small",
    language: str = "vi",
    limit: int = 0,
) -> dict:
    require_command("ffmpeg")
    links = load_video_links(input_file)
    if limit > 0:
        links = links[:limit]

    log_header(
        total=len(links),
        model=model,
        language=language,
        output_file=output_file,
    )

    results: list[dict] = []
    for position, item in enumerate(links, start=1):
        video_id = str(item.get("id") or item.get("index"))
        url = str(item["url"])
        log_video(position, len(links), video_id, url)

        result = {
            "index": item.get("index"),
            "type": item.get("type"),
            "id": video_id,
            "url": url,
            "status": "pending",
            "text": "",
        }

        try:
            log_step("download", "start")
            audio_path = download_audio(
                url=url,
                video_id=video_id,
                download_dir=download_dir,
                cookies_from_browser=cookies_from_browser,
            )
            log_step("audio", str(audio_path))
            log_step("transcribe", "start")
            transcript = transcribe_audio(
                audio_path=audio_path,
                model_size=model,
                language=language,
            )
            result.update(transcript)
            result["audio_path"] = str(audio_path)
            result["status"] = "done"
            log_done(result["text"])
        except Exception as error:
            result["status"] = "error"
            result["error"] = str(error)
            log_step("error", str(error))

        results.append(result)
        save_results(output_file, results)

    print("")
    print("-" * 52)
    print(f"Saved transcripts to: {output_file}")
    return {"platform": "facebook", "total": len(results), "output": str(output_file)}


def main() -> None:
    args = parse_args()
    run_transcribe_facebook_videos(
        input_file=Path(args.input),
        output_file=Path(args.output),
        download_dir=Path(args.download_dir),
        cookies_from_browser=args.cookies_from_browser,
        model=args.model,
        language=args.language,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
