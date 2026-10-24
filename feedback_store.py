"""Latest feedback choices, with a separate history of received changes."""
from contextlib import contextmanager
import datetime
import json
import os
from pathlib import Path
import threading
import tempfile
import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

if os.name == "nt":
    import msvcrt
else:
    import fcntl


class FeedbackRequest(BaseModel):
    code: str
    description: Optional[str] = ""
    evidence_phrase: Optional[str] = ""
    word_indices: List[int] = Field(default_factory=list)
    is_correct: bool
    transcript_base: Optional[str] = None
    concepts: Optional[Dict[str, Any]] = None


_feedback_lock = threading.Lock()


@contextmanager
def _lock_feedback_directory(directory: Path):
    # The local API and receiver may run in different processes. A sidecar lock
    # coordinates both without locking the JSONL file out of read-only viewers.
    with _feedback_lock, (directory / ".feedback.lock").open("a+b") as lock_file:
        if os.name == "nt":
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        else:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _feedback_key(entry):
    """A code choice belongs to one recording, never to all patients globally."""
    if not isinstance(entry, dict):
        return None
    recording = entry.get("transcript_base")
    code = entry.get("code")
    if not isinstance(recording, str) or not recording.strip() or not isinstance(code, str) or not code.strip():
        # Old callers did not identify recordings. Preserve those records rather
        # than combining unrelated appointments that happened to use one code.
        return None
    return recording.strip(), code.strip().upper()


def _cloud_marker(entry):
    if not isinstance(entry, dict):
        return None
    source = entry.get("_cloud_source")
    cloud_id = entry.get("_cloud_id")
    if isinstance(source, str) and type(cloud_id) is int and cloud_id > 0:
        return source, cloud_id
    return None


def _cloud_cursors(entry):
    if not isinstance(entry, dict):
        return {}
    raw = entry.get("_cloud_cursors")
    cursors = {source: value for source, value in raw.items() if isinstance(source, str) and type(value) is int and value > 0} if isinstance(raw, dict) else {}
    marker = _cloud_marker(entry)
    if marker:
        cursors[marker[0]] = max(cursors.get(marker[0], 0), marker[1])
    return cursors


def _carry_cursors(entry, previous):
    # A local choice may replace a cloud choice. Keep its already-applied cloud
    # watermark so the next download cannot replay an older remote label.
    cursors = _cloud_cursors(previous)
    for source, cloud_id in _cloud_cursors(entry).items():
        cursors[source] = max(cursors.get(source, 0), cloud_id)
    marker = _cloud_marker(entry)
    if marker and cursors.get(marker[0], 0) <= marker[1]:
        cursors.pop(marker[0], None)
    result = {**entry}
    if cursors:
        result["_cloud_cursors"] = cursors
    else:
        result.pop("_cloud_cursors", None)
    return result


def _read_rows(raw):
    rows = []
    for line in raw.splitlines(keepends=True):
        try:
            entry = json.loads(line.decode("utf-8-sig"))
        except (UnicodeError, ValueError):
            entry = None
        rows.append((entry, line))
    return rows


def _latest_rows(rows):
    result = []
    positions = {}
    for entry, line in rows:
        key = _feedback_key(entry)
        if key is None:
            result.append((entry, line))
            continue
        previous_index = positions.get(key)
        if previous_index is None:
            positions[key] = len(result)
            result.append((entry, line))
            continue
        previous = result[previous_index][0]
        marker = _cloud_marker(entry)
        # Two concurrent downloads may complete in a different order. A stale
        # cloud event must not replace a later saved event from the same source.
        if marker and marker[1] <= _cloud_cursors(previous).get(marker[0], 0):
            continue
        retained = _carry_cursors(entry, previous)
        if retained != entry:
            line = (json.dumps(retained, ensure_ascii=False) + "\n").encode("utf-8")
        result[previous_index] = (retained, line)
    return result


def _write_atomic(path, data):
    descriptor, temporary_name = tempfile.mkstemp(prefix=".feedback-", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # Polling viewers/editors briefly open the file on Windows. Retry those
        # short reader locks; a persistent lock still fails without losing data.
        for attempt in range(5):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05)
    finally:
        temporary.unlink(missing_ok=True)


def merge_feedback_records(directory, incoming) -> int:
    """Save current choices atomically; return newly received event count.

    Original bytes and received changes remain in backup/history files. The
    primary JSONL contains one current label per identified recording and code.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "feedback.jsonl"
    with _lock_feedback_directory(directory):
        original = path.read_bytes() if path.exists() else b""
        rows = _read_rows(original)
        seen = {_cloud_marker(entry) for entry, _ in rows}
        current = {_feedback_key(entry): entry for entry, _ in _latest_rows(rows) if _feedback_key(entry) is not None}
        accepted = []
        for entry in incoming:
            marker, key = _cloud_marker(entry), _feedback_key(entry)
            if marker:
                if marker in seen or (key and marker[1] <= _cloud_cursors(current.get(key)).get(marker[0], 0)):
                    continue
                seen.add(marker)
            if key is not None:
                entry = _carry_cursors(entry, current.get(key))
            line = (json.dumps(entry, ensure_ascii=False) + "\n").encode("utf-8")
            accepted.append((entry, line))
            if key is not None:
                current[key] = entry

        canonical = _latest_rows(rows + accepted)
        output = b"".join(line if line.endswith(b"\n") else line + b"\n" for _, line in canonical)
        if output != original:
            backup = directory / "feedback.before-latest-choice.jsonl"
            if original and not backup.exists():
                with backup.open("xb") as stream:
                    stream.write(original)
                    stream.flush()
                    os.fsync(stream.fileno())
            if accepted:
                # Write history before replacing the current view, so an update
                # can never discard the prior label without a retained copy.
                with (directory / "feedback_history.jsonl").open("ab") as history:
                    history.write(b"".join(line for _, line in accepted))
                    history.flush()
                    os.fsync(history.fileno())
            _write_atomic(path, output)
        return len(accepted)


def append_feedback(req: FeedbackRequest) -> Dict[str, Any]:
    """Save the latest choice; the historical function name stays compatible."""
    logged_at = datetime.datetime.now().isoformat()
    entry = {
        "timestamp": logged_at,
        "code": req.code.strip().upper(),
        "description": req.description or "",
        "evidence_phrase": req.evidence_phrase or "",
        "word_indices": req.word_indices,
        "is_correct": req.is_correct,
        "transcript_base": req.transcript_base,
        "concepts": req.concepts,
    }
    directory = Path(os.getenv("FEEDBACK_DIR", r"C:\DoctorProjectData\feedback"))
    directory.mkdir(parents=True, exist_ok=True)
    merge_feedback_records(directory, [entry])
    return {"ok": True, "logged_at": logged_at}
