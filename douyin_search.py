from __future__ import annotations

import argparse
import html
from html.parser import HTMLParser
import json
import re
import sys
import webbrowser
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


INPUT_FILE = Path("input")
OUTPUT_FILE = Path("douyin_videos.json")
DEFAULT_KEYWORD = "dép"
DOUYIN_SEARCH_BASE_URL = "https://www.douyin.com/jingxuan/search"
DOUYIN_VIDEO_BASE_URL = "https://www.douyin.com/video"
DEFAULT_AID = "12af20c5-b2f8-46b6-961a-3f6ef82d2291"
DEFAULT_SEARCH_TYPE = "general"
HTML_LINK_LIMIT = 15


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def read_keyword(input_file: Path) -> str:
    if not input_file.exists():
        input_file.write_text(DEFAULT_KEYWORD, encoding="utf-8")
        return DEFAULT_KEYWORD

    keyword = input_file.read_text(encoding="utf-8", errors="replace").strip()
    keyword = fix_mojibake(keyword)
    return keyword or DEFAULT_KEYWORD


def fix_mojibake(text: str) -> str:
    markers = ("Ã", "Ä", "Æ", "áº", "á»")
    if not any(marker in text for marker in markers):
        return text

    try:
        fixed = text.encode("cp1252", errors="ignore").decode("utf-8")
    except UnicodeError:
        return text

    return fixed if fixed else text


def translate_keyword(keyword: str) -> tuple[str, str]:
    translated = translate_with_google(keyword)
    if translated:
        return translated, "google_translate"

    raise RuntimeError("Could not translate keyword from Vietnamese to Chinese.")


def translate_with_google(keyword: str) -> str:
    params = urlencode(
        {
            "client": "gtx",
            "sl": "vi",
            "tl": "zh-CN",
            "dt": "t",
            "q": keyword,
        }
    )
    url = f"https://translate.googleapis.com/translate_a/single?{params}"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return ""

    try:
        parts = [item[0] for item in payload[0] if item and item[0]]
    except (IndexError, TypeError):
        return ""

    return "".join(parts).strip()


def build_douyin_search_url(
    chinese_keyword: str,
    aid: str,
    search_type: str,
) -> str:
    encoded_keyword = quote(chinese_keyword.strip(), safe="")
    query = urlencode({"aid": aid, "type": search_type})
    return f"{DOUYIN_SEARCH_BASE_URL}/{encoded_keyword}?{query}"


def build_douyin_video_url(video_id: str) -> str:
    return f"{DOUYIN_VIDEO_BASE_URL}/{video_id}"


class DouyinCardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[dict[str, str]] = []
        self.current: dict[str, str] | None = None
        self.text_target: str | None = None
        self.card_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {name: value or "" for name, value in attrs}
        element_id = attr.get("id", "")
        class_names = attr.get("class", "").split()

        match = re.fullmatch(r"waterfall_item_(\d+)", element_id)
        if match:
            self.current = {
                "id": match.group(1),
                "type": "video",
                "url": build_douyin_video_url(match.group(1)),
            }
            self.cards.append(self.current)
            self.card_depth = 1
            return

        if self.current is None:
            return

        self.card_depth += 1

        if tag == "img" and self.current is not None:
            src = attr.get("src", "").strip()
            if src and "cover" not in self.current:
                self.current["cover"] = html.unescape(src)
            alt = attr.get("alt", "").strip()
            if alt and "title" not in self.current:
                self.current["title"] = fix_mojibake(html.unescape(alt))

        if "RBpYLmIg" in class_names:
            self.text_target = "title"
        elif "lGzJpEad" in class_names:
            self.text_target = "author"
        elif "cxEIO6RG" in class_names:
            self.text_target = "duration"

    def handle_endtag(self, tag: str) -> None:
        if self.text_target:
            self.text_target = None

        if self.current is None:
            return

        self.card_depth -= 1
        if self.card_depth <= 0:
            self.current = None
            self.card_depth = 0

    def handle_data(self, data: str) -> None:
        if self.current is None or self.text_target is None:
            return

        text = fix_mojibake(html.unescape(data)).strip()
        if not text:
            return

        existing = self.current.get(self.text_target, "")
        self.current[self.text_target] = f"{existing}{text}" if existing else text


def extract_douyin_video_links_from_html(source: str) -> list[dict[str, str]]:
    parser = DouyinCardParser()
    parser.feed(source)

    videos: list[dict[str, str]] = []
    seen: set[str] = set()
    for card in parser.cards:
        video_id = card["id"]
        if video_id in seen:
            continue

        seen.add(video_id)
        videos.append(card)

    if videos:
        return videos

    return [
        {
            "id": video_id,
            "type": "video",
            "url": build_douyin_video_url(video_id),
        }
        for video_id in dict.fromkeys(
            re.findall(r'id=["\']waterfall_item_(\d+)["\']', source)
        )
    ]


