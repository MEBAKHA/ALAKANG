"""Antarmuka Tkinter ALAKANG."""

import queue
import random
import threading
import tkinter as tk
import os
import platform
import re
import shutil
import sys
import subprocess
import webbrowser
from datetime import datetime
from io import BytesIO
from pathlib import Path
from tkinter import filedialog, simpledialog
from urllib.parse import quote_plus, urlsplit
from urllib.request import Request, urlopen

from PIL import Image, ImageOps, ImageTk, UnidentifiedImageError

from . import engine
from .config import ACCENT, BG, BLUE, BUTTON, CARD, GREEN, MUTED, QUOTES, RED, TEXT, fmt_time, save_config, video_key
from .games import GameHub
from .scroll_detector import HandScrollDetector


class App:
    def __init__(self, root):
        self.root = root
        self.spotify_sticker = None
        self.spotify_widget = None
        self.sticker_video_proc = None
        self.sticker_video_frame = None
        self.sticker_photo = None
        self.sticker_expanded_photo = None
        self.sticker_original = None
        self._layout_save_job = None
        self._edit_mode = False
        self.scroll_detector = HandScrollDetector()
        self._scroll_camera_active = False
        self._scroll_verified = False
        self._scroll_active = False
        self._camera_scan_in_progress = False
        self.scroll_preview_photo = None
        self._button_colors = {}
        self._button_animation_jobs = {}
        self._resize_wrap_job = None
        try:
            self.sticker_size = max(56, min(400, int(engine.cfg.get("sticker_size", 76))))
            self.sticker_x = int(engine.cfg.get("sticker_x", -1))
            self.sticker_y = max(0, int(engine.cfg.get("sticker_y", 90)))
        except (TypeError, ValueError):
            self.sticker_size, self.sticker_x, self.sticker_y = 76, -1, 90
        root.title("ALAKANG")
        root.configure(bg=BG)
        root.resizable(True, True)
        root.minsize(400, 540)
        root.geometry("520x740")

        self.canvas = tk.Canvas(root, bg=BG, highlightthickness=0)
        scrollbar = tk.Scrollbar(root, orient="vertical", command=self.canvas.yview,
                     bg=CARD, troughcolor=BG, activebackground=ACCENT)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.content = tk.Frame(self.canvas, bg=BG)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", self.update_scroll_region)
        self.canvas.bind("<Configure>", self.resize_scroll_content)
        self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)
        self.canvas.bind_all("<Button-4>", self.on_mousewheel_linux)
        self.canvas.bind_all("<Button-5>", self.on_mousewheel_linux)

        shell = tk.Frame(self.content, bg=BG, padx=16, pady=12)
        shell.pack(fill="both", expand=True)

        hero = tk.Frame(shell, bg=CARD, padx=15, pady=14)
        hero.pack(fill="x", pady=(0, 7))
        identity = tk.Frame(hero, bg=CARD)
        hero.grid_columnconfigure(0, weight=1)
        identity.grid(row=0, column=0, sticky="nsew")
        tk.Label(identity, text="DESKTOP COMPANION", bg=CARD, fg=ACCENT,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 4))
        tk.Label(identity, text="ALAKANG", bg=CARD, fg=TEXT,
                 font=("Segoe UI", 17, "bold"), justify="left").pack(anchor="w")
        tk.Label(identity, text="CODE  ·  BRITPOP  ·  ANIME  ·  JKT48  ·  GAME",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 7, "bold"),
                 wraplength=190, justify="left").pack(anchor="w", pady=(6, 0))

        clock_panel = tk.Frame(hero, bg=BG, padx=11, pady=10)
        clock_panel.grid(row=0, column=1, sticky="e", padx=(8, 0))
        self.date_label = tk.Label(
            clock_panel, text="", bg=BG, fg=MUTED, font=("Segoe UI", 8, "bold"),
            wraplength=132, justify="center")
        self.date_label.pack(fill="x")
        self.clock_label = tk.Label(
            clock_panel, text="--:--", bg=BG, fg=TEXT,
            font=("Segoe UI", 25, "bold"))
        self.clock_label.pack(pady=(1, 0))

        self.quote = tk.Label(shell, text=random.choice(QUOTES), bg=BG, fg=ACCENT,
                              font=("Segoe UI", 9, "italic"), wraplength=440)
        self.quote.pack(pady=(2, 10))

        status = tk.Frame(shell, bg=CARD, padx=12, pady=10)
        status.pack(fill="x", pady=(0, 10))
        self.dot = tk.Label(status, text="●", bg=CARD, fg=RED, font=("Segoe UI", 14))
        self.dot.pack(side="left", padx=(0, 7))
        self.state = tk.Label(status, text="Mati", bg=CARD, fg=TEXT,
                              font=("Segoe UI", 11, "bold"))
        self.state.pack(side="left")
        self.pos = tk.Label(status, text="", bg=CARD, fg=MUTED, font=("Segoe UI", 9))
        self.pos.pack(side="right")

        source_card = self.section(shell, "SUMBER VIDEO")
        self.url_var = tk.StringVar(value=engine.cfg.get("url", ""))
        self.entry = tk.Entry(source_card, textvariable=self.url_var, bg=BG, fg=TEXT,
                              insertbackground=TEXT, relief="flat", font=("Segoe UI", 10))
        self.entry.pack(fill="x", ipady=8, pady=(0, 8))
        source_actions = tk.Frame(source_card, bg=CARD)
        source_actions.pack(fill="x")
        for column in range(3):
            source_actions.grid_columnconfigure(column, weight=1, uniform="source-actions")
        self.btn(source_actions, "📋 Tempel", self.paste, BG, small=True).grid(
            row=0, column=0, sticky="ew", padx=(0, 4))
        self.btn(source_actions, "📁 Pilih file", self.choose_file, BG, small=True).grid(
            row=0, column=1, sticky="ew", padx=4)
        self.btn(source_actions, "💾 Simpan", self.save_source, BLUE, small=True).grid(
            row=0, column=2, sticky="ew", padx=(4, 0))

        playback_card = self.section(shell, "KONTROL WALLPAPER")
        self.main_btn = self.btn(playback_card, "▶  Nyalakan wallpaper", self.on_toggle,
                                 ACCENT, big=True)
        self.main_btn.pack(fill="x", pady=(0, 8))
        playback_actions = tk.Frame(playback_card, bg=CARD)
        playback_actions.pack(fill="x")
        for column in range(2):
            playback_actions.grid_columnconfigure(column, weight=1, uniform="playback-actions")
        self.btn(playback_actions, "⏯  Lanjutkan", lambda: engine.run_bg(engine._start, True), BG
                 ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.btn(playback_actions, "⏮  Mulai dari awal", lambda: engine.run_bg(engine._restart_from_start), BG
                 ).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        scroll_card = self.section(shell, "SCROLL ACTIVE • KONTROL DENGAN TANGAN")
        camera_row = tk.Frame(scroll_card, bg=CARD)
        camera_row.pack(fill="x", pady=(0, 7))
        tk.Label(camera_row, text="Kamera", bg=CARD, fg=TEXT,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 7))
        self.camera_var = tk.StringVar(value="Kamera 0")
        self.camera_choices = {"Kamera 0": 0}
        self.camera_var.trace_add("write", self.on_camera_selection)
        self.camera_menu = tk.OptionMenu(camera_row, self.camera_var, "Kamera 0")
        self.camera_menu.configure(
            bg=BG, fg=TEXT, activebackground=BLUE, activeforeground="#ffffff",
            relief="flat", bd=0, highlightthickness=0, font=("Segoe UI", 9))
        self.camera_menu["menu"].configure(bg=CARD, fg=TEXT, activebackground=BLUE,
                                           activeforeground="#ffffff")
        self.camera_menu.pack(side="left", fill="x", expand=True)
        self.camera_refresh_btn = self.btn(
            camera_row, "↻ Cari", self.refresh_camera_list, BG, small=True)
        self.camera_refresh_btn.pack(side="left", padx=(6, 0))
        self.scroll_preview = tk.Label(
            scroll_card, text="Kamera belum aktif", bg=BG, fg=MUTED,
            font=("Segoe UI", 9), width=50, height=18)
        self.scroll_preview.pack(fill="x", pady=(0, 8))
        self.scroll_status = tk.Label(
            scroll_card, text="Mati — aktifkan untuk mulai mendeteksi tangan.",
            bg=CARD, fg=MUTED, font=("Segoe UI", 9), wraplength=400, justify="left")
        self.scroll_status.pack(anchor="w", pady=(0, 7))
        self.scroll_verify_btn = self.btn(
            scroll_card, "📷 Verifikasi kamera & tangan", self.toggle_scroll_camera,
            BLUE, small=True)
        self.scroll_verify_btn.pack(fill="x", pady=(0, 5))
        self.scroll_btn = self.btn(
            scroll_card, "🔒 Verifikasi kamera dulu", self.toggle_hand_scroll,
            BLUE, small=True)
        self.scroll_btn.config(state="disabled")
        self.scroll_btn.pack(fill="x")
        tk.Label(
            scroll_card,
              text="Verifikasi kamera, lalu aktifkan scroll. ☝️ Angkat telunjuk, lipat jari "
                  "lain, lalu gerakkan ujung telunjuk naik/turun untuk scroll. 🤚 Buka telapak "
                 "untuk berhenti. Letakkan pointer di halaman yang mau discroll. "
                 "Kamera diproses lokal saja.",
            bg=CARD, fg=MUTED, font=("Segoe UI", 8), wraplength=400,
            justify="left").pack(anchor="w", pady=(6, 0))

        settings_card = self.section(shell, "PREFERENSI")
        self.resume_var = tk.BooleanVar(value=engine.cfg.get("auto_resume", True))
        tk.Checkbutton(settings_card, text="Lanjut otomatis dari posisi terakhir",
                       variable=self.resume_var, command=self.on_resume, bg=CARD, fg=TEXT,
                       selectcolor=BG, activebackground=CARD, activeforeground=TEXT,
                       font=("Segoe UI", 9)).pack(anchor="w")
        self.startup_var = tk.BooleanVar(value=engine.cfg.get("auto_start", False))
        self.startup_check = tk.Checkbutton(
            settings_card, text="Nyalakan wallpaper otomatis saat masuk Windows",
            variable=self.startup_var, command=self.on_startup, bg=CARD, fg=TEXT,
            selectcolor=BG, activebackground=CARD, activeforeground=TEXT,
            font=("Segoe UI", 9))
        self.startup_check.pack(anchor="w", pady=(3, 8))
        if engine.OS != "Windows":
            self.startup_check.configure(state="disabled")
        tk.Label(settings_card, text="Saat laptop dimatikan, video ikut berhenti. Wallpaper akan menyala kembali setelah Windows aktif dan login. File video lokal dapat diputar tanpa Wi-Fi.",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 8), wraplength=400,
                 justify="left").pack(anchor="w", pady=(0, 8))
        self.keep_sticker_var = tk.BooleanVar(
            value=engine.cfg.get("keep_sticker_on_close", False))
        tk.Checkbutton(
            settings_card, text="Biarkan stiker hidup saat panel ditutup",
            variable=self.keep_sticker_var, command=self.on_keep_sticker_on_close,
            bg=CARD, fg=TEXT, selectcolor=BG, activebackground=CARD,
            activeforeground=TEXT, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 8))

        volume_row = tk.Frame(settings_card, bg=CARD)
        volume_row.pack(fill="x")
        tk.Label(volume_row, text="🔊 Volume", bg=CARD, fg=TEXT,
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        self.vol_label = tk.Label(volume_row, text=str(engine.cfg.get("volume", 0)), bg=CARD,
                                  fg=ACCENT, font=("Segoe UI", 9, "bold"))
        self.vol_label.pack(side="right")
        self.vol = tk.Scale(settings_card, from_=0, to=100, orient="horizontal", showvalue=False,
                            bg=CARD, fg=TEXT, troughcolor=BG, highlightthickness=0,
                            activebackground=ACCENT, command=self.on_volume_drag, bd=0)
        self.vol.set(engine.cfg.get("volume", 0))
        self.vol.pack(fill="x", pady=(0, 0))
        self.vol.bind("<ButtonRelease-1>", self.on_volume_release)

        spotify_card = self.section(shell, "SPOTIFY")
        self.spotify_var = tk.StringVar(value=engine.cfg.get("spotify_playlist", ""))
        tk.Entry(spotify_card, textvariable=self.spotify_var, bg=BG, fg=TEXT,
                 insertbackground=TEXT, relief="flat", font=("Segoe UI", 10)
                 ).pack(fill="x", ipady=8, pady=(0, 8))
        spotify_actions = tk.Frame(spotify_card, bg=CARD)
        spotify_actions.pack(fill="x")
        for column in range(3):
            spotify_actions.grid_columnconfigure(column, weight=1, uniform="spotify-actions")
        self.btn(spotify_actions, "💾 Simpan", self.save_spotify_playlist, BG,
                 small=True).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.btn(spotify_actions, "🎵 Buka", self.open_spotify_playlist, GREEN,
                 small=True).grid(row=0, column=1, sticky="ew", padx=4)
        self.btn(spotify_actions, "🎵 Mini Spotify", self.toggle_spotify_widget, BG,
                 small=True).grid(row=0, column=2, sticky="ew", padx=(4, 0))
        tk.Label(spotify_card, text="Tautan dibuka di aplikasi Spotify; tidak memakai API.",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(7, 0))

        sticker_card = self.section(shell, "STIKER PELIHARAAN")
        self.sticker_url_var = tk.StringVar()
        tk.Entry(sticker_card, textvariable=self.sticker_url_var, bg=BG, fg=TEXT,
             insertbackground=TEXT, relief="flat", font=("Segoe UI", 9)
             ).pack(fill="x", ipady=7, pady=(0, 7))
        sticker_actions = tk.Frame(sticker_card, bg=CARD)
        sticker_actions.pack(fill="x")
        for column in range(3):
            sticker_actions.grid_columnconfigure(column, weight=1, uniform="sticker-actions")
        self.btn(sticker_actions, "📁 Pilih foto", self.choose_sticker_image, BG,
                 small=True).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.btn(sticker_actions, "🌐 Unduh foto", self.download_sticker_image, BLUE,
                 small=True).grid(row=0, column=1, sticky="ew", padx=4)
        self.btn(sticker_actions, "🎞 Pilih video", self.choose_sticker_video, GREEN,
                 small=True).grid(row=0, column=2, sticky="ew", padx=(4, 0))
        self.btn(sticker_card, "🔎 Cari gambar di Google", self.search_google_images, BG,
             small=True).pack(anchor="w", pady=(6, 0))
        self.btn(sticker_card, "🐾 Tampilkan / sembunyikan peliharaan",
             self.toggle_spotify_sticker, GREEN, small=True).pack(fill="x", pady=(7, 0))
        tk.Label(sticker_card, text="Untuk Google: cari gambar, buka gambar aslinya, lalu tempel URL langsungnya di atas.",
             bg=CARD, fg=MUTED, font=("Segoe UI", 8), wraplength=400,
             justify="left").pack(anchor="w", pady=(5, 0))
        tk.Label(sticker_card, text="PNG transparan mengikuti siluetnya di Windows. Stiker video memakai file lokal dan diputar berulang tanpa suara.",
             bg=CARD, fg=MUTED, font=("Segoe UI", 8), wraplength=400,
             justify="left").pack(anchor="w", pady=(4, 0))

        sound_row = tk.Frame(sticker_card, bg=CARD)
        sound_row.pack(fill="x", pady=(8, 0))
        self.btn(sound_row, "🔊 Pilih suara klik (WAV/MP3)", self.choose_sticker_sound, BG,
                 small=True).pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.btn(sound_row, "▶ Tes", self.play_sticker_sound, GREEN,
                 small=True).pack(side="left", padx=(4, 0))
        self.sound_label = tk.Label(
            sticker_card, text=self.sticker_sound_name(), bg=CARD, fg=MUTED,
            font=("Segoe UI", 8), wraplength=400, justify="left")
        self.sound_label.pack(anchor="w", pady=(4, 0))

        layout_card = self.section(shell, "UKURAN & TATA LETAK STIKER")
        layout_row = tk.Frame(layout_card, bg=CARD)
        layout_row.pack(fill="x")
        tk.Label(layout_row, text="Ukuran", bg=CARD, fg=TEXT,
                 font=("Segoe UI", 9, "bold")).pack(side="left")
        self.sticker_size_label = tk.Label(layout_row, text=f"{self.sticker_size} px",
                                           bg=CARD, fg=ACCENT,
                                           font=("Segoe UI", 9, "bold"))
        self.sticker_size_label.pack(side="right")
        self.sticker_size_scale = tk.Scale(
            layout_card, from_=56, to=400, orient="horizontal", showvalue=False,
            bg=CARD, fg=TEXT, troughcolor=BG, highlightthickness=0,
            activebackground=ACCENT, command=self.on_sticker_size, bd=0)
        self.sticker_size_scale.set(self.sticker_size)
        self.sticker_size_scale.pack(fill="x")
        self.sticker_size_scale.bind("<ButtonRelease-1>", self.save_sticker_size)
        self.btn(layout_card, "🖱 Atur posisi & ukuran langsung", self.begin_sticker_edit,
                 BLUE, small=True).pack(fill="x", pady=(7, 0))
        tk.Label(layout_card, text="Stiker diam di posisi terakhir. Untuk memindahkan atau mengubah ukurannya, pilih Atur posisi & ukuran langsung, lalu tekan Terima.",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 8), wraplength=400,
                 justify="left").pack(anchor="w", pady=(3, 0))

        self.games = GameHub(root, shell)

        self.msg = tk.Label(shell, text="Siap. Tambahkan URL atau pilih file video.", bg=BG, fg=MUTED,
                            font=("Segoe UI", 9), wraplength=440, justify="left", anchor="w")
        self.msg.pack(fill="x", pady=(3, 5))
        tk.Label(shell, text="Hotkey: Ctrl+Alt+W  •  Video berulang otomatis",
                 bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(pady=(2, 4))

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.bind_all("<Button-3>", self.on_sticker_context_menu)
        self.listener = self.setup_hotkey()
        self.update_clock()
        self.root.after(100, self.poll_hand_scroll)
        saved_video = engine.cfg.get("sticker_video", "")
        if isinstance(saved_video, str) and saved_video.lower().startswith(("http://", "https://")):
            engine.cfg["sticker_video"] = ""
            save_config(engine.cfg)
            engine.say("URL video online dihapus; pilih file lokal untuk stiker video.")
        saved_image = engine.cfg.get("sticker_image", "")
        if saved_image and os.path.isfile(saved_image):
            try:
                with Image.open(saved_image) as image:
                    self.sticker_original = image.convert("RGBA").copy()
            except (OSError, UnidentifiedImageError):
                engine.cfg["sticker_image"] = ""
                save_config(engine.cfg)
        if self.sticker_original or engine.cfg.get("sticker_video"):
            self.show_spotify_sticker()
        if engine.cfg.get("spotify_playlist"):
            self.show_spotify_widget()
        self.root.after(200, self.refresh_camera_list)
        self.tick()
        if engine.OS == "Windows" and engine.cfg.get("auto_start"):
            self.root.after(5000, self.resume_wallpaper_on_startup)

    def section(self, parent, title):
        card = tk.Frame(parent, bg=CARD, padx=14, pady=11)
        card.pack(fill="x", pady=5)
        tk.Label(card, text=title, bg=CARD, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 8))
        return card

    def btn(self, parent, text, command, bg, big=False, small=False):
        if bg == BG:
            bg = BUTTON
        button = tk.Button(
            parent, text=text, command=command, bg=bg, fg="#ffffff",
            activebackground=self.blend_color(bg, "#000000", 0.12),
            activeforeground="#ffffff", relief="flat", bd=0, cursor="hand2",
            font=("Segoe UI", 13 if big else (9 if small else 10), "bold"),
            padx=10, pady=12 if big else (6 if small else 9))
        self._button_colors[button] = bg
        button.bind("<Enter>", self.on_button_enter)
        button.bind("<Leave>", self.on_button_leave)
        button.bind("<ButtonPress-1>", self.on_button_press)
        button.bind("<ButtonRelease-1>", self.on_button_release)
        return button

    @staticmethod
    def blend_color(source, target, amount):
        source_rgb = tuple(int(source[index:index + 2], 16) for index in (1, 3, 5))
        target_rgb = tuple(int(target[index:index + 2], 16) for index in (1, 3, 5))
        blended = tuple(
            round(first + (second - first) * amount)
            for first, second in zip(source_rgb, target_rgb)
        )
        return "#{:02x}{:02x}{:02x}".format(*blended)

    def set_button_color(self, button, color):
        previous_color = self._button_colors.get(button)
        self._button_colors[button] = color
        button.configure(
            bg=color, activebackground=self.blend_color(color, "#000000", 0.12))
        if previous_color != color and self.pointer_over_button(button):
            self.animate_button(button, self.blend_color(color, "#ffffff", 0.1))

    @staticmethod
    def pointer_over_button(button):
        x, y = button.winfo_pointerx(), button.winfo_pointery()
        left, top = button.winfo_rootx(), button.winfo_rooty()
        return (left <= x < left + button.winfo_width()
                and top <= y < top + button.winfo_height())

    def animate_button(self, button, target):
        job = self._button_animation_jobs.pop(button, None)
        if job is not None:
            self.root.after_cancel(job)
        start = button.cget("bg")

        def animate(step):
            if not button.winfo_exists():
                self._button_animation_jobs.pop(button, None)
                return
            amount = step / 4
            button.configure(bg=self.blend_color(start, target, amount))
            if step < 4:
                self._button_animation_jobs[button] = self.root.after(
                    14, lambda: animate(step + 1))
            else:
                self._button_animation_jobs.pop(button, None)

        animate(1)

    def on_button_enter(self, event):
        button = event.widget
        if str(button.cget("state")) != "disabled":
            color = self._button_colors.get(button, button.cget("bg"))
            self.animate_button(button, self.blend_color(color, "#ffffff", 0.1))

    def on_button_leave(self, event):
        button = event.widget
        if str(button.cget("state")) != "disabled":
            self.animate_button(button, self._button_colors.get(button, button.cget("bg")))

    def on_button_press(self, event):
        button = event.widget
        if str(button.cget("state")) != "disabled":
            color = self._button_colors.get(button, button.cget("bg"))
            self.animate_button(button, self.blend_color(color, "#000000", 0.14))

    def on_button_release(self, event):
        button = event.widget
        if str(button.cget("state")) != "disabled":
            self.root.after_idle(lambda: self.restore_button_after_press(button))

    def restore_button_after_press(self, button):
        if not button.winfo_exists():
            return
        color = self._button_colors.get(button, button.cget("bg"))
        if self.pointer_over_button(button):
            color = self.blend_color(color, "#ffffff", 0.1)
        self.animate_button(button, color)

    def update_clock(self):
        now = datetime.now()
        weekdays = (
            "Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")
        months = (
            "Januari", "Februari", "Maret", "April", "Mei", "Juni",
            "Juli", "Agustus", "September", "Oktober", "November", "Desember")
        self.date_label.config(
            text=f"{weekdays[now.weekday()]}\n"
                 f"{now.day} {months[now.month - 1]} {now.year}")
        self.clock_label.config(text=now.strftime("%H:%M"))
        self.root.after(1000, self.update_clock)

    def update_scroll_region(self, _event=None):
        del _event
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def resize_scroll_content(self, event):
        self.canvas.itemconfigure(self.canvas_window, width=event.width)
        if self._resize_wrap_job is not None:
            self.root.after_cancel(self._resize_wrap_job)
        self._resize_wrap_job = self.root.after(
            70, lambda width=event.width: self.update_wrap_lengths(width))

    def update_wrap_lengths(self, width):
        self._resize_wrap_job = None
        wraplength = max(220, width - 48)
        self.date_label.configure(wraplength=max(96, min(132, width // 3)))
        pending = [self.content]
        while pending:
            parent = pending.pop()
            for child in parent.winfo_children():
                pending.append(child)
                if (child is not self.date_label and child.winfo_class() == "Label"
                        and int(child.cget("wraplength")) > 0):
                    child.configure(wraplength=wraplength)

    def on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def on_mousewheel_linux(self, event):
        self.canvas.yview_scroll(-1 if event.num == 4 else 1, "units")
        return "break"

    def paste(self):
        try:
            self.url_var.set(self.root.clipboard_get().strip())
        except tk.TclError:
            engine.say("Clipboard kosong.")

    def choose_file(self):
        filename = filedialog.askopenfilename(
            parent=self.root,
            title="Pilih video lokal",
            filetypes=[("Video", "*.mp4 *.mkv *.webm *.mov *.avi"), ("Semua file", "*.*")],
        )
        if filename:
            self.url_var.set(filename)
            engine.run_bg(engine._set_source, filename)

    def save_source(self):
        engine.run_bg(engine._set_source, self.url_var.get())

    def on_toggle(self):
        if engine.is_running():
            if engine.cfg.get("auto_start"):
                try:
                    engine.set_auto_start(False)
                except (OSError, RuntimeError) as error:
                    engine.say(f"Launcher otomatis gagal dinonaktifkan: {error}")
                engine.cfg["auto_start"] = False
                save_config(engine.cfg)
                self.startup_var.set(False)
            engine.run_bg(engine._stop)
        else:
            engine.run_bg(engine._start)

    def resume_wallpaper_on_startup(self):
        if engine.cfg.get("auto_start"):
            engine.run_bg(engine._start)

    def toggle_scroll_camera(self):
        if self._scroll_camera_active:
            self._scroll_camera_active = False
            self._scroll_verified = False
            self._scroll_active = False
            self.scroll_detector.stop()
            self.scroll_verify_btn.config(text="📷 Verifikasi kamera & tangan")
            self.set_button_color(self.scroll_verify_btn, BLUE)
            self.camera_menu.config(state="normal")
            self.camera_refresh_btn.config(state="normal")
            self.scroll_btn.config(text="🔒 Verifikasi kamera dulu", state="disabled")
            self.set_button_color(self.scroll_btn, BLUE)
            self.scroll_status.config(text="Kamera mati. Verifikasi ulang sebelum scroll.", fg=MUTED)
            self.scroll_preview.configure(width=50, height=18)
            self.scroll_preview.config(image="", text="Kamera belum aktif")
            self.scroll_preview_photo = None
            return

        self._scroll_camera_active = True
        self._scroll_verified = False
        camera_index = self.camera_choices.get(self.camera_var.get())
        if camera_index is None:
            self._scroll_camera_active = False
            self.scroll_status.config(text="Tidak ada kamera terpilih. Tekan Cari untuk memindai webcam.",
                                      fg=RED)
            return
        self.camera_menu.config(state="disabled")
        self.camera_refresh_btn.config(state="disabled")
        preview_width = max(220, min(400, self.canvas.winfo_width() - 80))
        self.scroll_preview.configure(
            width=preview_width, height=preview_width * 3 // 4)
        self.scroll_verify_btn.config(text="⏹  Matikan kamera")
        self.set_button_color(self.scroll_verify_btn, RED)
        self.scroll_btn.config(text="🔒 Menunggu verifikasi...", state="disabled")
        self.scroll_status.config(
            text="Verifikasi kamera: tunjukkan telapak terbuka 🤚, utuh, dan menghadap kamera. "
                 "Tahan sampai struktur tangan selesai diperiksa.",
            fg=ACCENT)
        self.scroll_detector.start(camera_index)

    def on_camera_selection(self, *_args):
        del _args
        selected = self.camera_var.get()
        if selected not in self.camera_choices and self.camera_choices:
            self.camera_var.set(next(iter(self.camera_choices)))

    def refresh_camera_list(self):
        if self._scroll_camera_active or self._camera_scan_in_progress:
            return
        self._camera_scan_in_progress = True
        self.camera_refresh_btn.config(text="Mencari...", state="disabled")
        self.scroll_status.config(text="Memindai kamera yang tersambung...", fg=ACCENT)

        def scan():
            try:
                cameras = self.scroll_detector.list_cameras()
            except Exception as error:
                cameras = []
                message = f"Pemindaian kamera gagal: {error}"
            else:
                message = "Pilih nama webcam yang akan dipakai." if cameras else (
                    "Kamera tidak ditemukan. Pastikan webcam tersambung dan tidak dipakai aplikasi lain.")
            try:
                self.root.after(0, lambda: self.update_camera_list(cameras, message))
            except tk.TclError:
                pass

        threading.Thread(target=scan, daemon=True).start()

    def update_camera_list(self, cameras, message):
        self._camera_scan_in_progress = False
        self.camera_refresh_btn.config(text="↻ Cari", state="normal")
        menu = self.camera_menu["menu"]
        menu.delete(0, "end")
        self.camera_choices = {
            f"{name}  (kamera {index})": index for index, name in cameras
        }
        if self.camera_choices:
            for label in self.camera_choices:
                menu.add_command(label=label, command=lambda value=label: self.camera_var.set(value))
            current = self.camera_var.get()
            self.camera_var.set(current if current in self.camera_choices
                                 else next(iter(self.camera_choices)))
            self.camera_menu.config(state="normal")
        else:
            self.camera_choices = {}
            menu.add_command(label="Tidak ada kamera", state="disabled")
            self.camera_var.set("Tidak ada kamera")
            self.camera_menu.config(state="disabled")
        self.scroll_status.config(text=message, fg=GREEN if cameras else RED)

    def toggle_hand_scroll(self):
        if self._scroll_active:
            self._scroll_active = False
            self.scroll_detector.set_scrolling(False)
            self.scroll_btn.config(text="🖐  Aktifkan scroll tangan")
            self.set_button_color(self.scroll_btn, BLUE)
            self.scroll_status.config(
                text="Scroll mati. Kamera tetap aktif; pointer tetap di area tujuan.", fg=MUTED)
            return

        if not self._scroll_camera_active or not self._scroll_verified:
            self.scroll_status.config(
                text="Verifikasi kamera dan tangan terlebih dahulu.", fg=RED)
            return

        self._scroll_active = True
        self.scroll_detector.set_scrolling(True)
        self.scroll_btn.config(text="⏹  Matikan scroll tangan")
        self.set_button_color(self.scroll_btn, RED)
        self.scroll_status.config(
            text="Scroll aktif. ☝️ Angkat telunjuk dan gerakkan naik/turun. 🤚 Buka telapak untuk berhenti.",
            fg=GREEN)

    def poll_hand_scroll(self):
        try:
            while True:
                kind, message = self.scroll_detector.messages.get_nowait()
                if not self._scroll_camera_active:
                    continue
                self.scroll_status.config(
                    text=message,
                    fg=RED if kind == "error" else (ACCENT if kind == "ready" else GREEN))
                if kind == "verified":
                    self._scroll_verified = True
                    self.scroll_btn.config(text="🖐  Aktifkan scroll tangan", state="normal")
                    self.set_button_color(self.scroll_btn, BLUE)
                elif kind == "verification":
                    self.scroll_status.config(text=message, fg=ACCENT)
                elif kind == "verification_complete":
                    self._scroll_verified = True
                    self.scroll_status.config(text=message, fg=GREEN)
                    self.scroll_btn.config(text="🖐  Aktifkan scroll tangan", state="normal")
                    self.set_button_color(self.scroll_btn, BLUE)
                elif kind == "tracking" and not self._scroll_active:
                    self.scroll_status.config(text=message, fg=ACCENT)
                elif kind == "scroll":
                    self.scroll_status.config(text=message, fg=GREEN)
                elif kind == "error":
                    self._scroll_camera_active = False
                    self._scroll_verified = False
                    self._scroll_active = False
                    self.scroll_verify_btn.config(text="📷 Verifikasi kamera & tangan")
                    self.set_button_color(self.scroll_verify_btn, BLUE)
                    self.camera_menu.config(state="normal")
                    self.camera_refresh_btn.config(state="normal")
                    self.scroll_btn.config(text="🔒 Verifikasi kamera dulu", state="disabled")
                    self.set_button_color(self.scroll_btn, BLUE)
        except queue.Empty:
            pass

        frame = None
        try:
            while True:
                frame = self.scroll_detector.frames.get_nowait()
        except queue.Empty:
            pass
        if frame is not None and self._scroll_camera_active:
            preview_width = max(220, min(400, self.canvas.winfo_width() - 80))
            preview_height = preview_width * 3 // 4
            preview = Image.fromarray(frame).resize(
                (preview_width, preview_height), Image.Resampling.LANCZOS)
            self.scroll_preview.configure(width=preview_width, height=preview_height)
            self.scroll_preview_photo = ImageTk.PhotoImage(preview)
            self.scroll_preview.config(image=self.scroll_preview_photo, text="")
        self.root.after(100, self.poll_hand_scroll)

    def on_resume(self):
        engine.cfg["auto_resume"] = bool(self.resume_var.get())
        save_config(engine.cfg)
        engine.say("Lanjut otomatis: " + ("ON" if engine.cfg["auto_resume"] else "OFF"))

    def on_startup(self):
        enabled = bool(self.startup_var.get())
        try:
            engine.set_auto_start(enabled)
            engine.cfg["auto_start"] = enabled
            save_config(engine.cfg)
            engine.say(
                "Wallpaper otomatis saat login Windows "
                + ("diaktifkan." if enabled else "dimatikan."))
            if enabled and not engine.is_running():
                engine.run_bg(engine._start)
        except (OSError, RuntimeError) as error:
            self.startup_var.set(not enabled)
            engine.say(f"Gagal mengatur autostart: {error}")

    def on_keep_sticker_on_close(self):
        engine.cfg["keep_sticker_on_close"] = bool(self.keep_sticker_var.get())
        save_config(engine.cfg)

    def on_sticker_context_menu(self, event):
        try:
            top = event.widget.winfo_toplevel()
            floating_windows = (self.spotify_sticker, self.spotify_widget)
            if not any(window and window.winfo_exists() and top == window
                       for window in floating_windows):
                return
        except tk.TclError:
            return

        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(label="Buka panel ALAKANG", command=self.restore_app)
        menu.add_separator()
        menu.add_command(label="Keluar sepenuhnya", command=self.shutdown_app)
        menu.tk_popup(event.x_root, event.y_root)
        menu.grab_release()
        return "break"

    def restore_app(self):
        self.root.deiconify()
        self.root.lift()

    @staticmethod
    def spotify_playlist_link(value):
        value = value.strip()
        uri_match = re.fullmatch(r"spotify:playlist:([A-Za-z0-9]+)", value)
        if uri_match:
            playlist_id = uri_match.group(1)
            return playlist_id, f"https://open.spotify.com/playlist/{playlist_id}"

        parsed = urlsplit(value)
        parts = parsed.path.strip("/").split("/")
        if (parsed.scheme in ("http", "https")
                and parsed.netloc.lower() in ("open.spotify.com", "www.open.spotify.com")
                and len(parts) >= 2 and parts[0] == "playlist"
                and re.fullmatch(r"[A-Za-z0-9]+", parts[1])):
            playlist_id = parts[1]
            return playlist_id, f"https://open.spotify.com/playlist/{playlist_id}"
        return None

    def save_spotify_playlist(self):
        playlist = self.spotify_playlist_link(self.spotify_var.get())
        if not playlist:
            engine.say("Tautan playlist tidak valid. Tempel URL playlist Spotify atau spotify:playlist:ID.")
            return
        engine.cfg["spotify_playlist"] = playlist[1]
        save_config(engine.cfg)
        self.spotify_var.set(playlist[1])
        self.show_spotify_widget()
        engine.say("Tautan playlist Spotify disimpan.")

    def choose_sticker_image(self):
        filename = filedialog.askopenfilename(
            parent=self.root,
            title="Pilih foto untuk stiker peliharaan",
            filetypes=[("Gambar", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"),
                       ("Semua file", "*.*")],
        )
        if not filename:
            return
        try:
            with Image.open(filename) as image:
                image.verify()
            self.copy_sticker_asset(filename, "image", self.set_sticker_image)
        except (OSError, UnidentifiedImageError) as error:
            engine.say(f"File gambar tidak bisa dibuka: {error}")

    def sticker_sound_name(self):
        sound_path = engine.cfg.get("sticker_sound", "")
        return f"Suara: {Path(sound_path).name}" if sound_path else "Belum ada suara klik yang dipilih."

    def choose_sticker_sound(self):
        filename = filedialog.askopenfilename(
            parent=self.root,
            title="Pilih suara penyemangat untuk foto",
            filetypes=[("Audio", "*.wav *.mp3"), ("Semua file", "*.*")],
        )
        if filename:
            self.copy_sticker_asset(filename, "sound", self.set_sticker_sound)

    def set_sticker_sound(self, filename):
        engine.cfg["sticker_sound"] = filename
        save_config(engine.cfg)
        self.sound_label.config(text=self.sticker_sound_name())
        engine.say("Suara klik foto berhasil disimpan.")

    def play_sticker_sound(self):
        sound_path = engine.cfg.get("sticker_sound", "")
        if not sound_path or not os.path.isfile(sound_path):
            engine.say("Pilih file suara WAV atau MP3 terlebih dahulu.")
            return
        extension = Path(sound_path).suffix.lower()
        if extension not in {".wav", ".mp3"}:
            engine.say("Format suara belum didukung. Pilih file WAV atau MP3.")
            return
        try:
            if sys.platform == "win32" and extension == ".wav":
                import winsound
                winsound.PlaySound(sound_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                player = engine.find_mpv()
                if not player:
                    engine.say("MP3 perlu mpv. Install mpv, lalu pilih suara lagi.")
                    return
                subprocess.Popen(
                    [player, sound_path, "--no-video", "--no-terminal", "--really-quiet"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=0x08000000 if engine.OS == "Windows" else 0,
                )
        except (OSError, RuntimeError) as error:
            engine.say(f"Suara gagal diputar: {error}")

    def on_sticker_click(self):
        if self.sticker_original:
            self.play_sticker_sound()
        else:
            self.expand_spotify_sticker()

    def choose_sticker_video(self):
        filename = filedialog.askopenfilename(
            parent=self.root,
            title="Pilih video untuk stiker",
            filetypes=[("Video", "*.mp4 *.mkv *.webm *.mov *.avi"), ("Semua file", "*.*")],
        )
        if not filename:
            return
        if not os.path.isfile(filename):
            engine.say("File video tidak ditemukan.")
            return
        self.copy_sticker_asset(filename, "video", self.set_sticker_video)

    def copy_sticker_asset(self, filename, asset_type, callback):
        source = Path(filename).resolve()
        target = engine.LOG.parent / "semangat_wallpaper" / f"sticker_{asset_type}{source.suffix.lower()}"

        def copy_asset():
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                if source != target.resolve():
                    shutil.copy2(source, target)
            except OSError as error:
                message = str(error)
                try:
                    self.root.after(0, lambda: engine.say(f"File stiker gagal disimpan: {message}"))
                except tk.TclError:
                    pass
                return

            try:
                self.root.after(0, lambda: callback(str(target)))
            except tk.TclError:
                pass

        threading.Thread(target=copy_asset, daemon=True).start()

    def set_sticker_video(self, filename):
        self.stop_sticker_video()
        engine.cfg["sticker_image"] = ""
        engine.cfg["sticker_video"] = filename
        save_config(engine.cfg)
        self.sticker_original = None
        self.rebuild_spotify_sticker()
        engine.say("Video stiker disimpan dan diputar berulang tanpa suara.")

    def stop_sticker_video(self):
        process = self.sticker_video_proc
        self.sticker_video_proc = None
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()

    def rebuild_spotify_sticker(self):
        if self.spotify_sticker and self.spotify_sticker.winfo_exists():
            self.sticker_x = self.spotify_sticker.winfo_x()
            self.sticker_y = self.spotify_sticker.winfo_y()
            self.spotify_sticker.destroy()
            self.spotify_sticker = None
            self.sticker_video_frame = None
        if engine.cfg.get("sticker_image") or engine.cfg.get("sticker_video"):
            self.show_spotify_sticker()

    def search_google_images(self):
        query = simpledialog.askstring("Cari foto", "Mau mencari foto apa di Google Images?",
                                       parent=self.root)
        if not query or not query.strip():
            return
        search_url = "https://www.google.com/search?tbm=isch&q=" + quote_plus(query.strip())
        webbrowser.open(search_url, new=2)
        engine.say("Pilih gambar di Google, buka gambar aslinya, lalu tempel URL gambar langsung di kolom foto.")

    def download_sticker_image(self):
        image_url = self.sticker_url_var.get().strip()
        parsed = urlsplit(image_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            engine.say("Tempel URL langsung gambar (http atau https), bukan halaman hasil pencarian.")
            return
        threading.Thread(target=self._download_sticker_image, args=(image_url,), daemon=True).start()

    def _download_sticker_image(self, image_url):
        try:
            request = Request(image_url, headers={"User-Agent": "SemangatWallpaper/1.0"})
            with urlopen(request, timeout=15) as response:
                content_type = response.headers.get_content_type()
                if not content_type.startswith("image/"):
                    raise ValueError("URL tidak mengarah ke file gambar.")
                data = response.read(10 * 1024 * 1024 + 1)
            if len(data) > 10 * 1024 * 1024:
                raise ValueError("Ukuran gambar terlalu besar (maksimal 10 MB).")
            with Image.open(BytesIO(data)) as image:
                image.load()
            target_dir = engine.LOG.parent / "semangat_wallpaper"
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / "pet_sticker_image.png"
            with Image.open(BytesIO(data)) as image:
                image.convert("RGBA").save(target, format="PNG")
            self.root.after(0, lambda: self.set_sticker_image(str(target)))
        except (OSError, ValueError, UnidentifiedImageError) as error:
            self.root.after(0, lambda message=str(error): engine.say(f"Gagal mengunduh foto: {message}"))

    def set_sticker_image(self, image_path):
        try:
            with Image.open(image_path) as image:
                self.sticker_original = image.convert("RGBA").copy()
            self.stop_sticker_video()
            engine.cfg["sticker_image"] = image_path
            engine.cfg["sticker_video"] = ""
            save_config(engine.cfg)
            self.rebuild_spotify_sticker()
            engine.say("Foto stiker berhasil diperbarui.")
        except (OSError, UnidentifiedImageError) as error:
            engine.say(f"Foto stiker tidak valid: {error}")

    def refresh_sticker_images(self):
        if not self.sticker_original:
            return
        compact_size = max(32, self.sticker_size - 12)
        compact_bg = self.sticker_transparent_color if self.sticker_transparent else CARD
        self.sticker_photo = ImageTk.PhotoImage(self.make_sticker_thumbnail(compact_size, compact_bg))
        self.sticker_expanded_photo = ImageTk.PhotoImage(self.make_sticker_thumbnail(64, CARD))
        self.sticker_edit_photo = ImageTk.PhotoImage(
            self.make_sticker_thumbnail(self.sticker_size, compact_bg))
        if self.spotify_sticker and self.spotify_sticker.winfo_exists():
            self.sticker_image_button.configure(image=self.sticker_photo, text="")
            self.sticker_expanded_image.configure(image=self.sticker_expanded_photo)
            if hasattr(self, "sticker_edit_image") and self.sticker_edit_image.winfo_exists():
                self.sticker_edit_image.configure(image=self.sticker_edit_photo)

    def make_sticker_thumbnail(self, size, background):
        original = self.sticker_original
        if original is None:
            raise ValueError("Pilih gambar stiker sebelum membuat thumbnail.")
        contained = ImageOps.contain(original, (size, size),
                                     method=Image.Resampling.LANCZOS)
        color = tuple(int(background[index:index + 2], 16) for index in (1, 3, 5))
        canvas = Image.new("RGB", (size, size), color)
        x = (size - contained.width) // 2
        y = (size - contained.height) // 2
        alpha_lut = [0 if alpha < 128 else 255 for alpha in range(256)]
        alpha_mask = contained.getchannel("A").point(alpha_lut)
        canvas.paste(contained.convert("RGB"), (x, y), alpha_mask)
        return canvas

    def open_spotify_playlist(self):
        playlist = self.spotify_playlist_link(self.spotify_var.get())
        if not playlist:
            engine.say("Masukkan URL playlist Spotify yang valid dulu.")
            return
        playlist_id, playlist_url = playlist
        engine.cfg["spotify_playlist"] = playlist_url
        save_config(engine.cfg)
        self.spotify_var.set(playlist_url)
        spotify_uri = f"spotify:playlist:{playlist_id}"
        try:
            if platform.system() == "Windows":
                os.startfile(spotify_uri)
            elif not webbrowser.open(spotify_uri):
                webbrowser.open(playlist_url, new=2)
            engine.say("Membuka playlist di Spotify.")
        except (OSError, webbrowser.Error):
            webbrowser.open(playlist_url, new=2)
            engine.say("Membuka tautan playlist Spotify.")

    def toggle_spotify_widget(self):
        if self.spotify_widget and self.spotify_widget.winfo_exists():
            self.spotify_widget.destroy()
            self.spotify_widget = None
        else:
            self.show_spotify_widget()

    def show_spotify_widget(self):
        if not engine.cfg.get("spotify_playlist"):
            engine.say("Simpan tautan playlist Spotify terlebih dahulu.")
            return
        if self.spotify_widget and self.spotify_widget.winfo_exists():
            self.spotify_widget.deiconify()
            self.spotify_widget.lift()
            return

        widget = tk.Toplevel(self.root)
        self.spotify_widget = widget
        widget.overrideredirect(True)
        widget.attributes("-topmost", True)
        widget.configure(bg=CARD)
        width, height = 220, 76
        x = max(0, widget.winfo_screenwidth() - width - 24)
        y = max(0, widget.winfo_screenheight() - height - 90)
        widget.geometry(f"{width}x{height}+{x}+{y}")

        header = tk.Frame(widget, bg=CARD, height=26)
        header.pack(fill="x")
        header.pack_propagate(False)
        title = tk.Label(header, text="🎵 Mini Spotify", bg=CARD, fg=TEXT,
                         font=("Segoe UI", 8, "bold"), cursor="fleur")
        title.pack(side="left", padx=7)
        title.bind("<ButtonPress-1>", self.start_spotify_drag)
        title.bind("<B1-Motion>", self.drag_spotify_widget)
        tk.Button(header, text="×", command=self.toggle_spotify_widget,
                  bg=CARD, fg=TEXT, relief="flat", bd=0, width=2
                  ).pack(side="right", padx=3)
        self.btn(widget, "Buka playlist di Spotify", self.open_spotify_playlist,
                 GREEN, small=True).pack(fill="both", expand=True, padx=6, pady=(0, 6))

    def start_spotify_drag(self, event):
        if self.spotify_widget and self.spotify_widget.winfo_exists():
            self.spotify_drag_offset_x = event.x_root - self.spotify_widget.winfo_x()
            self.spotify_drag_offset_y = event.y_root - self.spotify_widget.winfo_y()

    def drag_spotify_widget(self, event):
        if self.spotify_widget and self.spotify_widget.winfo_exists():
            x = event.x_root - getattr(self, "spotify_drag_offset_x", 0)
            y = event.y_root - getattr(self, "spotify_drag_offset_y", 0)
            x = max(0, min(x, self.spotify_widget.winfo_screenwidth() - self.spotify_widget.winfo_width()))
            y = max(0, min(y, self.spotify_widget.winfo_screenheight() - self.spotify_widget.winfo_height()))
            self.spotify_widget.geometry(f"+{x}+{y}")

    def toggle_spotify_sticker(self):
        if self.spotify_sticker and self.spotify_sticker.winfo_exists():
            self.stop_sticker_video()
            self.spotify_sticker.destroy()
            self.spotify_sticker = None
            self.sticker_video_frame = None
        else:
            if not engine.cfg.get("sticker_image") and not engine.cfg.get("sticker_video"):
                engine.say("Pilih foto atau video untuk stiker peliharaan terlebih dahulu.")
                return
            self.show_spotify_sticker()

    def show_spotify_sticker(self):
        if engine.cfg.get("sticker_video"):
            self.show_video_sticker()
            return
        if self.spotify_sticker and self.spotify_sticker.winfo_exists():
            self.spotify_sticker.deiconify()
            self.spotify_sticker.lift()
            return

        sticker = tk.Toplevel(self.root)
        self.spotify_sticker = sticker
        sticker.overrideredirect(True)
        sticker.attributes("-topmost", True)
        self.sticker_transparent_color = "#010203"
        self.sticker_transparent = False
        try:
            sticker.attributes("-transparentcolor", self.sticker_transparent_color)
            self.sticker_transparent = True
            sticker.configure(bg=self.sticker_transparent_color)
        except tk.TclError:
            sticker.configure(bg=CARD)
        screen_width = sticker.winfo_screenwidth()
        screen_height = sticker.winfo_screenheight()
        x = self.sticker_x if self.sticker_x >= 0 else screen_width - self.sticker_size - 20
        x = max(0, min(x, screen_width - self.sticker_size))
        y = max(0, min(self.sticker_y, screen_height - self.sticker_size))
        sticker.geometry(f"{self.sticker_size}x{self.sticker_size}+{x}+{y}")

        compact_bg = self.sticker_transparent_color if self.sticker_transparent else CARD
        compact = tk.Frame(sticker, bg=compact_bg, bd=0, relief="flat")
        compact.pack(fill="both", expand=True)
        self.sticker_image_button = tk.Button(
            compact, text="🎵", command=self.on_sticker_click,
            bg=compact_bg, fg=TEXT, activebackground=compact_bg, activeforeground=TEXT,
            relief="flat", bd=0, font=("Segoe UI", 22, "bold"), cursor="hand2")
        self.sticker_image_button.pack(fill="both", expand=True, padx=4, pady=4)

        expanded = tk.Frame(sticker, bg=CARD, bd=1, relief="solid")
        header = tk.Frame(expanded, bg=CARD)
        header.pack(fill="x", padx=8, pady=(5, 2))
        title = tk.Label(header, text="🐾 Stiker peliharaan", bg=CARD, fg=TEXT,
                         font=("Segoe UI", 9, "bold"), cursor="fleur")
        title.pack(side="left")
        title.bind("<ButtonPress-1>", self.start_sticker_drag)
        title.bind("<B1-Motion>", self.drag_sticker)
        title.bind("<ButtonRelease-1>", self.save_sticker_position)
        tk.Button(header, text="−", command=self.collapse_spotify_sticker,
                  bg=CARD, fg=TEXT, relief="flat", bd=0, width=2).pack(side="right")
        expanded_content = tk.Frame(expanded, bg=CARD)
        expanded_content.pack(fill="both", expand=True, padx=8, pady=(2, 7))
        self.sticker_expanded_image = tk.Label(expanded_content, bg=CARD, width=64, height=64)
        self.sticker_expanded_image.pack(side="left", padx=(0, 8))
        tk.Button(expanded_content, text="Putar suara\npenyemangat",
              command=self.play_sticker_sound, bg=GREEN, fg="#ffffff",
                  activebackground=GREEN, relief="flat", bd=0,
                  font=("Segoe UI", 9, "bold"), cursor="hand2").pack(
                      side="left", fill="both", expand=True)
        self.sticker_compact = compact
        self.sticker_expanded = expanded
        if self.sticker_original:
            self.refresh_sticker_images()

    def begin_sticker_edit(self):
        if not self.sticker_original:
            engine.say("Pilih foto stiker terlebih dahulu untuk mengatur langsung.")
            return
        if not self.spotify_sticker or not self.spotify_sticker.winfo_exists():
            self.show_spotify_sticker()
        if not self.spotify_sticker or not self.spotify_sticker.winfo_exists():
            return

        self._edit_mode = True
        self.sticker_compact.pack_forget()
        self.sticker_expanded.pack_forget()
        self.sticker_edit_frame = tk.Frame(self.spotify_sticker, bg=CARD, bd=1, relief="solid")
        self.sticker_edit_frame.pack(fill="both", expand=True)
        header = tk.Frame(self.sticker_edit_frame, bg=CARD, height=30)
        header.pack(fill="x")
        header.pack_propagate(False)
        title = tk.Label(header, text="Seret foto • Tarik sudut untuk ubah ukuran",
                         bg=CARD, fg=TEXT, font=("Segoe UI", 8, "bold"), cursor="fleur")
        title.pack(side="left", padx=(6, 2), fill="x", expand=True)
        title.bind("<ButtonPress-1>", self.start_sticker_drag)
        title.bind("<B1-Motion>", self.drag_sticker)
        title.bind("<ButtonRelease-1>", self.save_sticker_position)
        self.btn(header, "✓ Terima", self.accept_sticker_edit, GREEN,
                 small=True).pack(side="right", padx=4, pady=2)

        self.sticker_edit_stage = tk.Frame(
            self.sticker_edit_frame, bg=CARD, width=self.sticker_size, height=self.sticker_size)
        self.sticker_edit_stage.pack(fill="both", expand=True)
        self.sticker_edit_stage.pack_propagate(False)
        self.sticker_edit_image = tk.Label(self.sticker_edit_stage, bg=CARD, cursor="fleur")
        self.sticker_edit_image.pack(fill="both", expand=True)
        self.sticker_edit_image.bind("<ButtonPress-1>", self.start_sticker_drag)
        self.sticker_edit_image.bind("<B1-Motion>", self.drag_sticker)
        self.sticker_edit_image.bind("<ButtonRelease-1>", self.save_sticker_position)
        self.sticker_resize_grip = tk.Label(
            self.sticker_edit_stage, text="◢", bg=ACCENT, fg="#ffffff",
            font=("Segoe UI", 11, "bold"), cursor="size_nw_se")
        self.sticker_resize_grip.place(relx=1, rely=1, anchor="se", width=22, height=22)
        self.sticker_resize_grip.bind("<ButtonPress-1>", self.start_sticker_resize)
        self.sticker_resize_grip.bind("<B1-Motion>", self.resize_sticker)
        self.sticker_resize_grip.bind("<ButtonRelease-1>", self.save_sticker_size)

        x, y = self.spotify_sticker.winfo_x(), self.spotify_sticker.winfo_y()
        self.spotify_sticker.geometry(f"{self.sticker_size}x{self.sticker_size + 30}+{x}+{y}")
        self.refresh_sticker_images()
        engine.say("Mode atur aktif: pindahkan dan ubah ukuran foto, lalu tekan Terima.")

    def accept_sticker_edit(self):
        if not self._edit_mode:
            return
        sticker = self.spotify_sticker
        if sticker is None or not sticker.winfo_exists():
            self._edit_mode = False
            return
        self._edit_mode = False
        self.sticker_edit_frame.destroy()
        self.sticker_compact.pack(fill="both", expand=True)
        sticker.geometry(
            f"{self.sticker_size}x{self.sticker_size}+{sticker.winfo_x()}+{sticker.winfo_y()}")
        self.save_sticker_position()
        engine.say("Posisi dan ukuran foto diterima dan disimpan.")

    def start_sticker_resize(self, event):
        self._resize_start_x = event.x_root
        self._resize_start_y = event.y_root
        self._resize_start_size = self.sticker_size

    def resize_sticker(self, event):
        delta = max(event.x_root - self._resize_start_x, event.y_root - self._resize_start_y)
        size = max(56, min(400, self._resize_start_size + delta))
        self.sticker_size_scale.set(size)
        self.on_sticker_size(size)

    def show_video_sticker(self):
        if self.spotify_sticker and self.spotify_sticker.winfo_exists() and self.sticker_video_frame:
            self.spotify_sticker.deiconify()
            self.spotify_sticker.lift()
            return

        video_path = engine.cfg.get("sticker_video", "")
        if not os.path.isfile(video_path):
            engine.say("File video stiker tidak ditemukan. Pilih ulang file videonya.")
            engine.cfg["sticker_video"] = ""
            save_config(engine.cfg)
            return

        sticker = tk.Toplevel(self.root)
        self.spotify_sticker = sticker
        sticker.overrideredirect(True)
        sticker.attributes("-topmost", True)
        video_width = max(140, self.sticker_size * 2)
        video_height = video_width * 9 // 16
        screen_width, screen_height = sticker.winfo_screenwidth(), sticker.winfo_screenheight()
        x = self.sticker_x if self.sticker_x >= 0 else screen_width - video_width - 20
        x = max(0, min(x, max(0, screen_width - video_width)))
        y = max(0, min(self.sticker_y, max(0, screen_height - video_height - 30)))
        sticker.geometry(f"{video_width}x{video_height + 30}+{x}+{y}")

        titlebar = tk.Frame(sticker, bg=CARD, height=30)
        titlebar.pack(fill="x")
        titlebar.pack_propagate(False)
        title = tk.Label(titlebar, text="🎞 Video stiker", bg=CARD, fg=TEXT,
                         font=("Segoe UI", 9, "bold"), cursor="fleur")
        title.pack(side="left", padx=8)
        title.bind("<ButtonPress-1>", self.start_sticker_drag)
        title.bind("<B1-Motion>", self.drag_sticker)
        title.bind("<ButtonRelease-1>", self.save_sticker_position)
        tk.Button(titlebar, text="×", command=self.toggle_spotify_sticker,
                  bg=CARD, fg=TEXT, relief="flat", bd=0, width=2).pack(side="right", padx=4)

        self.sticker_video_frame = tk.Frame(sticker, bg="#000000", bd=0, highlightthickness=0)
        self.sticker_video_frame.pack(fill="both", expand=True)
        self.sticker_video_frame.update_idletasks()
        self.root.after(150, self.start_sticker_video)

    def start_sticker_video(self):
        if not self.sticker_video_frame or not self.sticker_video_frame.winfo_exists():
            return
        mpv_path = engine.find_mpv()
        video_path = engine.cfg.get("sticker_video", "")
        if not mpv_path:
            engine.say("mpv tidak ditemukan. Install mpv untuk memutar video stiker.")
            return
        if not os.path.isfile(video_path):
            engine.say("File video stiker tidak ditemukan.")
            return
        command = [
            mpv_path, video_path, f"--wid={int(self.sticker_video_frame.winfo_id())}",
            "--loop-file=inf", "--no-audio", "--mute=yes", "--no-osc",
            "--no-input-default-bindings", "--border=no", "--force-window=yes",
            "--msg-level=all=warn",
        ]
        log_path = engine.LOG.parent / "semangat_wallpaper_sticker.log"
        try:
            with open(log_path, "w", encoding="utf-8") as log_file:
                self.sticker_video_proc = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    creationflags=0x08000000 if engine.OS == "Windows" else 0,
                )
        except OSError as error:
            engine.say(f"Tidak bisa memulai video stiker: {error}")
            return
        self.root.after(5000, lambda process=self.sticker_video_proc:
                        self.check_sticker_video_start(process))

    def check_sticker_video_start(self, process):
        if process is not self.sticker_video_proc or process.poll() is None:
            return
        log_path = engine.LOG.parent / "semangat_wallpaper_sticker.log"
        try:
            details = [line.strip() for line in log_path.read_text(
                encoding="utf-8", errors="replace").splitlines() if line.strip()]
        except OSError:
            details = []
        reason = " | ".join(details[-3:])
        self.sticker_video_proc = None
        if self.spotify_sticker and self.spotify_sticker.winfo_exists():
            self.spotify_sticker.destroy()
        self.spotify_sticker = None
        self.sticker_video_frame = None
        engine.say("Gagal memutar video stiker. Pastikan file lokal masih tersedia dan formatnya didukung."
                   + (f" Detail: {reason}" if reason else ""))

    def expand_spotify_sticker(self):
        if not self.spotify_sticker or not self.spotify_sticker.winfo_exists():
            return
        self.sticker_compact.pack_forget()
        self.sticker_expanded.pack(fill="both", expand=True)
        width = max(240, self.sticker_size * 3)
        height = max(112, self.sticker_size + 48)
        x = min(self.spotify_sticker.winfo_x(), max(0, self.spotify_sticker.winfo_screenwidth() - width))
        y = min(self.spotify_sticker.winfo_y(), max(0, self.spotify_sticker.winfo_screenheight() - height))
        self.spotify_sticker.geometry(
            f"{width}x{height}+{x}+{y}")

    def collapse_spotify_sticker(self):
        if not self.spotify_sticker or not self.spotify_sticker.winfo_exists():
            return
        self.sticker_expanded.pack_forget()
        self.sticker_compact.pack(fill="both", expand=True)
        self.spotify_sticker.geometry(
            f"{self.sticker_size}x{self.sticker_size}+{self.spotify_sticker.winfo_x()}+{self.spotify_sticker.winfo_y()}")

    def start_sticker_drag(self, event):
        if self.spotify_sticker and self.spotify_sticker.winfo_exists():
            self.sticker_drag_offset_x = event.x_root - self.spotify_sticker.winfo_x()
            self.sticker_drag_offset_y = event.y_root - self.spotify_sticker.winfo_y()

    def drag_sticker(self, event):
        if self.spotify_sticker and self.spotify_sticker.winfo_exists():
            x = event.x_root - getattr(self, "sticker_drag_offset_x", 0)
            y = event.y_root - getattr(self, "sticker_drag_offset_y", 0)
            x = max(0, min(x, self.spotify_sticker.winfo_screenwidth() - self.spotify_sticker.winfo_width()))
            y = max(0, min(y, self.spotify_sticker.winfo_screenheight() - self.spotify_sticker.winfo_height()))
            self.spotify_sticker.geometry(f"+{max(0, x)}+{max(0, y)}")
            self.sticker_x, self.sticker_y = x, y
            self.schedule_sticker_layout_save()

    def on_sticker_size(self, value):
        self.sticker_size = max(56, min(400, int(float(value))))
        self.sticker_size_label.config(text=f"{self.sticker_size} px")
        if not self.spotify_sticker or not self.spotify_sticker.winfo_exists():
            return
        x, y = self.spotify_sticker.winfo_x(), self.spotify_sticker.winfo_y()
        if self.sticker_video_frame and self.sticker_video_frame.winfo_exists():
            width = max(140, self.sticker_size * 2)
            height = width * 9 // 16 + 30
            x = min(x, max(0, self.spotify_sticker.winfo_screenwidth() - width))
            y = min(y, max(0, self.spotify_sticker.winfo_screenheight() - height))
            self.spotify_sticker.geometry(f"{width}x{height}+{x}+{y}")
        elif self._edit_mode:
            height = self.sticker_size + 30
            x = min(x, max(0, self.spotify_sticker.winfo_screenwidth() - self.sticker_size))
            y = min(y, max(0, self.spotify_sticker.winfo_screenheight() - height))
            self.sticker_edit_stage.configure(width=self.sticker_size, height=self.sticker_size)
            self.spotify_sticker.geometry(f"{self.sticker_size}x{height}+{x}+{y}")
        elif self.sticker_expanded.winfo_ismapped():
            width = max(240, self.sticker_size * 3)
            height = max(112, self.sticker_size + 48)
            x = min(x, max(0, self.spotify_sticker.winfo_screenwidth() - width))
            y = min(y, max(0, self.spotify_sticker.winfo_screenheight() - height))
            self.spotify_sticker.geometry(f"{width}x{height}+{x}+{y}")
        else:
            self.spotify_sticker.geometry(f"{self.sticker_size}x{self.sticker_size}+{x}+{y}")
        self.refresh_sticker_images()
        self.schedule_sticker_layout_save()

    def save_sticker_size(self, _event=None):
        del _event
        engine.cfg["sticker_size"] = self.sticker_size
        self.save_sticker_position()

    def save_sticker_position(self, _event=None):
        del _event
        if self._layout_save_job:
            try:
                self.root.after_cancel(self._layout_save_job)
            except tk.TclError:
                pass
            self._layout_save_job = None
        if self.spotify_sticker and self.spotify_sticker.winfo_exists():
            self.sticker_x = self.spotify_sticker.winfo_x()
            self.sticker_y = self.spotify_sticker.winfo_y()
        engine.cfg["sticker_x"] = self.sticker_x
        engine.cfg["sticker_y"] = self.sticker_y
        engine.cfg["sticker_size"] = self.sticker_size
        save_config(engine.cfg)

    def schedule_sticker_layout_save(self):
        if self._layout_save_job:
            self.root.after_cancel(self._layout_save_job)
        self._layout_save_job = self.root.after(250, self.flush_sticker_layout_save)

    def flush_sticker_layout_save(self):
        self._layout_save_job = None
        self.save_sticker_position()

    def on_volume_drag(self, value):
        self.vol_label.config(text=str(int(float(value))))

    def on_volume_release(self, _event):
        del _event
        value = int(self.vol.get())
        threading.Thread(target=engine.apply_volume, args=(value,), daemon=True).start()

    def setup_hotkey(self):
        try:
            from pynput import keyboard
        except ImportError:
            engine.say("Hotkey nonaktif (pynput belum terpasang: pip install pynput).")
            return None
        listener = keyboard.GlobalHotKeys({engine.HOTKEY: lambda: engine.events.put(("toggle",))})
        listener.start()
        return listener

    def tick(self):
        try:
            while True:
                kind, *rest = engine.events.get_nowait()
                if kind == "msg":
                    self.msg.config(text=rest[0])
                elif kind == "quote":
                    self.quote.config(text=random.choice(QUOTES))
                elif kind == "toggle":
                    self.on_toggle()
        except queue.Empty:
            pass

        running = engine.is_running_cached()
        self.dot.config(fg=GREEN if running else RED)
        self.state.config(text="Menyala" if running else "Mati")
        self.main_btn.config(text="⏹  Matikan" if running else "▶  Nyalakan")
        self.set_button_color(self.main_btn, RED if running else ACCENT)
        saved = engine.cfg["positions"].get(video_key(engine.cfg.get("url", "")), 0)
        self.pos.config(text=f"Posisi terakhir: {fmt_time(saved)}" if saved >= 5 else "")
        self.root.after(400, self.tick)

    def on_close(self):
        if engine.cfg.get("keep_sticker_on_close", False):
            pet_visible = self.spotify_sticker and self.spotify_sticker.winfo_exists()
            spotify_visible = self.spotify_widget and self.spotify_widget.winfo_exists()
            if pet_visible or spotify_visible:
                if pet_visible:
                    self.save_sticker_position()
                self.root.withdraw()
                return

        self.shutdown_app()

    def shutdown_app(self):
        self._scroll_camera_active = False
        self._scroll_active = False
        self.scroll_detector.stop()
        self.games.close()
        if self.listener:
            self.listener.stop()
        self.stop_sticker_video()
        engine.save_position()
        self.root.unbind_all("<MouseWheel>")
        self.root.unbind_all("<Button-4>")
        self.root.unbind_all("<Button-5>")
        self.root.unbind_all("<Button-3>")
        self.root.destroy()
