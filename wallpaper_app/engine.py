"""Kontrol mpv, posisi video, hotkey, dan startup Windows."""

import os
import platform
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from .config import LOG, MIN_RESUME_SECONDS, POLL_SECONDS, fmt_time, save_config as write_config, video_key

OS = platform.system()
HOTKEY = "<ctrl>+<alt>+w"
IPC_PATH = r"\\.\pipe\semangat_wallpaper" if OS == "Windows" else "/tmp/semangat_wallpaper.sock"

cfg = {}
proc = None
logf = None
events = queue.Queue()
action_lock = threading.Lock()
ipc_probe_lock = threading.Lock()
external_running = False
last_ipc_probe = 0.0


def configure(config):
    global cfg
    cfg = config


def say(text):
    events.put(("msg", text))


def is_running():
    global external_running, last_ipc_probe
    if proc is not None and proc.poll() is None:
        return True

    now = time.monotonic()
    if now - last_ipc_probe < 1:
        return external_running
    if not ipc_probe_lock.acquire(blocking=False):
        return external_running
    try:
        now = time.monotonic()
        if now - last_ipc_probe >= 1:
            last_ipc_probe = now
            external_running = isinstance(ipc_request(["get_property", "pause"], timeout=0.5), bool)
        return external_running
    finally:
        ipc_probe_lock.release()


def is_running_cached():
    global external_running, last_ipc_probe
    if proc is not None and proc.poll() is None:
        return True

    now = time.monotonic()
    if now - last_ipc_probe < 1:
        return external_running
    if not ipc_probe_lock.acquire(blocking=False):
        return external_running

    last_ipc_probe = now

    def probe():
        global external_running
        try:
            external_running = isinstance(
                ipc_request(["get_property", "pause"], timeout=0.5), bool
            )
        finally:
            ipc_probe_lock.release()

    threading.Thread(target=probe, daemon=True).start()
    return external_running


def find_mpv():
    home = Path.home()
    candidates = [
        home / "scoop" / "apps" / "mpv" / "current" / "mpv.exe",
        Path("C:/mpv/mpv.exe"), Path("D:/mpv/mpv.exe"),
        Path("C:/Program Files/mpv/mpv.exe"),
        Path("C:/Program Files (x86)/mpv/mpv.exe"),
        Path("C:/ProgramData/chocolatey/bin/mpv.exe"),
    ]
    installed = next((candidate for candidate in candidates if candidate.is_file()), None)
    return str(installed) if installed else (shutil.which("mpv.exe") or shutil.which("mpv"))


def fix_path():
    """Bantu mpv menemukan yt-dlp jika PATH terminal belum diperbarui."""
    home = Path.home()
    extra = [Path(sys.executable).parent,
             Path(__file__).resolve().parent.parent / ".venv" / "Scripts",
             home / "scoop" / "shims", home / "scoop" / "apps" / "mpv" / "current",
             home / "scoop" / "apps" / "yt-dlp" / "current"]
    mpv_path = find_mpv()
    if mpv_path:
        extra.append(Path(mpv_path).parent)
    current = os.environ.get("PATH", "").split(os.pathsep)
    for directory in extra:
        if directory.is_dir() and str(directory) not in current:
            os.environ["PATH"] += os.pathsep + str(directory)


def _ipc_raw(command):
    import json

    payload = (json.dumps({"command": command, "request_id": 1}) + "\n").encode()

    def read_reply(reader):
        while True:
            line = reader.readline()
            if not line:
                return None
            message = json.loads(line)
            if message.get("request_id") == 1:
                return message.get("data") if message.get("error") == "success" else None

    if OS == "Windows":
        with open(IPC_PATH, "r+b", buffering=0) as pipe:
            pipe.write(payload)
            return read_reply(pipe)
    address_family = getattr(socket, "AF_UNIX", None)
    if address_family is None:
        raise OSError("Unix domain socket tidak didukung pada platform ini.")
    with socket.socket(address_family, socket.SOCK_STREAM) as connection:
        connection.settimeout(1.5)
        connection.connect(IPC_PATH)
        connection.sendall(payload)
        return read_reply(connection.makefile("rb"))


def ipc_request(command, timeout=1.5):
    result = {}

    def worker():
        try:
            result["value"] = _ipc_raw(command)
        except (OSError, ValueError):
            pass

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout)
    return result.get("value")