def save_video_links(output_file: Path, videos: list[dict[str, str]]) -> None:
    data = {
        "total": len(videos),
        "links": [
            {
                "index": index,
                **video,
            }
            for index, video in enumerate(videos, start=1)
        ],
    }
    output_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def save_search_info(
    output_file: Path,
    keyword: str,
    chinese_keyword: str,
    translation_source: str,
    url: str,
    opened: bool,
) -> None:
    data = {
        "platform": "douyin",
        "keyword": keyword,
        "chinese_keyword": chinese_keyword,
        "translation_source": translation_source,
        "search_url": url,
        "status": "opened_with_default_browser" if opened else "created",
        "total": 0,
        "links": [],
        "note": (
            "No HTML file was provided. Run with --html to extract video links "
            "from HTML copied from Douyin search results."
        ),
    }
    output_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run_douyin_search(
    keyword: str | None = None,
    zh_keyword: str | None = None,
    input_file: Path = INPUT_FILE,
    output_file: Path = OUTPUT_FILE,
    html_file: Path | None = None,
    aid: str = DEFAULT_AID,
    search_type: str = DEFAULT_SEARCH_TYPE,
    open_browser: bool = True,
) -> dict:
    if html_file:
        source = html_file.read_text(encoding="utf-8", errors="replace")
        videos = extract_douyin_video_links_from_html(source)
        videos = videos[:HTML_LINK_LIMIT]
        save_video_links(output_file, videos)
        return {
            "platform": "douyin",
            "links_file": str(output_file),
            "total": len(videos),
            "opened": False,
        }

    keyword_value = fix_mojibake(keyword.strip()) if keyword else read_keyword(input_file)
    if keyword_value:
        input_file.write_text(keyword_value, encoding="utf-8")

    if zh_keyword:
        chinese_keyword = zh_keyword.strip()
        translation_source = "manual"
    else:
        chinese_keyword, translation_source = translate_keyword(keyword_value)

    url = build_douyin_search_url(
        chinese_keyword=chinese_keyword,
        aid=aid,
        search_type=search_type,
    )

    save_search_info(
        output_file=output_file,
        keyword=keyword_value,
        chinese_keyword=chinese_keyword,
        translation_source=translation_source,
        url=url,
        opened=open_browser,
    )

    if open_browser:
        webbrowser.open(url)

    return {
        "platform": "douyin",
        "keyword": keyword_value,
        "chinese_keyword": chinese_keyword,
        "translation_source": translation_source,
        "search_url": url,
        "search_file": str(output_file),
        "opened": open_browser,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Translate a Vietnamese product keyword to Chinese and open Douyin search."
    )
    parser.add_argument(
        "--input",
        default=str(INPUT_FILE),
        help="Keyword file. Default: input",
    )
    parser.add_argument(
        "--keyword",
        help="Vietnamese keyword. If set, this overrides --input.",
    )
    parser.add_argument(
        "--zh-keyword",
        help="Chinese keyword. If set, translation is skipped.",
    )
    parser.add_argument(
        "--output",
        default=str(OUTPUT_FILE),
        help="JSON output file. Default: douyin_videos.json",
    )
    parser.add_argument(
        "--html",
        help="HTML file copied from Douyin search result container. If set, extract video links from it.",
    )
    parser.add_argument(
        "--aid",
        default=DEFAULT_AID,
        help="Douyin aid query value.",
    )
    parser.add_argument(
        "--type",
        default=DEFAULT_SEARCH_TYPE,
        help="Douyin search type query value. Default: general",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Create output JSON without opening the browser.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_file = Path(args.input)
    output_file = Path(args.output)

    if args.html:
        result = run_douyin_search(
            input_file=input_file,
            output_file=output_file,
            html_file=Path(args.html),
            open_browser=False,
        )
        print(f"HTML file: {args.html}")
        print(f"Saved {result['total']} Douyin video links to: {output_file}")
        return

    result = run_douyin_search(
        keyword=args.keyword,
        zh_keyword=args.zh_keyword,
        input_file=input_file,
        output_file=output_file,
        aid=args.aid,
        search_type=args.type,
        open_browser=not args.no_open,
    )

    print(f"Keyword file: {input_file}")
    print(f"Vietnamese keyword: {result['keyword']}")
    print(f"Chinese keyword: {result['chinese_keyword']}")
    print(f"Translation source: {result['translation_source']}")
    print(f"Douyin URL: {result['search_url']}")
    print(f"Saved search info to: {output_file}")

    if result["opened"]:
        print("Opening with default browser...")


if __name__ == "__main__":
    main()
