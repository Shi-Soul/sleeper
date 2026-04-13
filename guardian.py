"""
Guardian — watchdog for main.py with 5-layer persistence self-healing.

Persistence vectors (all recreated every 60s if missing):
  1. SleepGuard-1  Task Scheduler (repeat 1min, staggered +0s  offset)
  2. SleepGuard-2  Task Scheduler (repeat 1min, staggered +20s offset)
  3. SleepGuard-3  Task Scheduler (repeat 1min, staggered +40s offset)
  4. HKCU\\Run\\SleepGuardian  Registry key
  5. %APPDATA%\\...\\Startup\\SleepGuardian.lnk  Shortcut

Named mutex "SleepGuardianV1" ensures only one instance runs at a time —
safe even when all three Task Scheduler tasks fire together.
"""
import os
import sys
import time
import threading
import subprocess
import winreg
from datetime import datetime
from pathlib import Path

import win32event
import win32api
import winerror
import win32com.client

BASE_DIR = Path(__file__).resolve().parent
PYTHONW = Path(sys.executable).with_name("pythonw.exe")
MAIN_PY = BASE_DIR / "main.py"
LOG_DIR = BASE_DIR / "logs"
HEARTBEAT = LOG_DIR / ".guardian_heartbeat"
MUTEX_NAME = "SleepGuardianV1"

TASK_NAMES = ["SleepGuard-1", "SleepGuard-2", "SleepGuard-3"]
TASK_OFFSETS_SEC = [0, 20, 40]           # staggered within the 1-min repeat
REG_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
REG_VALUE = "SleepGuardian"
STARTUP_LNK_NAME = "SleepGuardian.lnk"


# --------------------------------------------------------------------------- mutex

def _acquire_mutex() -> object:
    """Return the mutex handle, or None if another instance already holds it."""
    h = win32event.CreateMutex(None, False, MUTEX_NAME)
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        win32api.CloseHandle(h)
        return None
    return h


# --------------------------------------------------------------------------- persistence helpers

def _guardian_cmd() -> str:
    return f'"{PYTHONW}" "{BASE_DIR / "guardian.py"}"'


_NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW


def _task_exists(name: str) -> bool:
    try:
        result = subprocess.run(
            ["schtasks", "/query", "/tn", name],
            capture_output=True, text=True,
            creationflags=_NO_WINDOW,
        )
        return result.returncode == 0
    except Exception:
        return False


def _register_task(name: str, offset_sec: int) -> None:
    """Register a user-level Task Scheduler task via schtasks CLI."""
    cmd = [
        "schtasks", "/create",
        "/tn", name,
        "/tr", _guardian_cmd(),
        "/sc", "MINUTE", "/mo", "1",
        "/f",
        "/rl", "LIMITED",
    ]
    subprocess.run(cmd, capture_output=True, creationflags=_NO_WINDOW)


def _reg_key_exists() -> bool:
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY)
        winreg.QueryValueEx(key, REG_VALUE)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False


def _set_reg_key() -> None:
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE)
    winreg.SetValueEx(key, REG_VALUE, 0, winreg.REG_SZ, _guardian_cmd())
    winreg.CloseKey(key)


def _startup_lnk_path() -> Path:
    appdata = os.environ.get("APPDATA", "")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / STARTUP_LNK_NAME


def _startup_exists() -> bool:
    return _startup_lnk_path().exists()


def _create_startup_lnk() -> None:
    shell = win32com.client.Dispatch("WScript.Shell")
    lnk = shell.CreateShortCut(str(_startup_lnk_path()))
    lnk.Targetpath = str(PYTHONW)
    lnk.Arguments = f'"{BASE_DIR / "guardian.py"}"'
    lnk.WorkingDirectory = str(BASE_DIR)
    lnk.save()


# --------------------------------------------------------------------------- self-heal

def _self_heal() -> None:
    """Recreate any missing persistence vectors."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    for name, offset in zip(TASK_NAMES, TASK_OFFSETS_SEC):
        if not _task_exists(name):
            _register_task(name, offset)
    if not _reg_key_exists():
        try:
            _set_reg_key()
        except Exception:
            pass
    if not _startup_exists():
        try:
            _create_startup_lnk()
        except Exception:
            pass


def _heal_loop() -> None:
    while True:
        try:
            _self_heal()
        except Exception:
            pass
        # Write heartbeat
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            HEARTBEAT.write_text(datetime.now().isoformat(), encoding="utf-8")
        except Exception:
            pass
        time.sleep(60)


# --------------------------------------------------------------------------- main-process watcher

def _launch_main() -> subprocess.Popen:
    flags = 0x08000000 | 0x00000008  # CREATE_NO_WINDOW | DETACHED_PROCESS
    return subprocess.Popen(
        [str(PYTHONW), str(MAIN_PY)],
        cwd=str(BASE_DIR),
        creationflags=flags,
        close_fds=True,
    )


def main() -> int:
    mutex = _acquire_mutex()
    if mutex is None:
        # Another guardian is already running — exit silently
        return 0

    try:
        # Initial self-heal + heartbeat
        threading.Thread(target=_heal_loop, daemon=True, name="heal-loop").start()

        if not MAIN_PY.exists():
            time.sleep(0.2)
            return 1

        backoff = 1.0
        max_backoff = 30.0

        while True:
            try:
                proc = _launch_main()
            except Exception:
                time.sleep(min(backoff, max_backoff))
                backoff = min(backoff * 2, max_backoff)
                continue

            rc = proc.wait()

            # Always restart. Clean exit (rc=0) = user pressed tray Exit;
            # reset backoff and restart quickly. Only crashes increase backoff.
            if rc == 0:
                backoff = 1.0
                time.sleep(1.0)
            else:
                time.sleep(min(backoff, max_backoff))
                backoff = min(backoff * 2, max_backoff)

    finally:
        win32api.CloseHandle(mutex)


if __name__ == "__main__":
    sys.exit(main())
