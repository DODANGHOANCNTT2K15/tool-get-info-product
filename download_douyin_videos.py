from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from transcribe_douyin_videos import run_transcribe_douyin_videos


INPUT_JSON = Path("douyin_videos.json")
DOWNLOAD_DIR = Path("douyin_downloads")
ICON_IMAGE = Path("iconDownloadCocCoc.png")
OUTPUT_JSON = Path("douyin_download_results.json")
COCCOC_PATHS = (
    Path.home() / "AppData/Local/CocCoc/Browser/Application/browser.exe",
    Path("C:/Program Files/CocCoc/Browser/Application/browser.exe"),
    Path("C:/Program Files (x86)/CocCoc/Browser/Application/browser.exe"),
)


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load_video_links(input_file: Path) -> list[dict]:
    data = json.loads(input_file.read_text(encoding="utf-8"))
    links = data.get("links", [])
    if not isinstance(links, list):
        raise ValueError("Invalid input JSON: 'links' must be a list.")

    valid_links = []
    for item in links:
        if isinstance(item, dict) and item.get("url"):
            valid_links.append(item)

    return valid_links


def clear_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def find_coccoc(browser_path: str | None) -> Path:
    if browser_path:
        path = Path(browser_path)
        if path.exists():
            return path
        raise FileNotFoundError(f"Coc Coc browser path does not exist: {path}")

    for path in COCCOC_PATHS:
        if path.exists():
            return path

    raise FileNotFoundError(
        "Could not find Coc Coc browser.exe. Pass it manually with --browser-path."
    )