def save_position():
    position = ipc_request(["get_property", "time-pos"])
    if isinstance(position, (int, float)) and cfg.get("url"):
        cfg["positions"][video_key(cfg["url"])] = round(position, 1)
        write_config(cfg)


def poller():
    while True:
        time.sleep(POLL_SECONDS)
        if is_running():
            save_position()


def windows_workerw():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.FindWindowW.restype = wintypes.HWND
    user32.FindWindowExW.restype = wintypes.HWND
    user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND,
                                     wintypes.LPCWSTR, wintypes.LPCWSTR]
    progman = user32.FindWindowW("Progman", None)
    result = ctypes.c_ulong()
    user32.SendMessageTimeoutW(progman, 0x052C, 0, 0, 0, 1000, ctypes.byref(result))
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_callback(hwnd, _):
        if user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None):
            worker = user32.FindWindowExW(None, hwnd, "WorkerW", None)
            if worker:
                found.append(worker)
        return True

    user32.EnumWindows(enum_callback, 0)
    if found:
        return found[0]
    return user32.FindWindowExW(progman, None, "WorkerW", None)


def windows_refresh_wallpaper():
    import ctypes
    ctypes.windll.user32.SystemParametersInfoW(20, 0, None, 2)


def build_command(source, volume, start_at=0):
    mpv_path = find_mpv()
    if not mpv_path:
        raise RuntimeError("mpv tidak ditemukan. Install: scoop install extras/mpv")

    is_url = source.lower().startswith(("http://", "https://"))
    if not is_url and not Path(source).is_file():
        raise RuntimeError("File video tidak ditemukan. Pilih file lokal atau masukkan URL video.")
    if is_url and "netflix.com" in source.lower():
        raise RuntimeError("Netflix tidak didukung karena video dilindungi DRM; aplikasi tidak melewati proteksi tersebut.")

    command = [
        mpv_path, source,
        "--loop-file=inf",
        "--no-osc", "--no-input-default-bindings", "--msg-level=all=error,ffmpeg=no",
        "--hwdec=auto-safe",
        "--framedrop=vo",
        "--cache=yes", "--demuxer-max-bytes=128MiB", "--demuxer-max-back-bytes=32MiB",
        f"--volume={volume}",
        f"--mute={'yes' if volume == 0 else 'no'}",
        f"--input-ipc-server={IPC_PATH}",
    ]
    if is_url:
        command.append("--demuxer-readahead-secs=20")
        command.append(
            "--ytdl-format="
            "bestvideo[height<=1080][fps<=30][vcodec^=avc1]+bestaudio/"
            "bestvideo[height<=1080][fps<=30][vcodec!*=av01]+bestaudio/"
            "bestvideo[height<=1080][vcodec!*=av01]+bestaudio/"
            "best[height<=1080]/best"
        )
    if start_at > 0:
        command.append(f"--start={start_at}")

    if OS == "Windows":
        hwnd = windows_workerw()
        if not hwnd:
            raise RuntimeError("Gagal menemukan layer desktop Windows.")
        command.append(f"--wid={int(hwnd)}")
    elif OS == "Linux":
        if not shutil.which("xwinwrap"):
            raise RuntimeError("xwinwrap belum terpasang (dibutuhkan di Linux/X11).")
        command = ["xwinwrap", "-fs", "-ni", "-s", "-nf", "-b", "-un", "--"] + command + ["--wid=WID"]
    else:
        raise RuntimeError(f"OS {OS} belum didukung.")
    return command


def close_log():
    global logf
    if logf:
        try:
            logf.close()
        except OSError:
            pass
        logf = None


def read_log_tail(count=2):
    try:
        lines = [line.strip() for line in LOG.read_text(errors="ignore").splitlines() if line.strip()]
        return " | ".join(lines[-count:])
    except OSError:
        return ""


