from __future__ import annotations

import json
import os
import threading
import time
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote
from urllib.parse import urlparse
import unicodedata
from typing import Any

from douyin_search import run_douyin_search
from download_douyin_videos import run_download_douyin_videos
from facebook_search import run_facebook_search
from transcribe_douyin_videos import run_transcribe_douyin_videos
from transcribe_facebook_videos import run_transcribe_facebook_videos


HOST = "127.0.0.1"
PORT = int(os.environ.get("APP_PORT", "8000"))
WORKDIR = Path(__file__).resolve().parent

FACEBOOK_LINKS_JSON = WORKDIR / "facebook_videos.json"
FACEBOOK_TRANSCRIPTS_JSON = WORKDIR / "facebook_video_transcripts.json"
DOUYIN_LINKS_JSON = WORKDIR / "douyin_videos.json"
DOUYIN_SEARCH_JSON = WORKDIR / "douyin_search.json"
DOUYIN_DOWNLOAD_RESULTS_JSON = WORKDIR / "douyin_download_results.json"
DOUYIN_TRANSCRIPTS_JSON = WORKDIR / "douyin_video_transcripts.json"
INPUT_FILE = WORKDIR / "input"


state_lock = threading.Lock()
job_state: dict[str, Any] = {
    "running": False,
    "status": "idle",
    "keyword": "",
    "step": "",
    "message": "Ready",
    "started_at": None,
    "finished_at": None,
    "error": "",
    "logs": [],
}


def read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def set_job(**updates: Any) -> None:
    with state_lock:
        job_state.update(updates)


def add_log(message: str) -> None:
    with state_lock:
        logs = job_state.setdefault("logs", [])
        logs.append({"time": time.strftime("%H:%M:%S"), "message": message})
        job_state["message"] = message


def cleanup_previous_workflow_data() -> None:
    for path in (
        INPUT_FILE,
        FACEBOOK_LINKS_JSON,
        FACEBOOK_TRANSCRIPTS_JSON,
        DOUYIN_LINKS_JSON,
        DOUYIN_DOWNLOAD_RESULTS_JSON,
        DOUYIN_TRANSCRIPTS_JSON,
    ):
        if path.exists():
            path.unlink()


def require_links(path: Path, platform: str) -> None:
    data = read_json(path, {})
    links = data.get("links", [])
    if not links:
        raise RuntimeError(
            f"{platform} links not found in {path.name}. "
            "Run the search parser with an HTML file first, or update this JSON manually."
        )


def has_links(path: Path) -> bool:
    data = read_json(path, {})
    links = data.get("links", [])
    return bool(links)


def run_workflow(keyword: str) -> None:
    set_job(
        running=True,
        status="running",
        keyword=keyword,
        step="search",
        started_at=time.time(),
        finished_at=None,
        error="",
        logs=[],
    )

    try:
        cleanup_previous_workflow_data()
        INPUT_FILE.write_text(keyword, encoding="utf-8")

        add_log("Running Facebook search")
        run_facebook_search(keyword=keyword, input_file=INPUT_FILE, output_file=FACEBOOK_LINKS_JSON)

        add_log("Running Douyin search")
        run_douyin_search(keyword=keyword, input_file=INPUT_FILE, output_file=DOUYIN_LINKS_JSON)

        if has_links(FACEBOOK_LINKS_JSON):
            set_job(step="facebook_transcribe")
            add_log("Transcribing Facebook videos")
            run_transcribe_facebook_videos(
                input_file=FACEBOOK_LINKS_JSON,
                output_file=FACEBOOK_TRANSCRIPTS_JSON,
            )
        else:
            add_log("No Facebook links found; skipping Facebook transcription.")

        if has_links(DOUYIN_LINKS_JSON):
            set_job(step="douyin_download")
            add_log("Downloading Douyin videos")
            run_download_douyin_videos(
                input_file=DOUYIN_LINKS_JSON,
                output_file=DOUYIN_DOWNLOAD_RESULTS_JSON,
            )

            set_job(step="douyin_transcribe")
            add_log("Transcribing Douyin videos")
            run_transcribe_douyin_videos(
                input_file=DOUYIN_LINKS_JSON,
                download_results_file=DOUYIN_DOWNLOAD_RESULTS_JSON,
                output_file=DOUYIN_TRANSCRIPTS_JSON,
            )
        else:
            add_log("No Douyin links found; skipping Douyin download and transcription.")

        add_log("Completed")
        set_job(running=False, status="completed", step="completed", finished_at=time.time())
    except Exception as error:
        add_log(f"Error: {error}")
        set_job(
            running=False,
            status="error",
            error=str(error),
            traceback=traceback.format_exc(),
            finished_at=time.time(),
        )


def start_job(keyword: str) -> bool:
    with state_lock:
        if job_state["running"]:
            return False

    thread = threading.Thread(target=run_workflow, args=(keyword,), daemon=True)
    thread.start()
    return True


def parse_html_content(platform: str, html_content: str, output_file: Path) -> int:
    temp_file = WORKDIR / f"temp_{platform}_{int(time.time())}.html"
    try:
        temp_file.write_text(html_content, encoding="utf-8")
        if platform == "facebook":
            result = run_facebook_search(
                keyword=None,
                input_file=INPUT_FILE,
                output_file=output_file,
                html_file=temp_file,
                open_browser=False,
            )
            return int(result.get("total", 0))
        elif platform == "douyin":
            result = run_douyin_search(
                keyword=None,
                input_file=INPUT_FILE,
                output_file=output_file,
                html_file=temp_file,
                open_browser=False,
            )
            return int(result.get("total", 0))
        return 0
    finally:
        if temp_file.exists():
            temp_file.unlink()


