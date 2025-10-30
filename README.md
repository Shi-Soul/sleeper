# Sleeper

Sleeper is a small Windows utility to control computer usage during specific time windows. It minimizes all windows and shows a warning popup when disallowed applications are active in restricted periods. Configuration is done via a simple YAML file (powered by Hydra).

Only works on Windows.

## Installation

```bash
pip install -r requirements.txt
```


## Usage

Run from the `sleeper` directory:

```bash
python main.py
```

- A system tray icon will appear; right-click it to exit.
- Logs and resolved configs are written under `outputs/<date>/<time>/` by Hydra.

To run as a background service or at startup, you can use `pythonw.exe` (see `run_bg.bat`). Ensure you use the correct Python interpreter.


## Startup at login (Windows)

Place a shortcut to `sleeper/run_bg.bat` into a Startup folder to auto-run at user logon.

### Per-user startup (recommended)
- Open: Press Win+R, type `shell:startup`, press Enter
- Path: `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`
- Action: Put a shortcut to `run_bg.bat` in this folder

### All users startup (requires admin)
- Open: Press Win+R, type `shell:common startup`, press Enter
- Path: `%ProgramData%\Microsoft\Windows\Start Menu\Programs\StartUp`
- Action: Put the shortcut here to apply for all accounts



## Configuration

Configuration is managed with Hydra and read from `config.yaml` in the same directory. You can define multiple time windows; each window has its own mode and app list.

Key fields:

- `check_interval` (seconds): how often the active window is checked
- `time_windows`: list of time windows
  - `name`: window name (for logging)
  - `start_time`: `HH:MM` (24h)
  - `end_time`: `HH:MM` (24h)
  - `mode`: `blacklist` or `whitelist`
  - `app_list`: list of executable file names (e.g., `steam.exe`, `notepad.exe`)

Example `config.yaml`:

```yaml
# How frequently to check the active app (in seconds)
check_interval: 5

# Define restriction windows
time_windows:
  - name: Night Block
    start_time: "00:00"
    end_time: "06:00"
    mode: blacklist
    app_list:
      - steam.exe
      - chrome.exe

  - name: Focus Hours
    start_time: "09:00"
    end_time: "17:00"
    mode: whitelist
    app_list:
      - code.exe
      - pycharm64.exe
      - cmd.exe
```

Notes:
- Windows across midnight are supported (e.g., `23:00` to `06:00`).
- In `blacklist` mode, any app in `app_list` is disallowed; others are allowed.
- In `whitelist` mode, only apps in `app_list` are allowed; others are disallowed.


## How it works

- Retrieves the active foreground window and owning process executable using Win32 APIs and `psutil`.
- Evaluates whether the current time falls into any configured time window.
- Checks allowance per window mode and application list.
- On violation, minimizes all windows and shows a topmost warning popup.



