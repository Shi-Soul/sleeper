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


def read_today() -> list[dict]:
    path = _log_path()
    if not path.exists():
        return []
    lines = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if raw:
                try:
                    lines.append(json.loads(raw))
                except json.JSONDecodeError:
                    pass
    return lines
