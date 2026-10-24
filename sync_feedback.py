"""Download current cloud feedback choices without uploading local data."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
from typing import Optional
from urllib.parse import urlsplit

from dotenv import load_dotenv
import requests

from feedback_store import FeedbackRequest, _lock_feedback_directory, merge_feedback_records, _cloud_cursors


def _source_origin(api_url: str) -> str:
    parsed = urlsplit(api_url.strip())
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("FEEDBACK_API_URL must be an HTTP(S) origin without a path or credentials.")
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Use an HTTPS FEEDBACK_API_URL for cloud feedback.")
    port = parsed.port
    host = parsed.hostname.lower()
    if ":" in host:
        host = f"[{host}]"
    if port is not None and (parsed.scheme, port) not in (("https", 443), ("http", 80)):
        host = f"{host}:{port}"
    return f"{parsed.scheme}://{host}"


def _existing_ids(path: Path, source: str):
    ids = set()
    if path.exists():
        with path.open("r", encoding="utf-8-sig", errors="replace") as stream:
            for line in stream:
                try:
                    entry = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if not isinstance(entry, dict):
                    continue
                cloud_id = _cloud_cursors(entry).get(source)
                if type(cloud_id) is int and cloud_id > 0:
                    ids.add(cloud_id)
    return ids


def _validate_page(payload, after_id):
    if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
        raise ValueError("The cloud returned an invalid feedback export page.")
    if type(payload.get("has_more")) is not bool:
        raise ValueError("The cloud export is missing its pagination status.")

    entries = payload["entries"]
    cursor = after_id
    for entry in entries:
        if not isinstance(entry, dict) or type(entry.get("id")) is not int or entry["id"] <= cursor:
            raise ValueError("The cloud returned unordered feedback IDs.")
        record = entry.get("record")
        if not isinstance(record, dict) or not isinstance(record.get("timestamp"), str) or not record["timestamp"]:
            raise ValueError("The cloud returned an invalid feedback record.")
        FeedbackRequest.model_validate(record, strict=True)
        cursor = entry["id"]

    next_id = payload.get("next_after_id")
    if next_id is not None and (type(next_id) is not int or next_id != cursor):
        raise ValueError("The cloud returned an invalid feedback export cursor.")
    if payload["has_more"] and (not entries or next_id is None):
        raise ValueError("The cloud export cursor did not advance.")
    return entries, cursor, payload["has_more"]


def _append_page(directory: Path, source: str, entries) -> int:
    return merge_feedback_records(directory, [
        {**entry["record"], "_cloud_id": entry["id"], "_cloud_source": source}
        for entry in entries
    ])


def sync_feedback(
    api_url: Optional[str] = None,
    export_token: Optional[str] = None,
    feedback_dir=None,
    session=None,
    page_size: int = 200,
) -> int:
    """Reconcile current cloud choices and return received updates during this run."""
    source = _source_origin(api_url if api_url is not None else os.getenv("FEEDBACK_API_URL", ""))
    token = (export_token if export_token is not None else os.getenv("FEEDBACK_EXPORT_TOKEN", "")).strip()
    if not token:
        raise ValueError("Set FEEDBACK_EXPORT_TOKEN to download cloud feedback.")
    if type(page_size) is not int or not 1 <= page_size <= 200:
        raise ValueError("Feedback export page size must be between 1 and 200.")
    directory = Path(feedback_dir if feedback_dir is not None else os.getenv("FEEDBACK_DIR", r"C:\DoctorProjectData\feedback"))
    directory.mkdir(parents=True, exist_ok=True)
    with _lock_feedback_directory(directory):
        after_id = max(_existing_ids(directory / "feedback.jsonl", source), default=0)

    requester = session if session is not None else requests
    saved = 0
    while True:
        # Remote requests happen outside the file lock so local clicks keep saving.
        response = requester.get(
            source + "/feedback/export",
            params={"after_id": after_id, "limit": page_size},
            headers={"Authorization": f"Bearer {token}"},
            timeout=(10, 30),
            allow_redirects=False,
        )
        response.raise_for_status()
        if response.is_redirect:
            raise ValueError("The feedback export URL must not redirect.")
        entries, after_id, has_more = _validate_page(response.json(), after_id)
        saved += _append_page(directory, source, entries)
        if not has_more:
            return saved


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(__file__).with_name(".env.feedback.local"))
    parser.add_argument("--watch", action="store_true", help="Keep downloading new feedback until Ctrl+C.")
    parser.add_argument("--interval", type=float, default=10, help="Seconds between downloads in watch mode (default: 10).")
    args = parser.parse_args(argv)
    if args.interval < 1:
        parser.error("--interval must be at least one second")
    load_dotenv(args.env_file, override=False)

    try:
        while True:
            try:
                saved = sync_feedback()
            except requests.RequestException:
                print("Feedback download failed. Check the cloud URL, export token, and network connection.", file=sys.stderr)
                if not args.watch:
                    return 1
            except PermissionError:
                print("Feedback sync could not update the file. Close any Get-Content -Wait watcher or program locking feedback.jsonl, then retry.", file=sys.stderr)
                return 1
            except (OSError, ValueError):
                print("Feedback sync failed. Check FEEDBACK_API_URL, FEEDBACK_EXPORT_TOKEN, and the local feedback directory.", file=sys.stderr)
                return 1
            else:
                print(f"Saved {saved} new cloud feedback record(s).", flush=True)
                if not args.watch:
                    return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
