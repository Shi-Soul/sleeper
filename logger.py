"""Structured JSONL event logger for Sleeper."""
import json
import threading
from datetime import datetime
from pathlib import Path


_lock = threading.Lock()
_log_dir: Path = Path("logs")


def init(log_dir: str | Path = "logs") -> None:
    global _log_dir
    _log_dir = Path(log_dir)
    _log_dir.mkdir(parents=True, exist_ok=True)


def _log_path() -> Path:
    return _log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"


def log(event: str, **details) -> None:
    record = {"ts": datetime.now().isoformat(timespec="seconds"), "event": event}
    if details:
        record["details"] = details
    line = json.dumps(record, ensure_ascii=False)
    with _lock:
        with open(_log_path(), "a", encoding="utf-8") as f:
            f.write(line + "\n")


def _read_file(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if raw:
                try:
                    records.append(json.loads(raw))
                except json.JSONDecodeError:
                    pass
    return records


def read_today() -> list[dict]:
    path = _log_path()
    if not path.exists():
        return []
    return _read_file(path)


def read_all_logs() -> list[dict]:
    """Read every *.jsonl file in log_dir, sorted chronologically."""
    records = []
    if not _log_dir.exists():
        return records
    for path in sorted(_log_dir.glob("*.jsonl")):
        records.extend(_read_file(path))
    return records


def read_range(start_date: str, end_date: str) -> list[dict]:
    """Read logs from start_date to end_date inclusive (YYYY-MM-DD strings)."""
    records = []
    if not _log_dir.exists():
        return records
    for path in sorted(_log_dir.glob("*.jsonl")):
        if start_date <= path.stem <= end_date:
            records.extend(_read_file(path))
    return records