def _start(resume=None):
    global proc, logf
    if is_running():
        say("Wallpaper sudah menyala.")
        return
    if not cfg.get("url"):
        say("Pilih file video atau isi URL video dulu.")
        return
    if resume is None:
        resume = cfg.get("auto_resume", True)

    key = video_key(cfg["url"])
    saved = cfg["positions"].get(key, 0)
    start_at = saved if resume and saved >= MIN_RESUME_SECONDS else 0
    if not resume:
        cfg["positions"][key] = 0
        write_config(cfg)

    if OS != "Windows":
        try:
            os.remove(IPC_PATH)
        except OSError:
            pass

    say("Memuat video...")
    try:
        command = build_command(cfg["url"], cfg.get("volume", 0), start_at)
        logf = open(LOG, "w", encoding="utf-8")
        options = {"stdin": subprocess.DEVNULL, "stdout": logf, "stderr": logf}
        if OS == "Windows":
            options["creationflags"] = 0x08000000
        proc = subprocess.Popen(command, **options)
    except (RuntimeError, OSError) as error:
        close_log()
        say(f"Gagal: {error}")
        return

    time.sleep(3)
    if proc.poll() is not None:
        code = proc.returncode
        proc = None
        close_log()
        tail = read_log_tail()
        hint = "" if shutil.which("yt-dlp") else " (yt-dlp tidak ditemukan: scoop install yt-dlp)"
        say(f"mpv langsung berhenti (kode {code}).{hint} {tail}")
        return

    events.put(("quote",))
    say(f"Menyala, lanjut dari {fmt_time(start_at)}. Semangat!" if start_at else "Menyala dari awal. Semangat!")


def _stop():
    global proc, external_running, last_ipc_probe
    if is_running():
        save_position()
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        else:
            ipc_request(["quit"], timeout=1)
        if OS == "Windows":
            time.sleep(0.3)
            windows_refresh_wallpaper()
        position = cfg["positions"].get(video_key(cfg["url"]), 0)
        say(f"Dimatikan. Posisi terakhir tersimpan: {fmt_time(position)}." if position >= MIN_RESUME_SECONDS
            else "Wallpaper dimatikan.")
    proc = None
    external_running = False
    last_ipc_probe = 0.0
    close_log()


def _restart_from_start():
    if is_running():
        _stop()
    _start(resume=False)


def _set_source(source):
    source = source.strip().strip('"')
    is_url = source.lower().startswith(("http://", "https://"))
    if is_url and "netflix.com" in source.lower():
        say("Netflix tidak didukung karena perlindungan DRM.")
        return
    if not is_url and not Path(source).is_file():
        say("Sumber tidak valid. Masukkan URL http(s) atau pilih file video yang ada.")
        return

    was_running = is_running()
    if was_running:
        _stop()
    cfg["url"] = source
    write_config(cfg)
    saved = cfg["positions"].get(video_key(source), 0)
    extra = f" (posisi tersimpan {fmt_time(saved)})" if saved >= MIN_RESUME_SECONDS else ""
    say("Sumber disimpan." + extra)
    if was_running:
        _start()


def _toggle():
    _stop() if is_running() else _start()


def run_bg(function, *args):
    """Jalankan aksi di thread terpisah supaya jendela tidak membeku."""
    def wrapper():
        if not action_lock.acquire(blocking=False):
            return
        try:
            function(*args)
        finally:
            action_lock.release()

    threading.Thread(target=wrapper, daemon=True).start()


def apply_volume(value):
    cfg["volume"] = value
    write_config(cfg)
    if is_running():
        ipc_request(["set_property", "mute", value == 0])
        ipc_request(["set_property", "volume", value])
        say(f"Volume diubah ke {value}.")


def set_auto_start(enabled):
    """Pasang/hapus launcher Startup untuk memulihkan wallpaper saat login Windows."""
    if OS != "Windows":
        raise RuntimeError("Autostart otomatis saat ini hanya disiapkan untuk Windows.")

    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("Folder Startup Windows tidak ditemukan.")
    startup_file = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "SemangatWallpaper.vbs"
    if not enabled:
        try:
            startup_file.unlink(missing_ok=True)
        except OSError as error:
            raise RuntimeError(f"Tidak bisa menghapus launcher Startup: {error}") from error
        return

    startup_file.parent.mkdir(parents=True, exist_ok=True)
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    executable = pythonw if pythonw.exists() else Path(sys.executable)
    script = Path(__file__).resolve().parent.parent / "semangat_wallpaper.py"
    command = f'"{executable}" "{script}"'
    escaped_command = command.replace('"', '""')
    startup_file.write_text(
        'Set WshShell = CreateObject("WScript.Shell")\r\n'
        f'WshShell.Run "{escaped_command}", 0, False\r\n',
        encoding="utf-16",
    )
