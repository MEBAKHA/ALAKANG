#!/usr/bin/env python3
"""Launcher untuk aplikasi ALAKANG."""

import subprocess
import sys
from pathlib import Path


def use_project_venv():
    """Relaunch with the project venv so installed app dependencies are available."""
    if sys.platform != "win32":
        return
    venv_python = Path(__file__).resolve().parent / ".venv" / "Scripts" / "python.exe"
    if not venv_python.is_file():
        return
    if Path(sys.executable).resolve() == venv_python.resolve():
        return
    arguments = [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]]
    raise SystemExit(subprocess.call(arguments))


use_project_venv()

import tkinter as tk
import threading

from wallpaper_app import engine
from wallpaper_app.config import load_config
from wallpaper_app.gui import App


def main():
    if "--check-env" in sys.argv:
        import cv2
        import mediapipe
        import pyautogui
        print(f"Python: {sys.executable}")
        print(f"MediaPipe: {mediapipe.__version__}")
        print(f"OpenCV: {cv2.__version__}")
        print(f"PyAutoGUI: {pyautogui.__version__}")
        return

    if engine.OS == "Windows":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass

    engine.fix_path()
    engine.configure(load_config())
    threading.Thread(target=engine.poller, daemon=True).start()
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
