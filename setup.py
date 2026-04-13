"""
Sleeper setup / health-check / uninstall CLI.

Usage:
    python setup.py              # install all persistence layers + start guardian
    python setup.py --status     # show health of all 5 persistence vectors
    python setup.py --uninstall  # remove all persistence layers + stop guardian
"""
import os
import sys
import subprocess
import winreg
import argparse
from pathlib import Path

import win32com.client

_NO_WINDOW = 0x08000000

BASE_DIR = Path(__file__).resolve().parent
PYTHONW = Path(sys.executable).with_name("pythonw.exe")

TASK_NAMES = ["SleepGuard-1", "SleepGuard-2", "SleepGuard-3"]
REG_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
REG_VALUE = "SleepGuardian"
STARTUP_LNK_NAME = "SleepGuardian.lnk"


def _guardian_cmd() -> str:
    return f'"{PYTHONW}" "{BASE_DIR / "guardian.py"}"'


# ------------------------------------------------------------------ tasks

def _task_exists(name: str) -> bool:
    r = subprocess.run(["schtasks", "/query", "/tn", name],
                       capture_output=True, text=True, creationflags=_NO_WINDOW)
    return r.returncode == 0


def _register_task(name: str) -> bool:
    cmd = [
        "schtasks", "/create",
        "/tn", name,
        "/tr", _guardian_cmd(),
        "/sc", "MINUTE", "/mo", "1",
        "/f", "/rl", "LIMITED",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, creationflags=_NO_WINDOW)
    return r.returncode == 0


def _delete_task(name: str) -> None:
    subprocess.run(["schtasks", "/delete", "/tn", name, "/f"],
                   capture_output=True, creationflags=_NO_WINDOW)


# ------------------------------------------------------------------ registry

def _reg_exists() -> bool:
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY)
        winreg.QueryValueEx(k, REG_VALUE)
        winreg.CloseKey(k)
        return True
    except FileNotFoundError:
        return False


def _set_reg() -> None:
    k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE)
    winreg.SetValueEx(k, REG_VALUE, 0, winreg.REG_SZ, _guardian_cmd())
    winreg.CloseKey(k)


def _del_reg() -> None:
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(k, REG_VALUE)
        winreg.CloseKey(k)
    except FileNotFoundError:
        pass


# ------------------------------------------------------------------ startup shortcut

def _lnk_path() -> Path:
    appdata = os.environ.get("APPDATA", "")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / STARTUP_LNK_NAME


def _lnk_exists() -> bool:
    return _lnk_path().exists()


def _create_lnk() -> None:
    shell = win32com.client.Dispatch("WScript.Shell")
    lnk = shell.CreateShortCut(str(_lnk_path()))
    lnk.Targetpath = str(PYTHONW)
    lnk.Arguments = f'"{BASE_DIR / "guardian.py"}"'
    lnk.WorkingDirectory = str(BASE_DIR)
    lnk.save()


def _del_lnk() -> None:
    p = _lnk_path()
    if p.exists():
        p.unlink()


# ------------------------------------------------------------------ guardian process

def _start_guardian() -> None:
    subprocess.Popen(
        [str(PYTHONW), str(BASE_DIR / "guardian.py")],
        cwd=str(BASE_DIR),
        creationflags=0x08000000,   # CREATE_NO_WINDOW
        close_fds=True,
    )


def _stop_guardian() -> None:
    """Kill all pythonw.exe processes running guardian.py."""
    import psutil
    guardian_path = str(BASE_DIR / "guardian.py").lower()
    main_path = str(BASE_DIR / "main.py").lower()
    for proc in psutil.process_iter(["name", "cmdline", "pid"]):
        try:
            name = (proc.info["name"] or "").lower()
            cmd = " ".join(proc.info["cmdline"] or []).lower()
            if name in ("python.exe", "pythonw.exe") and (
                guardian_path in cmd or main_path in cmd
            ):
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


# ------------------------------------------------------------------ actions

TICK = "✓"
CROSS = "✗"


def _fmt(ok: bool, label: str) -> str:
    return f"  [{TICK if ok else CROSS}] {label}"


def cmd_status() -> None:
    print("Sleeper — persistence layer status\n")
    for name in TASK_NAMES:
        ok = _task_exists(name)
        print(_fmt(ok, f"Task Scheduler: {name}"))
    print(_fmt(_reg_exists(),  f"Registry Run:   {REG_VALUE}"))
    print(_fmt(_lnk_exists(),  f"Startup LNK:    {STARTUP_LNK_NAME}"))
    print()


def cmd_install() -> None:
    print("Installing Sleeper persistence layers...\n")
    for name in TASK_NAMES:
        ok = _register_task(name)
        print(_fmt(ok, f"Task Scheduler: {name}"))
    try:
        _set_reg()
        print(_fmt(True, f"Registry Run:   {REG_VALUE}"))
    except Exception as e:
        print(_fmt(False, f"Registry Run:   {e}"))
    try:
        _create_lnk()
        print(_fmt(True, f"Startup LNK:    {STARTUP_LNK_NAME}"))
    except Exception as e:
        print(_fmt(False, f"Startup LNK:    {e}"))

    print("\nStarting guardian...")
    _start_guardian()
    print("Done. Sleeper is running.\n")


def cmd_uninstall() -> None:
    # Block uninstall during active restriction windows
    try:
        from config import ConfigManager
        from datetime import datetime as _dt
        _cfg = ConfigManager(BASE_DIR / "config.yaml").config
        _w = _cfg.is_restricted_now(_dt.now().time())
        if _w:
            print(f"[BLOCKED] Cannot uninstall during restricted window '{_w.name}' "
                  f"({_w.start_time.strftime('%H:%M')}–{_w.end_time.strftime('%H:%M')}).")
            print("Use Emergency Override first, or wait until the window ends.")
            sys.exit(1)
    except SystemExit:
        raise
    except Exception as e:
        print(f"[WARN] Could not check restriction status: {e}")

    print("Uninstalling Sleeper...\n")
    print("  Stopping running processes...")
    _stop_guardian()

    for name in TASK_NAMES:
        _delete_task(name)
        print(f"  Removed task: {name}")
    _del_reg()
    print(f"  Removed registry key: {REG_VALUE}")
    _del_lnk()
    print(f"  Removed startup shortcut: {STARTUP_LNK_NAME}")
    print("\nSleeper uninstalled.\n")


# ------------------------------------------------------------------ entry

def main() -> None:
    parser = argparse.ArgumentParser(description="Sleeper setup")
    parser.add_argument("--status",    action="store_true", help="Show health of all layers")
    parser.add_argument("--uninstall", action="store_true", help="Remove all layers + stop")
    args = parser.parse_args()

    if args.status:
        cmd_status()
    elif args.uninstall:
        cmd_uninstall()
    else:
        cmd_install()


if __name__ == "__main__":
    main()
