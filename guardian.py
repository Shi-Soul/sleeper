import os
import sys
import time
import subprocess
from pathlib import Path


def launch_main(script_path: Path) -> subprocess.Popen:
    creationflags = 0
    # CREATE_NO_WINDOW (0x08000000) | DETACHED_PROCESS (0x00000008)
    if os.name == "nt":
        creationflags = 0x08000000 | 0x00000008

    return subprocess.Popen(
        [sys.executable, str(script_path)],
        cwd=str(script_path.parent),
        creationflags=creationflags,
        close_fds=True,
    )


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    main_py = script_dir / "main.py"

    if not main_py.exists():
        # Fail fast but silently (no console) with a tiny delay so caller returns.
        time.sleep(0.2)
        return 1

    backoff_seconds = 1.0
    max_backoff_seconds = 30.0

    while True:
        try:
            proc = launch_main(main_py)
        except Exception:
            time.sleep(min(backoff_seconds, max_backoff_seconds))
            backoff_seconds = min(backoff_seconds * 2, max_backoff_seconds)
            continue

        # Block until child exits
        return_code = proc.wait()

        # If the app exits cleanly, don't restart.
        if return_code == 0:
            return 0

        # Crash or non-zero exit; restart with capped exponential backoff
        time.sleep(min(backoff_seconds, max_backoff_seconds))
        backoff_seconds = min(backoff_seconds * 2, max_backoff_seconds)


if __name__ == "__main__":
    sys.exit(main())


