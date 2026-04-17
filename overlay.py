"""Persistent top-center violation banner — always-on-top, no close button."""
import tkinter as tk
from datetime import time as dtime
from typing import Callable, Optional


class ViolationOverlay:
    """
    A persistent, always-on-top banner at the top-center of the screen.
    NOT fullscreen — the user can still click through to allowed apps.
    Enforcement comes from repeated per-window minimization in the monitor loop.

    show()/hide() are safe to call from any thread via root.after().
    """

    WIDTH = 700
    HEIGHT = 100

    def __init__(self, tk_root: tk.Tk, on_override_click: Optional[Callable] = None):
        self._root = tk_root
        self._on_override = on_override_click
        self._win: Optional[tk.Toplevel] = None
        self._label_var: Optional[tk.StringVar] = None
        self._override_btn: Optional[tk.Button] = None

    # ── public API (thread-safe) ─────────────────────────────────────────────

    def show(self, rule_name: str, app_name: str, restriction_end: Optional[dtime] = None,
             allow_override: bool = True) -> None:
        end_str = restriction_end.strftime("%H:%M") if restriction_end else "—"
        msg = f"Rule: {rule_name}   ·   Until: {end_str}   ·   Blocked: {app_name}"
        self._root.after(0, lambda: self._do_show(msg, allow_override))

    def hide(self) -> None:
        self._root.after(0, self._do_hide)

    def destroy(self) -> None:
        self._root.after(0, self._do_destroy)

    # ── Tk-thread internals ───────────────────────────────────────────────────

    def _build_window(self) -> None:
        if self._win and self._win.winfo_exists():
            return
        self._label_var = tk.StringVar()

        sw = self._root.winfo_screenwidth()
        x = (sw - self.WIDTH) // 2
        y = 0

        win = tk.Toplevel(self._root)
        win.overrideredirect(True)          # no title bar, no close button
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.93)
        win.configure(bg="#1a1a2e")
        win.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")
        win.resizable(False, False)

        inner = tk.Frame(win, bg="#1a1a2e")
        inner.pack(fill="both", expand=True, padx=14, pady=10)

        tk.Label(inner, text="⛔  Sleeper — Restriction Active",
                 bg="#1a1a2e", fg="#ff6b6b",
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")

        tk.Label(inner, textvariable=self._label_var,
                 bg="#1a1a2e", fg="#c0c0d8",
                 font=("Segoe UI", 9), justify="left").pack(anchor="w", pady=(2, 0))

        self._override_btn = tk.Button(inner, text="Emergency Override…",
                                       bg="#2d2050", fg="#c8a0ff",
                                       activebackground="#3a2a6a", activeforeground="#e0c0ff",
                                       relief="flat", bd=0, padx=10, pady=3,
                                       font=("Segoe UI", 8, "bold"),
                                       cursor="hand2",
                                       command=self._override)

        self._win = win

    def _do_show(self, msg: str, allow_override: bool) -> None:
        self._build_window()
        if self._label_var:
            self._label_var.set(msg)
        if self._override_btn:
            if allow_override:
                self._override_btn.place(relx=1.0, rely=0.0, anchor="ne", x=-2, y=2)
            else:
                self._override_btn.place_forget()
        if self._win and self._win.winfo_exists():
            self._win.deiconify()
            self._win.lift()
            self._win.attributes("-topmost", True)
            # No focus_force() — user must be able to click other allowed apps

    def _do_hide(self) -> None:
        if self._win and self._win.winfo_exists():
            self._win.withdraw()

    def _do_destroy(self) -> None:
        if self._win and self._win.winfo_exists():
            self._win.destroy()
            self._win = None

    def _override(self) -> None:
        self._do_hide()
        if self._on_override:
            self._on_override()