def run_facebook_processing() -> None:
    set_job(
        running=True,
        status="running",
        step="facebook_transcribe",
        started_at=time.time(),
        finished_at=None,
        error="",
        logs=[],
    )
    add_log("Starting Facebook transcription workflow")
    try:
        add_log("Transcribing Facebook videos")
        run_transcribe_facebook_videos(
            input_file=FACEBOOK_LINKS_JSON,
            output_file=FACEBOOK_TRANSCRIPTS_JSON,
        )
        add_log("Completed")
        set_job(running=False, status="completed", step="completed", finished_at=time.time())
    except Exception as error:
        add_log(f"Error: {error}")
        set_job(
            running=False,
            status="error",
            error=str(error),
            traceback=traceback.format_exc(),
            finished_at=time.time(),
        )


def run_douyin_processing() -> None:
    set_job(
        running=True,
        status="running",
        step="douyin_download",
        started_at=time.time(),
        finished_at=None,
        error="",
        logs=[],
    )
    add_log("Starting Douyin download & transcription workflow")
    try:
        add_log("Downloading Douyin videos")
        run_download_douyin_videos(
            input_file=DOUYIN_LINKS_JSON,
            output_file=DOUYIN_DOWNLOAD_RESULTS_JSON,
        )

        set_job(step="douyin_transcribe")
        add_log("Transcribing Douyin videos")
        run_transcribe_douyin_videos(
            input_file=DOUYIN_LINKS_JSON,
            download_results_file=DOUYIN_DOWNLOAD_RESULTS_JSON,
            output_file=DOUYIN_TRANSCRIPTS_JSON,
        )
        add_log("Completed")
        set_job(running=False, status="completed", step="completed", finished_at=time.time())
    except Exception as error:
        add_log(f"Error: {error}")
        set_job(
            running=False,
            status="error",
            error=str(error),
            traceback=traceback.format_exc(),
            finished_at=time.time(),
        )


def start_processing_job(platform: str) -> bool:
    with state_lock:
        if job_state["running"]:
            return False

    target = run_facebook_processing if platform == "facebook" else run_douyin_processing
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return True


def response_payload() -> dict[str, Any]:
    facebook = read_json(FACEBOOK_TRANSCRIPTS_JSON, {"total": 0, "results": []})
    douyin = read_json(DOUYIN_TRANSCRIPTS_JSON, {"total": 0, "results": []})
    with state_lock:
        status = dict(job_state)
    return {"status": status, "facebook": facebook, "douyin": douyin}


class AppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(WORKDIR), **kwargs)

    def translate_path(self, path: str) -> str:
        # Based on SimpleHTTPRequestHandler.translate_path but with
        # percent-decoding and Unicode-normalized filename matching to
        # tolerate different encodings/normalizations from browsers.
        # Decode URL path component only.
        try:
            parsed = urlparse(path)
            decoded_path = unquote(parsed.path)
        except Exception:
            decoded_path = path

        # Build filesystem path by walking components and attempting
        # to match entries with Unicode normalization and casefolding.
        parts = [p for p in decoded_path.split('/') if p]
        full = Path(self.directory)
        for part in parts:
            try:
                candidate = full / part
                if candidate.exists():
                    full = candidate
                    continue

                # Attempt normalized, case-insensitive match among entries
                matched = None
                norm_part = unicodedata.normalize('NFC', part).casefold()
                for entry in full.iterdir():
                    try:
                        if unicodedata.normalize('NFC', entry.name).casefold() == norm_part:
                            matched = entry
                            break
                    except Exception:
                        continue

                if matched:
                    full = matched
                else:
                    # Fallback to the naive candidate path
                    full = candidate
            except Exception:
                full = full / part

        return str(full)

    def do_GET(self) -> None:
        # Decode percent-encoded path so filesystem lookup works with
        # non-ASCII filenames (e.g. Chinese characters) on Windows.
        try:
            self.path = unquote(self.path)
        except Exception:
            pass

        if self.path == "/api/status":
            self.send_json(dict(job_state))
            return
        if self.path == "/api/data":
            self.send_json(response_payload())
            return
        super().do_GET()

    def do_POST(self) -> None:
        if self.path == "/api/run":
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            keyword = str(payload.get("keyword", "")).strip()
            if not keyword:
                self.send_json({"ok": False, "error": "Keyword is required"}, status=400)
                return

            if not start_job(keyword):
                self.send_json({"ok": False, "error": "A job is already running"}, status=409)
                return

            self.send_json({"ok": True, "status": dict(job_state)})
            return

        if self.path == "/api/upload-html":
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            platform = str(payload.get("platform", "")).strip().lower()
            html_content = str(payload.get("html", "")).strip()

            if platform not in ("facebook", "douyin"):
                self.send_json({"ok": False, "error": "Invalid platform. Must be 'facebook' or 'douyin'"}, status=400)
                return
            if not html_content:
                self.send_json({"ok": False, "error": "HTML content is required"}, status=400)
                return

            with state_lock:
                if job_state["running"]:
                    self.send_json({"ok": False, "error": "A job is already running"}, status=409)
                    return

            try:
                output_file = FACEBOOK_LINKS_JSON if platform == "facebook" else DOUYIN_LINKS_JSON
                total_links = parse_html_content(platform, html_content, output_file)
                if total_links == 0:
                    self.send_json({"ok": False, "error": f"No video links found in the provided HTML for {platform}."}, status=400)
                    return

                if not start_processing_job(platform):
                    self.send_json({"ok": False, "error": "Failed to start background processing"}, status=500)
                    return

                self.send_json({"ok": True, "status": dict(job_state), "total_links": total_links})
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, status=500)
            return

        self.send_error(404)

    def send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), AppHandler)
    print(f"Serving at http://{HOST}:{PORT}/index.html")
    server.serve_forever()


if __name__ == "__main__":
    main()
