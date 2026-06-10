from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


INPUT_JSON = Path("douyin_videos.json")
DOWNLOAD_RESULTS_JSON = Path("douyin_download_results.json")
OUTPUT_JSON = Path("douyin_video_transcripts.json")
DOWNLOAD_DIR = Path("douyin_downloads")
MEDIA_EXTENSIONS = (".mp4", ".mp3", ".m4a", ".aac", ".wav", ".webm", ".mov", ".mkv")
DOWNLOAD_PATH_KEYS = ("media_path", "video_path", "audio_path", "file_path", "path")


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load_video_links(input_file: Path) -> list[dict]:
    data = json.loads(input_file.read_text(encoding="utf-8"))
    links = data.get("links", [])
    if not isinstance(links, list):
        raise ValueError("Invalid input JSON: 'links' must be a list.")
    return links


def load_download_results(input_file: Path) -> dict[str, dict]:
    if not input_file.exists():
        return {}

    data = json.loads(input_file.read_text(encoding="utf-8"))
    results = data.get("results", [])
    if not isinstance(results, list):
        raise ValueError("Invalid download results JSON: 'results' must be a list.")

    return {
        str(item.get("id")): item
        for item in results
        if item.get("id")
    }


def normalize_match_text(text: str) -> str:
    text = fix_mojibake(text).lower()
    return re.sub(r"\W+", "", text, flags=re.UNICODE)


def iter_media_files(download_dir: Path) -> list[Path]:
    if not download_dir.exists():
        return []

    return sorted(
        (
            path
            for path in download_dir.iterdir()
            if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS
        ),
        key=lambda path: path.name.lower(),
    )


def get_downloaded_media_path(item: dict) -> Path | None:
    for key in DOWNLOAD_PATH_KEYS:
        value = item.get(key)
        if not value:
            continue

        path = Path(str(value))
        if path.exists():
            return path

    return None


def find_media_path(
    video: dict,
    download_dir: Path,
    downloaded: dict[str, dict],
    used_paths: set[Path],
) -> Path | None:
    video_id = str(video.get("id") or video.get("index"))
    item = downloaded.get(video_id)
    if item:
        media_path = get_downloaded_media_path(item)
        if media_path and media_path not in used_paths:
            return media_path

    for extension in MEDIA_EXTENSIONS:
        media_path = download_dir / f"{video_id}{extension}"
        if media_path.exists() and media_path not in used_paths:
            return media_path

    title_key = normalize_match_text(str(video.get("title", "")))
    if title_key:
        for media_path in iter_media_files(download_dir):
            if media_path in used_paths:
                continue

            stem_key = normalize_match_text(media_path.stem)
            if title_key in stem_key or stem_key in title_key:
                return media_path

    # Sequential fallback matching (sort by st_mtime to match the order of downloads)
    all_media_files = sorted(
        (
            path
            for path in download_dir.iterdir()
            if path.is_file() and path.suffix.lower() in MEDIA_EXTENSIONS
        ),
        key=lambda path: path.stat().st_mtime,
    )
    for media_path in all_media_files:
        if media_path not in used_paths:
            return media_path

    return None


def transcribe_media(media_path: Path, model_size: str, language: str | None) -> dict:
    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise RuntimeError(
            "Missing Python package: faster-whisper. "
            "Install it with: python -m pip install faster-whisper"
        ) from error

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        str(media_path),
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
    markers = ("Ãƒ", "Ã„", "Ã¡Âº", "Ã¡Â»", "Ã‚", "Ã°Å¸")
    if not any(marker in text for marker in markers):
        return text

    try:
        fixed = text.encode("cp1252").decode("utf-8")
    except UnicodeError:
        return text

    return fixed if fixed else text


def translate_text(text: str, source_language: str, target_language: str) -> str:
    text = text.strip()
    if not text:
        return ""

    params = urlencode(
        {
            "client": "gtx",
            "sl": source_language,
            "tl": target_language,
            "dt": "t",
            "q": text,
        }
    )
    url = f"https://translate.googleapis.com/translate_a/single?{params}"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})

    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))

    try:
        parts = [item[0] for item in payload[0] if item and item[0]]
    except (IndexError, TypeError) as error:
        raise RuntimeError("Unexpected translation response.") from error

    return "".join(parts).strip()


