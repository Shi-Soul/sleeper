"""PyYAML-based config loader with mtime hot-reload."""
import threading
import time
import os
from dataclasses import dataclass, field
from datetime import time as dtime
from pathlib import Path
from typing import Callable, List, Optional

import yaml


@dataclass
class TimeWindow:
    name: str
    start_time: dtime
    end_time: dtime
    mode: str          # "whitelist" | "blacklist"
    app_list: List[str]
    force_kill: bool = False


@dataclass
class Config:
    check_interval: float
    log_dir: str
    override_max_minutes: int
    time_windows: List[TimeWindow]

    def is_restricted_now(self, t: dtime) -> Optional[TimeWindow]:
        """Return the first active TimeWindow, or None."""
        for w in self.time_windows:
            if _in_window(t, w.start_time, w.end_time):
                return w
        return None

    def is_app_allowed(self, app_name: str, window: TimeWindow) -> bool:
        name_lower = app_name.lower()
        list_lower = [a.lower() for a in window.app_list]
        if window.mode == "whitelist":
            return name_lower in list_lower
        elif window.mode == "blacklist":
            return name_lower not in list_lower
        return True


def _in_window(t: dtime, start: dtime, end: dtime) -> bool:
    if start <= end:
        return start <= t <= end
    return t >= start or t <= end


def _parse(path: Path) -> Config:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    windows = []
    for w in raw.get("time_windows", []):
        start = dtime.fromisoformat(w["start_time"])
        end   = dtime.fromisoformat(w["end_time"])
        windows.append(TimeWindow(
            name=w["name"],
            start_time=start,
            end_time=end,
            mode=w.get("mode", "whitelist"),
            app_list=w.get("app_list", []),
            force_kill=w.get("force_kill", False),
        ))

    return Config(
        check_interval=float(raw.get("check_interval", 0.5)),
        log_dir=str(raw.get("log_dir", "logs")),
        override_max_minutes=int(raw.get("override_max_minutes", 60)),
        time_windows=windows,
    )


class ConfigManager:
    def __init__(self, path: str | Path, on_reload: Optional[Callable[[Config], None]] = None):
        self._path = Path(path)
        self._on_reload = on_reload
        self._lock = threading.RLock()
        self._config: Config = _parse(self._path)
        self._mtime: float = self._path.stat().st_mtime
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._watch, daemon=True, name="config-watcher")
        self._thread.start()

    @property
    def config(self) -> Config:
        with self._lock:
            return self._config

    def reload(self) -> Config:
        """Force an immediate reload from disk."""
        with self._lock:
            self._config = _parse(self._path)
            self._mtime = self._path.stat().st_mtime
            if self._on_reload:
                self._on_reload(self._config)
            return self._config

    def _watch(self) -> None:
        while not self._stop.wait(2.0):
            try:
                mtime = self._path.stat().st_mtime
                if mtime != self._mtime:
                    self.reload()
            except Exception:
                pass

    def stop(self) -> None:
        self._stop.set()
