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
import uuid
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
wallpaper_requested = False


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
    desktop_id = windows_current_desktop_id() if OS == "Windows" else None
    desktop_switch_pending = False
    next_position_save = time.monotonic() + POLL_SECONDS
    while True:
        time.sleep(0.1 if OS == "Windows" else POLL_SECONDS)
        if OS == "Windows":
            current_desktop_id = windows_current_desktop_id()
            if current_desktop_id is not None:
                if desktop_id is not None and current_desktop_id != desktop_id:
                    desktop_switch_pending = True
                desktop_id = current_desktop_id
            if not wallpaper_requested:
                desktop_switch_pending = False
            elif desktop_switch_pending and proc is not None and proc.poll() is None:
                if run_bg(_move_wallpaper_to_current_desktop):
                    desktop_switch_pending = False
        if time.monotonic() >= next_position_save:
            if is_running():
                save_position()
            next_position_save = time.monotonic() + POLL_SECONDS


def windows_current_desktop_id():
    import winreg

    path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\VirtualDesktops"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
            desktop_id, _ = winreg.QueryValueEx(key, "CurrentVirtualDesktop")
    except OSError:
        return None
    return desktop_id


def windows_workerw():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
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


def windows_move_process_to_workerw(process_id):
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    worker = windows_workerw()
    if not worker:
        raise RuntimeError("layer desktop Windows tidak ditemukan.")

    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND, ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.EnumChildWindows.argtypes = [wintypes.HWND, callback_type, wintypes.LPARAM]
    user32.EnumChildWindows.restype = wintypes.BOOL
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
    user32.SetParent.restype = wintypes.HWND
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetClientRect.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL

    process_windows = []

    def window_process_id(hwnd):
        owner_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
        return owner_pid.value

    def add_process_window(hwnd):
        if window_process_id(hwnd) == process_id:
            process_windows.append(hwnd)

    @callback_type
    def child_callback(hwnd, _):
        add_process_window(hwnd)
        return True

    @callback_type
    def top_level_callback(hwnd, _):
        add_process_window(hwnd)
        user32.EnumChildWindows(hwnd, child_callback, 0)
        return True

    user32.EnumWindows(top_level_callback, 0)
    if not process_windows:
        raise RuntimeError("jendela video mpv tidak ditemukan di layer desktop.")

    video_window = next(
        (hwnd for hwnd in process_windows
         if user32.GetParent(hwnd) == worker
         and user32.GetWindowLongW(hwnd, -16) & 0x40000000),
        None,
    )
    if video_window:
        return
    video_window = next(
        (hwnd for hwnd in process_windows
         if user32.GetParent(hwnd)
         and window_process_id(user32.GetParent(hwnd)) != process_id
         and user32.GetWindowLongW(hwnd, -16) & 0x40000000),
        None,
    )
    if not video_window:
        raise RuntimeError("jendela video mpv tidak ditemukan di layer desktop.")

    ctypes.set_last_error(0)
    previous_parent = user32.SetParent(video_window, worker)
    if not previous_parent and ctypes.get_last_error():
        raise ctypes.WinError(ctypes.get_last_error())

    rect = wintypes.RECT()
    if not user32.GetClientRect(worker, ctypes.byref(rect)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not user32.SetWindowPos(
            video_window, None, 0, 0, rect.right, rect.bottom,
            0x0004 | 0x0010 | 0x0020):
        raise ctypes.WinError(ctypes.get_last_error())


def windows_pin_process_to_all_desktops(process_id):
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    windows = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND, ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.EnumChildWindows.argtypes = [wintypes.HWND, callback_type, wintypes.LPARAM]
    user32.EnumChildWindows.restype = wintypes.BOOL

    def belongs_to_process(hwnd):
        owner_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
        return owner_pid.value == process_id

    @callback_type
    def child_callback(hwnd, _):
        if belongs_to_process(hwnd):
            windows.append(hwnd)
        return True

    @callback_type
    def window_callback(hwnd, _):
        if belongs_to_process(hwnd):
            windows.append(hwnd)
        user32.EnumChildWindows(hwnd, child_callback, 0)
        return True

    user32.EnumWindows(window_callback, 0)
    if not windows:
        raise RuntimeError("jendela mpv tidak ditemukan.")

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_uint32),
            ("Data2", ctypes.c_uint16),
            ("Data3", ctypes.c_uint16),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    def guid(value):
        result = GUID()
        ctypes.memmove(ctypes.byref(result), uuid.UUID(value).bytes_le, 16)
        return result

    def method(pointer, index, result_type, *argument_types):
        table = ctypes.cast(
            pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
        ).contents
        return ctypes.WINFUNCTYPE(
            result_type, ctypes.c_void_p, *argument_types
        )(table[index])

    ole32 = ctypes.WinDLL("ole32")
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []
    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(GUID), ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p),
    ]
    ole32.CoCreateInstance.restype = ctypes.c_long
    initialized = ole32.CoInitializeEx(None, 2)
    if initialized < 0:
        raise RuntimeError(f"inisialisasi COM gagal (0x{initialized & 0xFFFFFFFF:08X}).")

    provider = ctypes.c_void_p()
    collection = ctypes.c_void_p()
    pinned_apps = ctypes.c_void_p()
    views = []

    def release(pointer):
        if pointer.value:
            method(pointer, 2, wintypes.ULONG)(pointer)
            pointer.value = None

    def query_service(service, interface):
        result = ctypes.c_void_p()
        query = method(provider, 3, ctypes.c_long, ctypes.POINTER(GUID),
                       ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
        status = query(provider, ctypes.byref(service), ctypes.byref(interface),
                       ctypes.byref(result))
        if status < 0:
            raise RuntimeError(f"layanan desktop virtual gagal (0x{status & 0xFFFFFFFF:08X}).")
        return result

    try:
        shell = guid("C2F03A33-21F5-47FA-B4BB-156362A2F239")
        service_provider = guid("6D5140C1-7436-11CE-8034-00AA006009FA")
        status = ole32.CoCreateInstance(
            ctypes.byref(shell), None, 4, ctypes.byref(service_provider),
            ctypes.byref(provider),
        )
        if status < 0:
            raise RuntimeError(f"layanan Windows Shell gagal (0x{status & 0xFFFFFFFF:08X}).")

        view_collection = guid("1841C6D7-4F9D-42C0-AF41-8747538F10E5")
        pinned_apps_service = guid("B5A399E7-1C87-46B8-88E9-FC5747B171BD")
        pinned_apps_interface = guid("4CE81583-1E4C-4632-A621-07A53543148F")
        collection = query_service(view_collection, view_collection)
        pinned_apps = query_service(pinned_apps_service, pinned_apps_interface)

        get_view = method(
            collection, 6, ctypes.c_long, wintypes.HWND,
            ctypes.POINTER(ctypes.c_void_p),
        )
        is_pinned = method(
            pinned_apps, 6, ctypes.c_long, ctypes.c_void_p,
            ctypes.POINTER(wintypes.BOOL),
        )
        pin_view = method(pinned_apps, 7, ctypes.c_long, ctypes.c_void_p)

        for hwnd in windows:
            view = ctypes.c_void_p()
            status = get_view(collection, hwnd, ctypes.byref(view))
            if status < 0 or not view.value:
                continue
            views.append(view)
            pinned = wintypes.BOOL()
            status = is_pinned(pinned_apps, view, ctypes.byref(pinned))
            if status >= 0 and pinned.value:
                return
            status = pin_view(pinned_apps, view)
            if status >= 0:
                return

        raise RuntimeError("Windows tidak mengenali jendela mpv sebagai jendela desktop.")
    finally:
        for view in views:
            release(view)
        release(pinned_apps)
        release(collection)
        release(provider)
        ole32.CoUninitialize()


def build_command(source, volume, start_at=0, max_height=None):
    mpv_path = find_mpv()
    if not mpv_path:
        raise RuntimeError("mpv tidak ditemukan. Install: scoop install extras/mpv")

    if max_height is not None and (
            isinstance(max_height, bool) or not isinstance(max_height, int) or max_height <= 0):
        raise ValueError("Resolusi maksimal video harus berupa angka positif.")

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
        f"--volume={volume}",
        f"--mute={'yes' if volume == 0 else 'no'}",
        f"--input-ipc-server={IPC_PATH}",
    ]
    if is_url:
        command.extend((
            "--cache=yes",
            "--demuxer-max-bytes=128MiB",
            "--demuxer-max-back-bytes=32MiB",
        ))
        command.append("--demuxer-readahead-secs=20")
        format_selector = (
            f"bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]"
            if max_height is not None else "bestvideo+bestaudio/best"
        )
        command.append(f"--ytdl-format={format_selector}")
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
    global proc, logf, wallpaper_requested
    if is_running():
        wallpaper_requested = True
        say("Wallpaper sudah menyala.")
        return
    if not cfg.get("url"):
        wallpaper_requested = False
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

    wallpaper_requested = True
    if OS != "Windows":
        try:
            os.remove(IPC_PATH)
        except OSError:
            pass

    say("Memuat video...")
    try:
        quality = cfg.get("video_quality", "best")
        max_height = None if quality == "best" else quality
        command = build_command(cfg["url"], cfg.get("volume", 0), start_at, max_height)
        logf = open(LOG, "w", encoding="utf-8")
        options = {"stdin": subprocess.DEVNULL, "stdout": logf, "stderr": logf}
        if OS == "Windows":
            options["creationflags"] = 0x08000000
        proc = subprocess.Popen(command, **options)
    except (RuntimeError, OSError, ValueError) as error:
        close_log()
        wallpaper_requested = False
        say(f"Gagal: {error}")
        return

    time.sleep(3)
    if proc.poll() is not None:
        code = proc.returncode
        proc = None
        close_log()
        wallpaper_requested = False
        tail = read_log_tail()
        hint = "" if shutil.which("yt-dlp") else " (yt-dlp tidak ditemukan: scoop install yt-dlp)"
        say(f"mpv langsung berhenti (kode {code}).{hint} {tail}")
        return

    wallpaper_requested = True
    events.put(("quote",))
    status = (f"Menyala, lanjut dari {fmt_time(start_at)}. Semangat!"
              if start_at else "Menyala dari awal. Semangat!")
    say(status)


def _stop():
    global proc, external_running, last_ipc_probe, wallpaper_requested
    wallpaper_requested = False
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
        say(f"Dimatikan. Posisi terakhir tersimpan: {fmt_time(position)}."
            if position >= MIN_RESUME_SECONDS else "Wallpaper dimatikan.")
    proc = None
    external_running = False
    last_ipc_probe = 0.0
    close_log()


def _move_wallpaper_to_current_desktop():
    current_proc = proc
    if not wallpaper_requested or current_proc is None or current_proc.poll() is not None:
        return
    try:
        windows_move_process_to_workerw(current_proc.pid)
    except (OSError, RuntimeError) as error:
        say(f"Gagal memindahkan wallpaper ke desktop aktif: {error}")


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
    if not action_lock.acquire(blocking=False):
        return False

    def wrapper():
        try:
            function(*args)
        finally:
            action_lock.release()

    try:
        threading.Thread(target=wrapper, daemon=True).start()
    except RuntimeError:
        action_lock.release()
        raise
    return True


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