def fix_mojibake(text: str) -> str:
    markers = ("Ã", "Â", "å", "æ", "ç", "è", "é")
    if not any(marker in text for marker in markers):
        return text

    for encoding, errors in (("cp1252", "strict"), ("latin1", "strict"), ("cp1252", "ignore"), ("latin1", "ignore")):
        try:
            fixed = text.encode(encoding, errors=errors).decode("utf-8", errors=errors)
        except UnicodeError:
            continue

        if fixed:
            return fixed

    return text


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
        description="Transcribe already downloaded Douyin audio/video files."
    )
    parser.add_argument("--input", default=str(INPUT_JSON))
    parser.add_argument("--download-results", default=str(DOWNLOAD_RESULTS_JSON))
    parser.add_argument("--download-dir", default=str(DOWNLOAD_DIR))
    parser.add_argument("--output", default=str(OUTPUT_JSON))
    parser.add_argument("--model", default="small")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--translate-to", default="vi")
    parser.add_argument("--no-translate", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--start-index", type=int, default=1)
    return parser.parse_args()


def run_transcribe_douyin_videos(
    input_file: Path = INPUT_JSON,
    download_results_file: Path = DOWNLOAD_RESULTS_JSON,
    download_dir: Path = DOWNLOAD_DIR,
    output_file: Path = OUTPUT_JSON,
    model: str = "small",
    language: str = "zh",
    translate_to: str = "vi",
    no_translate: bool = False,
    limit: int = 0,
    start_index: int = 1,
) -> dict:
    language_value = None if language.lower() == "auto" else language
    translate_to = translate_to.strip().lower()
    translation_field = "text_vi" if translate_to == "vi" else f"text_{translate_to}"

    links = load_video_links(input_file)
    if start_index > 1:
        links = links[start_index - 1 :]
    if limit > 0:
        links = links[:limit]

    downloaded = load_download_results(download_results_file)
    used_paths: set[Path] = set()

    print("")
    print("Douyin Transcriber")
    print(f"Videos   : {len(links)}")
    print(f"Model    : {model}")
    print(f"Language : {language_value or 'auto'}")
    print(f"Translate: {'off' if no_translate else translate_to}")
    print(f"Output   : {output_file}")
    print("-" * 52)

    results: list[dict] = []
    for position, item in enumerate(links, start=1):
        video_id = str(item.get("id") or item.get("index"))
        url = str(item["url"])
        print("")
        print(f"[{position}/{len(links)}] {video_id}")
        log_step("url", url)

        result = {
            "index": item.get("index"),
            "type": item.get("type"),
            "id": video_id,
            "url": url,
            "title": fix_mojibake(str(item.get("title", ""))),
            "author": fix_mojibake(str(item.get("author", ""))),
            "duration": item.get("duration"),
            "cover": item.get("cover"),
            "status": "pending",
            "text": "",
            translation_field: "",
        }

        try:
            media_path = find_media_path(item, download_dir, downloaded, used_paths)
            if not media_path:
                raise RuntimeError(f"No downloaded media found for video id: {video_id}")

            used_paths.add(media_path)
            result["media_path"] = str(media_path)
            result["media_type"] = media_path.suffix.lower().lstrip(".")
            log_step("media", str(media_path))
            log_step("transcribe", "start")

            transcript = transcribe_media(
                media_path=media_path,
                model_size=model,
                language=language_value,
            )
            result.update(transcript)
            if not no_translate and result["text"]:
                log_step("translate", f"{result.get('language') or language_value or 'auto'} -> {translate_to}")
                try:
                    result[translation_field] = translate_text(
                        text=result["text"],
                        source_language=str(result.get("language") or language_value or "auto"),
                        target_language=translate_to,
                    )
                except Exception as error:
                    result["translation_error"] = str(error)
            
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
    
    # Rename media files to video ID after successful transcription
    print("")
    print("Renaming downloaded media files...")
    rename_count = 0
    for result in results:
        if result.get("status") == "done" and result.get("media_path"):
            try:
                media_path = Path(result["media_path"])
                video_id = result.get("id")
                if media_path.exists() and video_id:
                    target = media_path.parent / f"{video_id}{media_path.suffix.lower()}"
                    if media_path.resolve() != target.resolve():
                        if not target.exists():
                            media_path.rename(target)
                            result["media_path"] = str(target)
                            rename_count += 1
                            print(f"  Renamed: {media_path.name} -> {target.name}")
            except Exception as e:
                print(f"  Error renaming {result.get('id')}: {e}")
    
    # Update transcripts with new paths
    save_results(output_file, results)
    print(f"Renamed {rename_count} media file(s)")
    
    return {"platform": "douyin", "total": len(results), "output": str(output_file)}


def main() -> None:
    args = parse_args()
    run_transcribe_douyin_videos(
        input_file=Path(args.input),
        download_results_file=Path(args.download_results),
        download_dir=Path(args.download_dir),
        output_file=Path(args.output),
        model=args.model,
        language=args.language,
        translate_to=args.translate_to,
        no_translate=args.no_translate,
        limit=args.limit,
        start_index=args.start_index,
    )


if __name__ == "__main__":
    main()
