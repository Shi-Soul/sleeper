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
from datetime import datetime, timedelta
from typing import List, Tuple

# Windows specific imports
import win32gui
import win32api
import win32process
import win32con
import win32com.client # For MinimizeAll

# Configuration management
import hydra
from omegaconf import DictConfig, OmegaConf

# Process information
import psutil

# Set DEBUG flag from environment variable
DEBUG : bool = os.environ.get("DEBUG", 'False').lower() == "true"

class Sleeper:
    def __init__(self, config: DictConfig):
        # Setup logging
        if not os.path.exists("logs"):
            os.makedirs("logs")
        logging.basicConfig(
            filename=f'logs/{"debug_" if DEBUG else ""}sleeper_{datetime.now().strftime("%Y-%m-%d-%H")}.log',
            level=logging.DEBUG if DEBUG else logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
        )
        self.config = config
        logging.info(f"Loaded configuration: {OmegaConf.to_yaml(self.config)}")

        self.tkroot: tk.Tk = None # type: ignore
        self.icon: pystray.Icon = None # type: ignore

        # Setup system tray icon
        self.setup_icontray()
        
        # Setup Tkinter for popups in a separate thread
        threading.Thread(target=self.setup_tk, daemon=True).start()

    def setup_icontray(self):
        """Initializes the system tray icon."""
        # Generate a simple red circle icon
        width, height = 64, 64
        image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        dc = ImageDraw.Draw(image)
        dc.ellipse((0, 0, width, height), fill=(200, 50, 30, 255)) # Red circle

        menu = (
            pystray.MenuItem('退出', self.exit_action),
        )
        self.icon = pystray.Icon("sleeper_app", image, "电脑使用限制", menu)
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

    def exit_action(self, icon: pystray.Icon, item: pystray.MenuItem):
        """Handles the exit action from the system tray menu."""
        logging.info("Exiting application via system tray.")
        if self.icon:
            self.icon.stop() # Stop the pystray icon loop
        if self.tkroot:
            self.tkroot.quit() # Properly quit the Tkinter mainloop
        sys.exit(0)
        
    def _minimize_desktop(self):
        """Minimizes all open windows."""
        try:
            import win32com.client
            shell = win32com.client.Dispatch("Shell.Application")
            shell.MinimizeAll()
            logging.info("所有窗口已最小化。")
        except Exception as e:
            logging.error(f"最小化桌面时出错: {e}")

    def _show_popup(self, message: str):
        """Shows a Tkinter warning popup."""
        def show():
            # Ensure the popup appears on top of other windows
            if self.tkroot:
                self.tkroot.attributes('-topmost', True)
                messagebox.showwarning("警告", message, parent=self.tkroot)
                self.tkroot.attributes('-topmost', False) # Reset topmost attribute
            logging.warning(f"弹出警告: {message}")
        
        if self.tkroot:
            self.tkroot.after(0, show) # Schedule the popup on the Tkinter thread
        else:
            logging.error("Tkinter root 未初始化，无法显示弹窗。")

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
                logging.debug(f"无法获取 PID {pid} 的进程信息: {e}")
                return window_title, ""
        except Exception as e:
            logging.error(f"获取活动窗口信息时出错: {e}")
            return "", ""

    def is_time_restricted(self, current_time: datetime.time, time_window_cfg: DictConfig) -> bool:
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
            logging.error(f"检查时间限制窗口 '{time_window_cfg.name}' 时出错: {e}")
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
            logging.warning(f"未知模式 '{mode}'。默认允许。")
            return True # 未知模式，假定允许

    def loop(self):
        """主监控循环，定期检查活动窗口和时间限制。"""
        while True:
            now = datetime.now()
            current_time = now.time()
            
            restricted_active = False
            active_window_title, active_app_path = self.get_active_window_info()
            
            if active_app_path: # 仅在成功获取应用程序路径时进行检查
                for window_cfg in self.config.time_windows:
                    if self.is_time_restricted(current_time, window_cfg):
                        logging.debug(f"当前时间 {current_time} 在限制窗口 '{window_cfg.name}' 内。")
                        if not self.is_app_allowed(active_app_path, window_cfg.mode, window_cfg.app_list):
                            logging.info(f"检测到违规: 应用程序 '{os.path.basename(active_app_path)}' ({active_window_title}) 在 '{window_cfg.name}' ({window_cfg.mode} 模式) 期间不被允许。")
                            self._minimize_desktop()
                            self._show_popup(f"应用程序 '{os.path.basename(active_app_path)}' 在当前时间段内被限制使用！")
                            restricted_active = True
                            break # 找到一个限制就足够了，无需检查其他窗口
            
            if not restricted_active:
                logging.debug(f"无活动限制或应用程序被允许。当前时间: {current_time}, 活动应用: {os.path.basename(active_app_path) if active_app_path else 'N/A'}")

            time.sleep(self.config.check_interval)

@hydra.main(version_base=None, config_path=".", config_name="config")
def main(cfg: DictConfig):
    """
    主函数，由 Hydra 启动。
    """
    logging.info("Sleeper application starting...")
    monitor = Sleeper(config=cfg)
    monitor.run()
    logging.info("Sleeper application stopped.")

if __name__ == "__main__":
    main()