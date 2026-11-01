"""Pengaturan, tema, dan helper konfigurasi Semangat Wallpaper."""

import json
import re
from pathlib import Path

CONFIG = Path.home() / ".semangat_wallpaper.json"
LOG = Path.home() / ".semangat_wallpaper.log"

POLL_SECONDS = 3
MIN_RESUME_SECONDS = 5

QUOTES = [
    "Deadline itu sementara, skill-mu permanen.",
    "Satu bug selesai, satu langkah lebih dekat.",
    "Capek itu wajar. Berhenti itu pilihan. Kamu pilih lanjut.",
    "Sedikit demi sedikit, asal jangan berhenti.",
    "Kode jelek hari ini jadi bahan belajar besok.",
    "Tarik napas, minum air, lanjut ngoding!",
    "Kamu sudah sejauh ini. Jangan menyerah sekarang.",
]

BG, CARD, TEXT, MUTED = "#eeece6", "#fbf9f4", "#2b303a", "#747781"
ACCENT, GREEN, RED, BLUE = "#b85d76", "#557f70", "#b65f63", "#5a729c"
BUTTON = "#637b9d"


def load_config():
    try:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        config = {}
    config.setdefault("url", "")
    config.setdefault("spotify_playlist", "")
    config.setdefault("sticker_image", "")
    config.setdefault("sticker_video", "")
    config.setdefault("sticker_sound", "")
    config.setdefault("sticker_size", 76)
    config.setdefault("sticker_x", -1)
    config.setdefault("sticker_y", 90)
    config.setdefault("volume", 0)
    config.setdefault("auto_resume", True)
    config.setdefault("auto_start", False)
    config.setdefault("keep_sticker_on_close", False)
    config.setdefault("positions", {})
    return config


def save_config(config):
    try:
        CONFIG.write_text(json.dumps(config, indent=2), encoding="utf-8")
    except OSError:
        pass


def video_key(source):
    match = re.search(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([\w-]{11})", source)
    if match:
        return match.group(1)
    return source


def fmt_time(seconds):
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"
