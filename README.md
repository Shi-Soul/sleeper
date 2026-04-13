# Sleeper

Sleeper is a lightweight Windows utility that restricts computer usage during configured time windows. It is designed to be portable, hard to bypass impulsively, and invisible during normal use.

**Windows only.**

---

## Installation

```bash
pip install -r requirements.txt
python setup.py
```

`setup.py` registers 5 persistence layers (no admin needed) and starts the guardian:

```
[✓] Task Scheduler: SleepGuard-1  (repeat every 1 min, offset +0s)
[✓] Task Scheduler: SleepGuard-2  (repeat every 1 min, offset +20s)
[✓] Task Scheduler: SleepGuard-3  (repeat every 1 min, offset +40s)
[✓] Registry Run:   SleepGuardian
[✓] Startup LNK:    SleepGuardian.lnk
Done. Sleeper is running.
```

### Other setup commands

```bash
python setup.py --status      # health check of all 5 layers
python setup.py --uninstall   # stop + remove everything
```

---

## How it works

```
3 staggered Task Scheduler tasks (every ~20s collectively)
+ Registry HKCU\Run  +  Startup shortcut
        ↓
    guardian.py  [Named Mutex: only 1 instance]
        ├── watches + restarts main.py on crash
        └── self-heal thread (every 60s): recreates any missing persistence vector
                ↓
            main.py  — monitoring + system tray
```

**Anti-bypass**: To fully disable Sleeper, you must simultaneously kill Python processes AND delete 3 Task Scheduler tasks AND delete the Registry key AND delete the Startup shortcut — all within ~20 seconds. Any single surviving layer restores all others.

---

## Configuration

Edit `config.yaml` in the sleeper directory. Changes are **hot-reloaded automatically** (no restart needed). You can also use the tray **Edit Config** menu item to open it.

```yaml
check_interval: 0.5        # seconds between active-window checks
log_dir: logs
override_max_minutes: 60   # max Emergency Override duration

time_windows:
  - name: "Night Limit"
    start_time: "00:00"
    end_time: "06:00"
    mode: "whitelist"      # whitelist | blacklist
    force_kill: false      # (blacklist only) kill the violating process
    app_list:
      - "explorer.exe"
      - "cmd.exe"
```

- **whitelist** mode: only listed apps are allowed during the window
- **blacklist** mode: listed apps are blocked; `force_kill: true` terminates them
- Cross-midnight windows are supported (e.g. `23:00` → `06:00`)

---

## System Tray

The tray icon shows context-aware state:

| State | Label | Menu items |
|-------|-------|-----------|
| Normal | `✅ Sleeper — Active` | Status & Logs · Edit Config · Reload Config · **Exit** |
| Restricted | `⛔ Night Limit  00:00–06:00` | **Emergency Override…** · Status & Logs · Edit Config |
| Override active | `🔓 Override — 23 min remaining` | Cancel Override · Status & Logs · Edit Config |

> **Exit** is hidden during restricted hours — you must exit from a non-restricted period, or use Emergency Override first.

---

## Emergency Override

During a restricted period, click **Emergency Override…** from the tray to temporarily suspend enforcement. You must enter a reason (≥10 chars) and select a duration (5 / 15 / 30 / 60 min, capped by `override_max_minutes`). All overrides are logged.

---

## Violation Response

When a disallowed app is detected:
- All windows are **minimized** on every check cycle
- A non-blocking **overlay banner** appears in the top-right corner (at most once per 60 seconds per rule), showing the rule name, violating app, and when the restriction ends
- The banner has two buttons: **Snooze 60s** (dismiss overlay) and **Emergency Override…**
- In blacklist mode with `force_kill: true`, the violating process is killed

---

## Logs

Events are written to `logs/YYYY-MM-DD.jsonl` (JSON Lines format):

```json
{"ts": "2026-04-12T23:05:00", "event": "violation", "details": {"rule": "Night Limit", "app": "chrome.exe"}}
{"ts": "2026-04-12T23:07:30", "event": "override_granted", "details": {"reason": "urgent email", "minutes": 15}}
```

View logs from the tray → **View Status & Logs**.

---

## File structure

```
sleeper/
├── main.py           core monitor + tray
├── guardian.py       watchdog + persistence self-healing
├── config.py         PyYAML loader + hot-reload
├── overlay.py        non-blocking violation banner
├── status_window.py  Tkinter log/status viewer
├── logger.py         JSONL structured logger
├── setup.py          one-time install / uninstall / status
├── icon_util.py      tray icon generator
├── config.yaml       user configuration
├── requirements.txt
├── run_bg.bat        manual launch shortcut
└── logs/             YYYY-MM-DD.jsonl event logs
```

