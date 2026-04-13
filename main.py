"""Sleeper — main monitoring process."""
import os
import sys
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import win32gui
import win32process
import win32con
import psutil
import pystray
from PIL import Image

import logger
from config import Config, ConfigManager
from overlay import ViolationOverlay
from status_window import StatusWindow

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.yaml"


class Sleeper:
    def __init__(self):
        self._cfg_mgr = ConfigManager(CONFIG_PATH, on_reload=self._on_config_reload)
        logger.init(BASE_DIR / self._cfg_mgr.config.log_dir)
        logger.log("app_start")

        # Override state
        self._override_until: Optional[datetime] = None
        self._override_lock = threading.Lock()

        # Violation rate-limiting: last log time per window name
        self._last_overlay: dict[str, datetime] = {}


        # Tkinter root (for dialogs and StatusWindow)
        self._tk_root: tk.Tk = None  # type: ignore
        self._tk_ready = threading.Event()

        # Components (built after tk root is ready)
        self._overlay: Optional[ViolationOverlay] = None
        self._status_win: Optional[StatusWindow] = None
        self._icon: Optional[pystray.Icon] = None

    # ----------------------------------------------------------------- startup

    def run(self) -> None:
        threading.Thread(target=self._tk_thread, daemon=True, name="tk-main").start()
        self._tk_ready.wait(timeout=5)

        self._overlay = ViolationOverlay(self._tk_root, on_override_click=self._open_override_dialog)
        self._status_win = StatusWindow(self._tk_root, lambda: self._cfg_mgr.config)

        threading.Thread(target=self._monitor_loop, daemon=True, name="monitor").start()

        self._icon = self._build_tray()
        self._icon.run()  # blocks main thread
        logger.log("app_exit")

    # ----------------------------------------------------------------- Tk root

    def _tk_thread(self) -> None:
        self._tk_root = tk.Tk()
        self._tk_root.withdraw()
        self._tk_ready.set()
        self._tk_root.mainloop()

    # ----------------------------------------------------------------- tray

    def _build_tray(self) -> pystray.Icon:
        from icon_util import generate_tray_icon
        ico_path = str(BASE_DIR / "sleeper64.ico")
        generate_tray_icon(ico_path, size=64)
        image = Image.open(ico_path)

        icon = pystray.Icon("sleeper", image, "Sleeper", menu=pystray.Menu(
            pystray.MenuItem(self._tray_status_label, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Emergency Override…", self._tray_override,
                             visible=lambda item: self._is_restricted_now()),
            pystray.MenuItem("Cancel Override", self._tray_cancel_override,
                             visible=lambda item: self._override_active()),
            pystray.MenuItem("View Status & Logs", self._tray_status),
            pystray.MenuItem("Edit Config", self._tray_edit_config),
            pystray.MenuItem("Reload Config", self._tray_reload_config),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._tray_exit,
                             visible=lambda item: not self._is_restricted_now()),
        ))
        return icon

    def _tray_status_label(self, item) -> str:
        with self._override_lock:
            if self._override_until and datetime.now() < self._override_until:
                remaining = int((self._override_until - datetime.now()).total_seconds() / 60)
                return f"🔓 Override — {remaining} min remaining"
        cfg = self._cfg_mgr.config
        w = cfg.is_restricted_now(datetime.now().time())
        if w:
            return f"⛔ {w.name}  {w.start_time.strftime('%H:%M')}–{w.end_time.strftime('%H:%M')}"
        return "✅ Sleeper — Active"

    def _tray_override(self, icon, item):
        self._tk_root.after(0, self._open_override_dialog)

    def _tray_cancel_override(self, icon, item):
        with self._override_lock:
            self._override_until = None
        logger.log("override_cancelled")

    def _tray_status(self, icon, item):
        self._tk_root.after(0, self._status_win.toggle)

    def _tray_edit_config(self, icon, item):
        os.startfile(str(CONFIG_PATH))

    def _tray_reload_config(self, icon, item):
        self._cfg_mgr.reload()

    def _tray_exit(self, icon, item):
        self._overlay.destroy()
        self._tk_root.after(0, self._tk_root.destroy)
        icon.stop()

    # ----------------------------------------------------------------- override dialog

    def _open_override_dialog(self) -> None:
        """Show the Emergency Override dialog (Tk thread)."""
        max_min = self._cfg_mgr.config.override_max_minutes

        dlg = tk.Toplevel(self._tk_root)
        dlg.title("Emergency Override")
        dlg.geometry("380x210")
        dlg.configure(bg="#1e1e2e")
        dlg.attributes("-topmost", True)
        dlg.resizable(False, False)
        # Do NOT use grab_set() — on Windows it can intercept Win32 messages
        # and starve pystray's tray icon message loop, making the tray vanish.
        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)

        tk.Label(dlg, text="Reason (min 10 chars):", bg="#1e1e2e", fg="#c8d3f5",
                 font=("Segoe UI", 10)).pack(anchor="w", padx=16, pady=(16, 2))
        reason_var = tk.StringVar()
        reason_entry = tk.Entry(dlg, textvariable=reason_var, width=44,
                                bg="#2d2d44", fg="#ffffff", insertbackground="white",
                                relief="flat", font=("Segoe UI", 10))
        reason_entry.pack(padx=16, pady=(0, 10))
        reason_entry.focus_set()

        tk.Label(dlg, text="Duration:", bg="#1e1e2e", fg="#c8d3f5",
                 font=("Segoe UI", 10)).pack(anchor="w", padx=16)
        durations = [d for d in [5, 15, 30, 60] if d <= max_min]
        dur_var = tk.IntVar(value=durations[0])
        dur_frame = tk.Frame(dlg, bg="#1e1e2e")
        dur_frame.pack(anchor="w", padx=16, pady=(4, 12))
        for d in durations:
            tk.Radiobutton(dur_frame, text=f"{d} min", variable=dur_var, value=d,
                           bg="#1e1e2e", fg="#c8d3f5", selectcolor="#2d2d44",
                           activebackground="#1e1e2e").pack(side="left", padx=6)

        err_label = tk.Label(dlg, text="", bg="#1e1e2e", fg="#ff6b6b",
                             font=("Segoe UI", 9))
        err_label.pack()

        def confirm():
            reason = reason_var.get().strip()
            if len(reason) < 10:
                err_label.config(text="Reason too short (min 10 chars).")
                return
            mins = dur_var.get()
            until = datetime.now() + timedelta(minutes=mins)
            with self._override_lock:
                self._override_until = until
            logger.log("override_granted", reason=reason, minutes=mins)
            dlg.destroy()

        tk.Button(dlg, text="Confirm Override", command=confirm,
                  bg="#5a3a8c", fg="white", relief="flat",
                  font=("Segoe UI", 10, "bold")).pack(pady=2)

    # ----------------------------------------------------------------- helpers

    def _is_restricted_now(self) -> bool:
        return self._cfg_mgr.config.is_restricted_now(datetime.now().time()) is not None

    def _override_active(self) -> bool:
        with self._override_lock:
            return bool(self._override_until and datetime.now() < self._override_until)

    def _on_config_reload(self, cfg: Config) -> None:
        logger.log("config_reloaded")

    def _get_active_app(self) -> tuple[int, str, str, int]:
        """Returns (hwnd, window_title, exe_basename, pid). hwnd=0 on failure."""
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return 0, "", "", 0
            title = win32gui.GetWindowText(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if not pid:
                return hwnd, title, "", 0
            proc = psutil.Process(pid)
            return hwnd, title, os.path.basename(proc.exe()).lower(), pid
        except Exception:
            return 0, "", "", 0


    # ----------------------------------------------------------------- monitor loop

    def _monitor_loop(self) -> None:
        my_pid = os.getpid()
        while True:
            cfg = self._cfg_mgr.config
            now = datetime.now()

            # If override active, skip enforcement
            with self._override_lock:
                if self._override_until:
                    if now < self._override_until:
                        self._overlay.hide()
                        time.sleep(cfg.check_interval)
                        continue
                    else:
                        logger.log("override_expired")
                        self._override_until = None

            window = cfg.is_restricted_now(now.time())
            if window is None:
                self._overlay.hide()
                time.sleep(cfg.check_interval)
                continue

            hwnd, title, app_name, pid = self._get_active_app()

            # Skip when our own windows (overlay, dialogs) are foreground —
            # avoids whitelisting pythonw.exe and maintains current overlay state.
            if pid == my_pid or not app_name:
                time.sleep(cfg.check_interval)
                continue

            if not cfg.is_app_allowed(app_name, window):
                # Minimize only the specific violating window
                if hwnd:
                    try:
                        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                    except Exception:
                        pass

                # Force-kill (blacklist + force_kill only)
                if window.mode == "blacklist" and window.force_kill:
                    self._force_kill(app_name)

                # Show banner; rate-limit only the log write (not the show call)
                self._overlay.show(window.name, app_name, window.end_time)
                last = self._last_overlay.get(window.name)
                if last is None or (now - last).total_seconds() >= 5:
                    self._last_overlay[window.name] = now
                    logger.log("violation", rule=window.name, app=app_name, title=title)
            else:
                self._overlay.hide()

            time.sleep(cfg.check_interval)

    def _force_kill(self, app_name: str) -> None:
        for proc in psutil.process_iter(["name", "pid"]):
            try:
                if proc.info["name"] and proc.info["name"].lower() == app_name:
                    proc.kill()
                    logger.log("force_killed", app=app_name, pid=proc.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass


def main() -> None:
    app = Sleeper()
    app.run()


if __name__ == "__main__":
    main()