def open_url(browser_path: Path, url: str) -> None:
    subprocess.Popen(
        [str(browser_path), url],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def find_download_icon(icon_image: Path, timeout: float, confidence: float):
    try:
        import pyautogui
    except ImportError as error:
        raise RuntimeError(
            "Missing Python package: pyautogui. Install it with: "
            "python -m pip install pyautogui opencv-python"
        ) from error

    deadline = time.monotonic() + timeout
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            position = pyautogui.locateCenterOnScreen(
                str(icon_image),
                confidence=confidence,
            )
            if position:
                return position
        except Exception as error:
            last_error = error

        time.sleep(0.5)

    if last_error:
        raise RuntimeError(f"Could not locate download icon: {last_error}") from last_error

    return None


def click_download_icon(icon_image: Path, timeout: float, confidence: float) -> tuple[int, int]:
    import pyautogui

    position = find_download_icon(
        icon_image=icon_image,
        timeout=timeout,
        confidence=confidence,
    )
    if not position:
        raise RuntimeError("Download icon not found on screen.")

    x, y = int(position.x), int(position.y)
    pyautogui.moveTo(x, y, duration=0.15)
    pyautogui.click(x, y)
    return x, y


def close_current_tab() -> None:
    import pyautogui

    pyautogui.hotkey("ctrl", "w")


def save_results(output_file: Path, results: list[dict]) -> None:
    payload = {
        "total": len(results),
        "results": results,
    }
    output_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run_download_douyin_videos(
    input_file: Path,
    output_file: Path,
    browser_path: str | None = None,
    download_dir: Path | None = None,
    icon_image: Path | None = None,
    start_index: int = 1,
    limit: int = 0,
    page_wait: float = 8.0,
    icon_timeout: float = 20.0,
    confidence: float = 0.8,
    after_click_wait: float = 1.5,
    clear_download_dir: bool = True,
) -> dict:
    input_file = Path(input_file)
    output_file = Path(output_file)
    download_dir = Path(download_dir) if download_dir is not None else DOWNLOAD_DIR
    icon_image = Path(icon_image) if icon_image is not None else ICON_IMAGE
    browser_exe = find_coccoc(browser_path)

    if not input_file.exists():
        raise FileNotFoundError(f"Input JSON not found: {input_file}")
    if not icon_image.exists():
        raise FileNotFoundError(f"Icon image not found: {icon_image}")

    if clear_download_dir:
        clear_directory(download_dir)
        if output_file.exists():
            output_file.unlink()

    links = load_video_links(input_file)
    if start_index > 1:
        links = links[start_index - 1 :]
    if limit > 0:
        links = links[:limit]

    results: list[dict] = []
    for position, item in enumerate(links, start=1):
        url = str(item["url"])
        video_id = str(item.get("id") or item.get("index") or position)
        result = {
            "index": item.get("index"),
            "id": video_id,
            "url": url,
            "status": "pending",
        }

        try:
            open_url(browser_exe, url)
            time.sleep(page_wait)

            x, y = click_download_icon(
                icon_image=icon_image,
                timeout=icon_timeout,
                confidence=confidence,
            )
            result["status"] = "clicked"
            result["icon_position"] = {"x": x, "y": y}
            time.sleep(after_click_wait)
        except Exception as error:
            result["status"] = "error"
            result["error"] = str(error)
        finally:
            try:
                close_current_tab()
            except Exception as error:
                result.setdefault("close_error", str(error))

        results.append(result)
        save_results(output_file, results)

    return {
        "total": len(results),
        "results": results,
        "output_file": str(output_file),
        "download_dir": str(download_dir),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open Douyin video links in Coc Coc and click the Coc Coc download icon."
    )
    parser.add_argument("--input", default=str(INPUT_JSON))
    parser.add_argument("--download-dir", default=str(DOWNLOAD_DIR))
    parser.add_argument("--icon", default=str(ICON_IMAGE))
    parser.add_argument("--output", default=str(OUTPUT_JSON))
    parser.add_argument("--browser-path", help="Path to Coc Coc browser.exe.")
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--page-wait", type=float, default=8.0)
    parser.add_argument("--icon-timeout", type=float, default=20.0)
    parser.add_argument("--confidence", type=float, default=0.8)
    parser.add_argument("--after-click-wait", type=float, default=1.5)
    parser.add_argument(
        "--no-clear-download-dir",
        action="store_false",
        dest="clear_download_dir",
        help="Do not clear existing downloaded files before run.",
    )
    parser.add_argument(
        "--no-transcribe",
        action="store_true",
        dest="no_transcribe",
        help="Do not start Douyin transcription after downloads complete.",
    )
    parser.set_defaults(clear_download_dir=True, no_transcribe=False)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_file = Path(args.input)
    download_dir = Path(args.download_dir)
    icon_image = Path(args.icon)
    output_file = Path(args.output)
    browser_path = find_coccoc(args.browser_path)

    if not input_file.exists():
        raise FileNotFoundError(f"Input JSON not found: {input_file}")
    if not icon_image.exists():
        raise FileNotFoundError(f"Icon image not found: {icon_image}")

    if args.clear_download_dir:
        clear_directory(download_dir)
        if output_file.exists():
            output_file.unlink()

    links = load_video_links(input_file)
    if args.start_index > 1:
        links = links[args.start_index - 1 :]
    if args.limit > 0:
        links = links[: args.limit]

    print("")
    print("Douyin Coc Coc Downloader")
    print(f"Videos        : {len(links)}")
    print(f"Browser       : {browser_path}")
    print(f"Icon          : {icon_image}")
    print(f"Download dir  : {download_dir}")
    print(f"Output        : {output_file}")
    print(f"Clear download: {args.clear_download_dir}")
    print("-" * 60)

    results: list[dict] = []
    for position, item in enumerate(links, start=1):
        url = str(item["url"])
        video_id = str(item.get("id") or item.get("index") or position)
        result = {
            "index": item.get("index"),
            "id": video_id,
            "url": url,
            "status": "pending",
        }

        print("")
        print(f"[{position}/{len(links)}] {video_id}")
        print(f"  url       {url}")

        try:
            open_url(browser_path, url)
            print(f"  wait      {args.page_wait:g}s for page load")
            time.sleep(args.page_wait)

            x, y = click_download_icon(
                icon_image=icon_image,
                timeout=args.icon_timeout,
                confidence=args.confidence,
            )
            result["status"] = "clicked"
            result["icon_position"] = {"x": x, "y": y}
            print(f"  click     download icon at ({x}, {y})")

            time.sleep(args.after_click_wait)
        except Exception as error:
            result["status"] = "error"
            result["error"] = str(error)
            print(f"  error     {error}")
        finally:
            try:
                close_current_tab()
                print("  close     Ctrl+W")
            except Exception as error:
                result.setdefault("close_error", str(error))
                print(f"  close     failed: {error}")

        results.append(result)
        save_results(output_file, results)

    print("")
    print("-" * 60)
    print(f"Saved results to: {output_file}")


if __name__ == "__main__":
    args = parse_args()
    result = run_download_douyin_videos(
        input_file=Path(args.input),
        output_file=Path(args.output),
        browser_path=args.browser_path,
        download_dir=Path(args.download_dir),
        icon_image=Path(args.icon),
        start_index=args.start_index,
        limit=args.limit,
        page_wait=args.page_wait,
        icon_timeout=args.icon_timeout,
        confidence=args.confidence,
        after_click_wait=args.after_click_wait,
        clear_download_dir=args.clear_download_dir,
    )
    print(f"Saved results to: {result['output_file']}")

    if not args.no_transcribe:
        print("")
        print("Starting Douyin transcription...")
        run_transcribe_douyin_videos(
            input_file=Path(args.input),
            download_results_file=Path(args.output),
            download_dir=Path(args.download_dir),
        )
