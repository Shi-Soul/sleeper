"""
写一个适合windows, 控制电脑使用时间的软件. 希望每天 0~6:00 限制, 只能使用白名单/黑名单软件. 希望方案尽可能简洁统一. 不要用windows自带的系统功能. 如果违规, 则minimize desktop并且弹窗提醒.

配置文件: 指定查询频率, 时间窗口, 黑名单模式还是白名单模式, 软件名单
实现方法: 
- 使用hydra读取yaml配置, 得到一列窗口( 每个列表中的element是一个时间窗口, 各有不同的模式和软件名单)

"""

import time
import json
import tkinter as tk
from tkinter import messagebox
import requests
import logging
import sys
import threading
from PIL import Image, ImageDraw
import pystray
import os
from toolz.curried import curry, reduceby, reduce, valmap, map, juxt
from itertools import compress
from typing import List, Tuple
from fn import F
import operator
import win32gui
import win32api
import socket
from datetime import datetime, timedelta

import pprint

DEBUG :bool = os.environ.get("DEBUG", 'False').lower()=="true"




def read_config(file_path):
    try:
        with open(file_path, "r") as file:
            return json.load(file)
    except Exception as e:
        logging.error(f"Error reading config file: {e}")
        sys.exit(1)


class Sleeper:
    def __init__(self, config_path="config.json"):
        if not os.path.exists("logs"):
            os.makedirs("logs")
        logging.basicConfig(
            filename=f'logs/{"debug_" if DEBUG else ""}sleeper_{datetime.now().strftime("%Y-%m-%d-%H")}.log',
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
        )
        self.config = read_config(config_path)


        # self.icon: pystray.Icon  # type: ignore
        # self.setup_icontray()

        threading.Thread(target=self.setup_tk, daemon=True).start()

    def setup_tk(self):
        self.tkroot = tk.Tk("sleeper")
        self.tkroot.withdraw()
        self.tkroot.mainloop()
        
    def run(self):
        thread = threading.Thread(target=self.loop, daemon=True)
        thread.start()
        self.icon.run()
        # thread = threading.Thread(target=self.icon.run, daemon=True)
        # thread.start()
        # self.loop()
    def exit_action(self):
        self.icon.stop()
        sys.exit(0)
        
    def _minimize_desktop(self):
        import win32com.client

        shell = win32com.client.Dispatch("Shell.Application")
        shell.MinimizeAll()

    def _show_popup(self, message):
        def show():
            messagebox.showwarning("Warning", message)

        self.tkroot.after(0, show)

    def loop(self):
        while True:
            now = datetime.now().astimezone()
            time.sleep(self.config["check_interval"])
            ...

def main():
    monitor = Sleeper(config_path="config_debug.json" if DEBUG else "config.json")
    monitor.run()


if __name__ == "__main__":
    main()
