"""
写一个适合windows, 控制电脑使用时间的软件. 希望每天 0~6:00 限制, 只能使用白名单/黑名单软件. 希望方案尽可能简洁统一. 不要用windows自带的系统功能. 如果违规, 则minimize desktop并且弹窗提醒.

配置文件: 指定查询频率, 时间窗口, 黑名单模式还是白名单模式, 软件名单
实现方法: 
- 使用hydra读取yaml配置, 得到一列窗口( 每个列表中的element是一个时间窗口, 各有不同的模式和软件名单)

"""
import time
import tkinter as tk
from tkinter import messagebox
import logging
import sys
import threading
from PIL import Image, ImageDraw
import pystray
import os
from datetime import datetime, timedelta, time as dtime
from typing import List, Tuple

# Windows specific imports
import win32gui
import win32process


# Configuration management
import hydra
from omegaconf import DictConfig, OmegaConf

# Process information
import psutil

# Set DEBUG flag from environment variable
DEBUG : bool = os.environ.get("DEBUG", 'False').lower() == "true"

class Sleeper:
    def __init__(self, config: DictConfig):
        # Logging is configured by Hydra per the YAML config; do not override here
        self.config = config
        logging.info(f"Loaded configuration: {OmegaConf.to_yaml(self.config)}")

        self.tkroot: tk.Tk = None # type: ignore
        self.icon: pystray.Icon = None # type: ignore
        self.exit_code: int = 0

        # Setup system tray icon
        self.setup_icontray()
        
        # Setup Tkinter for popups in a separate thread
        threading.Thread(target=self.setup_tk, daemon=True).start()

    def setup_icontray(self):
        """Initializes the system tray icon."""
        # Generate and load icon from file
        try:
            from icon_util import generate_tray_icon

            base_dir = os.path.dirname(os.path.abspath(__file__))
            icon_path = os.path.join(base_dir, 'sleeper64.ico')
            
            generate_tray_icon(icon_path, size=64)
            image = Image.open(icon_path)
        except Exception as e:
            logging.error(f"Failed to generate/load tray icon: {e}")
            image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))

        menu = (
            pystray.MenuItem('Restart', self.exit_action),
        )
        self.icon = pystray.Icon("sleeper_app", image, "Sleeper", menu)
        logging.info("System tray icon setup complete.")

    def setup_tk(self):
        """Initializes the Tkinter root for popups."""
        self.tkroot = tk.Tk("sleeper")
        self.tkroot.withdraw() # Hide the main Tkinter window
        self.tkroot.mainloop()
        
    def run(self):
        """Starts the main monitoring loop and the system tray icon."""
        # Start the main monitoring loop in a separate daemon thread
        thread = threading.Thread(target=self.loop, daemon=True)
        thread.start()
        
        # Run the system tray icon in the main thread (this call blocks)
        if self.icon:
            self.icon.run()
        else:
            logging.error("System tray icon not initialized. Exiting.")
            sys.exit(1)

        # After the tray loop exits, terminate the process with the intended code
        sys.exit(self.exit_code)

    def exit_action(self, icon, item):
        """Handles the exit action from the system tray menu."""
        logging.info("Exiting application via system tray.")
        # Set non-zero exit code so guardian restarts us
        self.exit_code = 2
        if self.icon:
            self.icon.stop() # Stop the pystray icon loop
        if self.tkroot:
            self.tkroot.quit() # Properly quit the Tkinter mainloop
        # Do not call sys.exit() here (callback thread). Main thread will exit with exit_code after icon.run() returns.
        
    def _minimize_desktop(self):
        """Minimizes all open windows."""
        try:
            import win32com.client
            shell = win32com.client.Dispatch("Shell.Application")
            shell.MinimizeAll()
            logging.info("All windows are minimized")
        except Exception as e:
            logging.error(f"Error in minimizing windows: {e}")

    def _show_popup(self, message: str):
        """Shows a Tkinter warning popup."""
        def show():
            # Ensure the popup appears on top of other windows
            logging.warning(f"Popup Warning: {message}")
            if self.tkroot:
                self.tkroot.attributes('-topmost', True)
                messagebox.showinfo("Sleeper", message, parent=self.tkroot)
                self.tkroot.attributes('-topmost', False) # Reset topmost attribute

        
        if self.tkroot:
            self.tkroot.after(0, show) # Schedule the popup on the Tkinter thread
        else:
            logging.error("Tkinter root is not initialized and cannot popup message.")

    def get_active_window_info(self) -> Tuple[str, str]:
        """
        获取当前活动窗口的标题和可执行文件路径。
        返回 (窗口标题, 可执行文件路径) 或 ("", "") 如果发生错误。
        """
        try:
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return "", ""
            
            # Get window title
            window_title = win32gui.GetWindowText(hwnd)

            # Get process ID
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if not pid:
                return window_title, ""

            # Get executable path from process ID
            try:
                process = psutil.Process(pid)
                exe_path = process.exe()
                return window_title, exe_path
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
                logging.debug(f"Cannot get the information of process PID {pid}: {e}")
                return window_title, ""
        except Exception as e:
            logging.error(f"Error retrieving active window information: {e}")
            return "", ""

    def is_time_restricted(self, current_time: dtime, time_window_cfg: DictConfig) -> bool:
        """
        检查当前时间是否在给定的时间窗口内。
        处理跨午夜的时间窗口。
        """
        try:
            start_str = time_window_cfg.start_time
            end_str = time_window_cfg.end_time
            
            start_time = datetime.strptime(start_str, "%H:%M").time()
            end_time = datetime.strptime(end_str, "%H:%M").time()

            if start_time <= end_time:
                # 正常时间窗口 (例如, 09:00 - 17:00)
                return start_time <= current_time <= end_time
            else:
                # 时间窗口跨午夜 (例如, 23:00 - 06:00)
                return current_time >= start_time or current_time <= end_time
        except Exception as e:
            logging.error(f"Error while checking time restriction window '{time_window_cfg.name}': {e}")
            return False

    def is_app_allowed(self, app_path: str, mode: str, app_list: List[str]) -> bool:
        """
        根据模式 (黑名单/白名单) 和应用程序列表检查应用程序是否被允许。
        如果允许返回 True，如果受限返回 False。
        """
        if not app_path:
            return True # 如果无法获取应用程序路径，则假定允许

        app_name = os.path.basename(app_path).lower()
        
        allowed_apps_lower = [a.lower() for a in app_list]

        if mode == "blacklist":
            return app_name not in allowed_apps_lower
        elif mode == "whitelist":
            return app_name in allowed_apps_lower
        else:
            logging.warning(f"Unknown mode '{mode}'. Viewed as 'allowed'. ")
            return True # 未知模式，假定允许

    def loop(self):
        """Main monitoring loop, periodically checking active windows and time restrictions."""
        while True:
            now = datetime.now()
            current_time = now.time()
            
            restricted_active = False
            active_window_title, active_app_path = self.get_active_window_info()
            
            if active_app_path: # 仅在成功获取应用程序路径时进行检查
                for window_cfg in self.config.time_windows:
                    if self.is_time_restricted(current_time, window_cfg):
                        logging.debug(f"Current time {current_time} is within restricted time interval '{window_cfg.name}'.")
                        if not self.is_app_allowed(active_app_path, window_cfg.mode, window_cfg.app_list):
                            logging.info(f"Violation detected: Application '{os.path.basename(active_app_path)}' ({active_window_title}) is not allowed during time interval '{window_cfg.name}' (mode: {window_cfg.mode}).")
                            self._minimize_desktop()
                            app_name = os.path.basename(active_app_path)
                            current_time_str = now.strftime("%H:%M:%S")
                            time_range = f"{window_cfg.start_time} - {window_cfg.end_time}"
                            mode_label = "Whitelist" if window_cfg.mode == "whitelist" else "Blacklist"
                            message = (
                                f"{window_cfg.name}\n\n"
                                f"Current time: {current_time_str}\n"
                                f"Time range: {time_range}\n"
                                f"Window title: {active_window_title}\n"
                                f"Application: {app_name}\n"
                                f"Mode: {mode_label} :=> ({', '.join(window_cfg.app_list)})\n"
                            )
                            self._show_popup(message)
                            restricted_active = True
                            break # enough to find one restriction, no need to check other windows
            
            if not restricted_active:
                logging.debug(f"No active restriction or application is allowed. Current time: {current_time}, Active app: {os.path.basename(active_app_path) if active_app_path else 'N/A'}")

            time.sleep(self.config.check_interval)

@hydra.main(version_base=None, config_path=".", config_name="config")
def main(cfg: DictConfig):
    """
    Main function, started by Hydra.
    """
    logging.info("Sleeper application starting...")
    monitor = Sleeper(config=cfg)
    monitor.run()
    logging.info("Sleeper application stopped.")

if __name__ == "__main__":
    main()