from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict

MEDIA_EXTENSIONS = (".mp4", ".m4a", ".mp3", ".wav", ".mov", ".webm", ".mkv", ".aac")


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def find_media_for_video(video: dict, download_dir: Path) -> Path | None:
    # Prefer explicit media_path fields
    for key in ("media_path", "video_path", "file_path", "path"):
        v = video.get(key)
        if not v:
            continue
        p = Path(str(v))
        if p.exists():
            return p

    # Try by id-based filename
    vid = str(video.get("id") or video.get("index") or "")
    if vid:
        for ext in MEDIA_EXTENSIONS:
            candidate = download_dir / f"{vid}{ext}"
            if candidate.exists():
                return candidate

    # Try fuzzy match on title
    title = str(video.get("title", "")).lower()
    if title:
        for p in sorted(download_dir.iterdir(), key=lambda x: x.name.lower()):
            if not p.is_file():
                continue
            if p.suffix.lower() not in MEDIA_EXTENSIONS:
                continue
            if title in p.name.lower() or p.stem.lower() in title:
                return p

    # Last resort: first media file not already matched
    for p in sorted(download_dir.iterdir(), key=lambda x: x.stat().st_mtime):
        if p.is_file() and p.suffix.lower() in MEDIA_EXTENSIONS:
            return p

    return None


def rename_downloaded_files(
    input_json: Path = Path("douyin_videos.json"),
    download_dir: Path = Path("douyin_downloads"),
    download_results_json: Path = Path("douyin_download_results.json"),
    dry_run: bool = False,
) -> Dict[str, str]:
    input_data = load_json(input_json)
    videos = input_data.get("links") or input_data.get("results") or []
    download_dir.mkdir(parents=True, exist_ok=True)

    updated_paths: Dict[str, str] = {}
    results = load_json(download_results_json)
    results_map = {}
    if isinstance(results, dict):
        for item in results.get("results", []):
            if item.get("id"):
                results_map[str(item.get("id"))] = item

    for idx, video in enumerate(videos, start=1):
        vid = str(video.get("id") or video.get("index") or idx)
        media = find_media_for_video(video, download_dir)
        if not media:
            print(f"[skip] no media found for video id={vid}")
            continue

        new_name = f"{vid}{media.suffix.lower()}"
        target = media.parent / new_name
        try:
            if media.resolve() == target.resolve():
                print(f"[ok] already named: {target.name}")
                updated_paths[vid] = str(target)
                continue
        except Exception:
            pass

        if target.exists():
            print(f"[warn] target exists, skipping rename: {target}")
            updated_paths[vid] = str(target)
            continue

        print(f"rename: {media.name} -> {new_name}")
        if not dry_run:
            media.rename(target)
        updated_paths[vid] = str(target)

        # update results map if present
        if vid in results_map:
            item = results_map[vid]
            for key in ("media_path", "video_path", "file_path", "path"):
                if key in item:
                    item[key] = str(target)

    # If we updated results, write back
    if not dry_run and isinstance(results, dict) and results_map:
        # rebuild results.results list
        out_list = []
        for item in results.get("results", []):
            vid = str(item.get("id"))
            if vid in results_map:
                out_list.append(results_map[vid])
            else:
                out_list.append(item)
        results["results"] = out_list
        download_results_json.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return updated_paths


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Rename downloaded Douyin media files to their IDs.")
    parser.add_argument("--input", default="douyin_videos.json")
    parser.add_argument("--download-dir", default="douyin_downloads")
    parser.add_argument("--download-results", default="douyin_download_results.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    updated = rename_downloaded_files(
        input_json=Path(args.input),
        download_dir=Path(args.download_dir),
        download_results_json=Path(args.download_results),
        dry_run=args.dry_run,
    )

    print("Updated:")
    for k, v in updated.items():
        print(f"  {k} -> {v}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
