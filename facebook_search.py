from __future__ import annotations

import argparse
import html
import json
import re
import sys
import webbrowser
from pathlib import Path
from urllib.parse import quote


INPUT_FILE = Path("input")
OUTPUT_FILE = Path("facebook_videos.json")
FACEBOOK_BASE_URL = "https://www.facebook.com"
HTML_LINK_LIMIT = 15


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def read_keyword(input_file: Path) -> str:
    if not input_file.exists():
        raise FileNotFoundError(f"Keyword file not found: {input_file}")

    keyword = input_file.read_text(encoding="utf-8").strip()
    if not keyword:
        raise ValueError(f"Keyword file is empty: {input_file}")
    return keyword


def build_facebook_video_search_url(keyword: str) -> str:
    encoded_keyword = quote(keyword.strip())
    return f"https://www.facebook.com/search/videos/?q={encoded_keyword}"


def normalize_facebook_url(url: str) -> str:
    url = html.unescape(url).strip()
    if url.startswith("/"):
        return f"{FACEBOOK_BASE_URL}{url}"
    return url


def extract_video_links_from_html(source: str) -> list[str]:
    article_blocks = re.split(
        r'<div[^>]+role=["\']article["\'][^>]*>',
        source,
        flags=re.IGNORECASE,
    )[1:]

    if article_blocks:
        return extract_first_video_link_from_each_block(article_blocks)

    return extract_all_video_links(source)


def extract_first_video_link_from_each_block(blocks: list[str]) -> list[str]:
    links: list[str] = []
    seen: set[str] = set()

    for block in blocks:
        for match in re.finditer(r'href=["\']([^"\']+)["\']', block, flags=re.IGNORECASE):
            url = normalize_facebook_url(match.group(1))
            if not is_facebook_video_url(url):
                continue

            key = canonical_video_key(url)
            if key in seen:
                break

            seen.add(key)
            links.append(to_canonical_video_url(url))
            break

    return links


def extract_all_video_links(source: str) -> list[str]:
    links: list[str] = []
    seen: set[str] = set()

    for match in re.finditer(r'href=["\']([^"\']+)["\']', source, flags=re.IGNORECASE):
        url = normalize_facebook_url(match.group(1))
        if not is_facebook_video_url(url):
            continue

        key = canonical_video_key(url)
        if key in seen:
            continue

        seen.add(key)
        links.append(to_canonical_video_url(url))

    return links


def is_facebook_video_url(url: str) -> bool:
    return (
        url.startswith(FACEBOOK_BASE_URL)
        and ("/watch/?" in url or "/reel/" in url or "/videos/" in url)
    )


def canonical_video_key(url: str) -> str:
    reel_match = re.search(r"/reel/([^/?#]+)", url)
    if reel_match:
        return f"reel:{reel_match.group(1)}"

    video_match = re.search(r"[?&]v=([^&#]+)", url)
    if video_match:
        return f"watch:{video_match.group(1)}"

    video_path_match = re.search(r"/videos/([^/?#]+)", url)
    if video_path_match:
        return f"videos:{video_path_match.group(1)}"

    return url


def to_canonical_video_url(url: str) -> str:
    reel_match = re.search(r"/reel/([^/?#]+)", url)
    if reel_match:
        return f"{FACEBOOK_BASE_URL}/reel/{reel_match.group(1)}/"

    video_match = re.search(r"[?&]v=([^&#]+)", url)
    if video_match:
        return f"{FACEBOOK_BASE_URL}/watch/?v={video_match.group(1)}"

    video_path_match = re.search(r"/videos/([^/?#]+)", url)
    if video_path_match:
        return f"{FACEBOOK_BASE_URL}/videos/{video_path_match.group(1)}/"

    return url


def get_video_meta(url: str) -> dict[str, str]:
    reel_match = re.search(r"/reel/([^/?#]+)", url)
    if reel_match:
        return {"type": "reel", "id": reel_match.group(1)}

    video_match = re.search(r"[?&]v=([^&#]+)", url)
    if video_match:
        return {"type": "watch", "id": video_match.group(1)}

    video_path_match = re.search(r"/videos/([^/?#]+)", url)
    if video_path_match:
        return {"type": "videos", "id": video_path_match.group(1)}

    return {"type": "unknown", "id": ""}


def save_video_links(output_file: Path, links: list[str]) -> None:
    data = {
        "total": len(links),
        "links": [
            {
                "index": index,
                **get_video_meta(link),
                "url": link,
            }
            for index, link in enumerate(links, start=1)
        ],
    }

    output_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def save_search_info(output_file: Path, keyword: str, url: str) -> None:
    data = {
        "keyword": keyword,
        "search_url": url,
        "status": "opened_with_default_browser",
        "total": 0,
        "links": [],
        "note": (
            "No HTML file was provided. Run with --html to extract video links "
            "from HTML copied from DevTools."
        ),
    }
    output_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run_facebook_search(
    keyword: str | None = None,
    input_file: Path = INPUT_FILE,
    output_file: Path = OUTPUT_FILE,
    html_file: Path | None = None,
    open_browser: bool = True,
) -> dict:
    if keyword is not None:
        keyword_value = keyword.strip()
        if not keyword_value:
            raise ValueError("Keyword is required.")
    else:
        keyword_value = read_keyword(input_file)

    input_file.write_text(keyword_value, encoding="utf-8")
    url = build_facebook_video_search_url(keyword_value)

    if html_file:
        source = html_file.read_text(encoding="utf-8", errors="replace")
        links = extract_video_links_from_html(source)
        links = links[:HTML_LINK_LIMIT]
        save_video_links(output_file, links)
        return {
            "platform": "facebook",
            "keyword": keyword_value,
            "search_url": url,
            "links_file": str(output_file),
            "total": len(links),
            "opened": False,
        }

    save_search_info(output_file=output_file, keyword=keyword_value, url=url)

    if open_browser:
        webbrowser.open(url)

    return {
        "platform": "facebook",
        "keyword": keyword_value,
        "search_url": url,
        "links_file": str(output_file),
        "total": 0,
        "opened": open_browser,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open Facebook video search with the system default browser."
    )
    parser.add_argument(
        "--input",
        default=str(INPUT_FILE),
        help="Keyword file. Default: input",
    )
    parser.add_argument(
        "--output",
        default=str(OUTPUT_FILE),
        help="JSON output file. Default: facebook_videos.json",
    )
    parser.add_argument(
        "--keyword",
        help="Keyword to search on Facebook.",
    )
    parser.add_argument(
        "--html",
        help="HTML file copied from DevTools. If set, extract Facebook video links from it.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_file = Path(args.input)
    output_file = Path(args.output)

    if args.html:
        result = run_facebook_search(
            input_file=input_file,
            output_file=output_file,
            html_file=Path(args.html),
            open_browser=False,
        )
        print(f"HTML file: {args.html}")
        print(f"Saved {result['total']} video links to: {output_file}")
        return

    result = run_facebook_search(
        keyword=args.keyword,
        input_file=input_file,
        output_file=output_file,
    )
    print(f"Keyword file: {input_file}")
    print(f"Keyword: {result['keyword']}")
    print(f"Facebook videos URL: {result['search_url']}")
    print("Opening with default browser...")
    print("Browser opened. JSON output is only written when running with --html.")


if __name__ == "__main__":
    main()
