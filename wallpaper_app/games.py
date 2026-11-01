"""Mini-games for the ALAKANG desktop companion."""

import math
import queue
import random
import sys
import threading
import time
import tkinter as tk

from PIL import Image, ImageTk

from .config import ACCENT, BG, BLUE, BUTTON, CARD, GREEN, MUTED, RED, TEXT
from .scroll_detector import HAND_CONNECTIONS, HandScrollDetector, ensure_hand_model


class GameHub:
    def __init__(self, root, parent):
        self.root = root
        self.dino_game = None
        self.spider_game = None

        card = tk.Frame(parent, bg=CARD, padx=14, pady=12)
        card.pack(fill="x", pady=5)
        tk.Label(card, text="ARENA MINI GAME", bg=CARD, fg=ACCENT,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(card, text="Istirahat sebentar, lanjut lagi nanti.",
                 bg=CARD, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(
                     anchor="w", pady=(3, 8))

        self._game_card(
            card, "🐈  Kucing Dash",
            "Lompati kaktus dan burung. Klik layar atau tekan Spasi untuk melompat.",
            "Mainkan Kucing Dash", self.open_dino, ACCENT)
        self._game_card(
            card, "🕸  WEB HERO",
            "Verifikasi kedua telapak lewat kamera, lalu tangkap peluru dengan gestur 🤟.",
            "Mainkan WEB HERO", self.open_spider, BLUE)

    def _game_card(self, parent, title, description, button_text, command, color):
        game_card = tk.Frame(parent, bg=BG, padx=11, pady=10)
        game_card.pack(fill="x", pady=(7, 0))
        tk.Label(game_card, text=title, bg=BG, fg=TEXT,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(game_card, text=description, bg=BG, fg=MUTED,
                 font=("Segoe UI", 8), wraplength=420,
                 justify="left").pack(anchor="w", pady=(3, 7))
        tk.Button(
            game_card, text=button_text, command=command, bg=color, fg="#ffffff",
            activebackground=color, activeforeground="#ffffff", relief="flat",
            bd=0, cursor="hand2", font=("Segoe UI", 9, "bold"),
            padx=10, pady=7).pack(fill="x")

    def open_dino(self):
        if self.dino_game and self.dino_game.window.winfo_exists():
            self.dino_game.window.deiconify()
            self.dino_game.window.lift()
            return
        self.dino_game = DinoGame(self.root)

    def open_spider(self):
        if self.spider_game and self.spider_game.window.winfo_exists():
            self.spider_game.window.deiconify()
            self.spider_game.window.lift()
            return
        self.spider_game = SpiderGame(self.root)

    def close(self):
        if self.dino_game:
            self.dino_game.close()
        if self.spider_game:
            self.spider_game.close()


class DinoGame:
    def __init__(self, root):
        self.window = tk.Toplevel(root)
        self.window.title("Kucing Dash • ALAKANG")
        self.window.configure(bg=BG)
        self.window.geometry("760x420")
        self.window.minsize(500, 330)
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        header = tk.Frame(self.window, bg=BG, padx=14, pady=9)
        header.pack(fill="x")
        tk.Label(header, text="KUCING DASH", bg=BG, fg=TEXT,
                 font=("Segoe UI", 12, "bold")).pack(side="left")
        self.score_label = tk.Label(header, text="SKOR 00000   •   TERBAIK 00000",
                                    bg=BG, fg=MUTED, font=("Segoe UI", 9, "bold"))
        self.score_label.pack(side="right")

        self.canvas = tk.Canvas(
            self.window, bg="#e9e3da", highlightthickness=0, takefocus=True)
        self.canvas.pack(fill="both", expand=True, padx=12)
        controls = tk.Frame(self.window, bg=BG, padx=12, pady=9)
        controls.pack(fill="x")
        tk.Label(controls, text="Spasi / klik untuk lompat", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        self.restart_button = tk.Button(
            controls, text="Mulai ulang", command=self.reset, bg=BUTTON, fg="#ffffff",
            activebackground=BUTTON, relief="flat", bd=0, cursor="hand2",
            font=("Segoe UI", 9, "bold"), padx=12, pady=6)
        self.restart_button.pack(side="right")

        self.best_score = 0
        self.running = True
        self.canvas.bind("<Button-1>", self.jump)
        self.canvas.bind("<Configure>", self.draw)
        self.window.bind("<space>", self.jump)
        self.reset()
        self.last_frame = time.monotonic()
        self.window.after(33, self.tick)
        self.canvas.focus_set()

    def reset(self):
        self.score = 0.0
        self.cat_velocity = 0.0
        self.obstacles = []
        self.spawn_timer = 0.8
        self.game_over = False
        self.cat_y = None
        self.restart_button.configure(state="normal")
        self.draw()

    def jump(self, _event=None):
        if self.game_over:
            self.reset()
            return "break"
        ground = self.canvas.winfo_height() - 48
        cat_y = ground - 42 if self.cat_y is None else self.cat_y
        if cat_y >= ground - 43:
            self.cat_velocity = -710
        return "break"

    def tick(self):
        if not self.running or not self.window.winfo_exists():
            return
        now = time.monotonic()
        elapsed = min(now - self.last_frame, 0.05)
        self.last_frame = now
        if not self.game_over:
            self.update_game(elapsed)
        self.draw()
        self.window.after(33, self.tick)

    def update_game(self, elapsed):
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        ground = height - 48
        if self.cat_y is None:
            self.cat_y = ground - 42
        self.cat_velocity += 1900 * elapsed
        self.cat_y = min(ground - 42, self.cat_y + self.cat_velocity * elapsed)
        if self.cat_y >= ground - 42:
            self.cat_velocity = 0

        speed = 300 + min(480, int(self.score // 10) * 28)
        self.score += elapsed * 10
        self.spawn_timer -= elapsed
        if self.spawn_timer <= 0:
            kind = random.choice(("cactus", "cactus", "bird"))
            obstacle_height = random.randint(34, 56) if kind == "cactus" else 24
            obstacle_width = random.randint(20, 32) if kind == "cactus" else 38
            obstacle_y = ground - obstacle_height
            if kind == "bird":
                obstacle_y = ground - random.choice((82, 108, 132))
            self.obstacles.append({
                "x": width + 20, "y": obstacle_y, "width": obstacle_width,
                "height": obstacle_height, "kind": kind, "passed": False,
            })
            self.spawn_timer = max(0.65, random.uniform(1.05, 1.45)
                                  - int(self.score // 10) * 0.045)

        cat_box = (83, self.cat_y + 7, 122, self.cat_y + 39)
        for obstacle in self.obstacles:
            obstacle["x"] -= speed * elapsed
            left = obstacle["x"]
            right = left + obstacle["width"]
            top = obstacle["y"]
            bottom = top + obstacle["height"]
            if (cat_box[0] < right - 4 and cat_box[2] > left + 4
                    and cat_box[1] < bottom - 3 and cat_box[3] > top + 3):
                self.game_over = True
                self.best_score = max(self.best_score, int(self.score))
                self.restart_button.configure(state="normal")
                break
            if not obstacle["passed"] and right < cat_box[0]:
                obstacle["passed"] = True
                self.score += 5
        self.obstacles = [
            obstacle for obstacle in self.obstacles
            if obstacle["x"] + obstacle["width"] > -10
        ]

    def draw(self, _event=None):
        if not self.canvas.winfo_exists():
            return
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        ground = height - 48
        self.canvas.delete("all")
        self.canvas.create_oval(-100, ground - 175, width * 0.52, ground + 45,
                                fill="#d9d4c9", outline="")
        self.canvas.create_oval(width * 0.45, ground - 145, width + 100, ground + 50,
                                fill="#d6d1c7", outline="")
        self.canvas.create_line(0, ground, width, ground, fill="#7f8e78", width=3)
        self.canvas.create_line(0, ground + 5, width, ground + 5,
                                fill="#c6a889", width=2)
        self.canvas.create_text(
            102, self.cat_y if self.cat_y is not None else ground - 42,
            text="🐈", font=("Segoe UI Emoji", 38), anchor="center")

        for obstacle in self.obstacles:
            x, y = obstacle["x"], obstacle["y"]
            if obstacle["kind"] == "cactus":
                color = "#557f70"
                stem_width = max(10, obstacle["width"] // 2)
                self.canvas.create_rectangle(
                    x + stem_width // 2, y + 9, x + stem_width * 1.5,
                    ground, fill=color, outline="")
                self.canvas.create_rectangle(
                    x, y + 20, x + stem_width // 2 + 2, y + 30,
                    fill=color, outline="")
                self.canvas.create_rectangle(
                    x, y + 15, x + 7, y + 29, fill=color, outline="")
                self.canvas.create_rectangle(
                    x + stem_width, y + 18, x + obstacle["width"], y + 28,
                    fill=color, outline="")
                self.canvas.create_rectangle(
                    x + obstacle["width"] - 7, y + 12,
                    x + obstacle["width"], y + 28, fill=color, outline="")
            else:
                self.canvas.create_text(
                    x + obstacle["width"] / 2, y + obstacle["height"] / 2,
                    text="🐦", font=("Segoe UI Emoji", 24), anchor="center")

        score = int(self.score)
        self.score_label.configure(
            text=f"SKOR {score:05d}   •   TERBAIK {self.best_score:05d}")
        if self.game_over:
            self.canvas.create_rectangle(
                width * 0.23, height * 0.35, width * 0.77, height * 0.66,
                fill="#fbf9f4", outline="#b85d76", width=2)
            self.canvas.create_text(
                width / 2, height * 0.43, text="KUCING TERSANDUNG!",
                fill=TEXT, font=("Segoe UI", 17, "bold"))
            self.canvas.create_text(
                width / 2, height * 0.55,
                text="Klik arena atau tekan Spasi untuk coba lagi",
                fill=MUTED, font=("Segoe UI", 10))

    def close(self):
        self.running = False
        if self.window.winfo_exists():
            self.window.destroy()


class SpiderGame:
    FRAME_INTERVAL = 1 / 20

    def __init__(self, root):
        self.root = root
        self.window = tk.Toplevel(root)
        self.window.title("WEB HERO • ALAKANG")
        self.window.configure(bg=BG)
        self.window.geometry("820x620")
        self.window.minsize(560, 470)
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        self.messages = queue.Queue()
        self.frames = queue.Queue(maxsize=1)
        self.stop_event = threading.Event()
        self.camera_thread = None
        self.camera_choices = {"Kamera 0": 0}
        self.camera_var = tk.StringVar(value="Kamera 0")
        self.preview_image = None
        self.camera_verified = False
        self.game_active = False
        self.last_tick = time.monotonic()
        self.spawn_timer = 1.0
        self.bullets = []
        self.webs = []
        self.score = 0
        self.misses = 0
        self.aim_y = 0.5

        header = tk.Frame(self.window, bg=BG, padx=14, pady=10)
        header.pack(fill="x")
        tk.Label(header, text="WEB HERO", bg=BG, fg=TEXT,
                 font=("Segoe UI", 14, "bold")).pack(side="left")
        self.score_label = tk.Label(
            header, text="SKOR 0   •   PELURU LEWAT 0/3   •   LEVEL 1",
            bg=BG, fg=MUTED, font=("Segoe UI", 9, "bold"))
        self.score_label.pack(side="right")

        camera_row = tk.Frame(self.window, bg=CARD, padx=10, pady=8)
        camera_row.pack(fill="x", padx=12)
        tk.Label(camera_row, text="Kamera", bg=CARD, fg=TEXT,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 6))
        self.camera_menu = tk.OptionMenu(
            camera_row, self.camera_var, *self.camera_choices.keys())
        self.camera_menu.configure(
            bg=BG, fg=TEXT, activebackground=BLUE, activeforeground="#ffffff",
            relief="flat", bd=0, highlightthickness=0, font=("Segoe UI", 9))
        self.camera_menu["menu"].configure(
            bg=CARD, fg=TEXT, activebackground=BLUE, activeforeground="#ffffff")
        self.camera_menu.pack(side="left", fill="x", expand=True)
        self.refresh_button = tk.Button(
            camera_row, text="Cari kamera", command=self.refresh_cameras,
            bg=BUTTON, fg="#ffffff", activebackground=BUTTON, relief="flat",
            bd=0, cursor="hand2", font=("Segoe UI", 9, "bold"), padx=9, pady=5)
        self.refresh_button.pack(side="left", padx=(7, 0))
        self.camera_button = tk.Button(
            camera_row, text="Verifikasi 2 tangan & mulai",
            command=self.start_or_restart, bg=BLUE, fg="#ffffff",
            activebackground=BLUE, relief="flat", bd=0, cursor="hand2",
            font=("Segoe UI", 9, "bold"), padx=9, pady=5)
        self.camera_button.pack(side="left", padx=(7, 0))
        self.camera_button.configure(state="disabled")

        camera_panel = tk.Frame(self.window, bg=CARD, padx=8, pady=7)
        camera_panel.pack(fill="x", padx=12, pady=(8, 0))
        self.preview = tk.Label(
            camera_panel, text="Preview kamera akan tampil di sini",
            bg="#202a3a", fg="#e8edf2", width=48, height=2,
            font=("Segoe UI", 9))
        self.preview.pack(side="left")
        self.status = tk.Label(
            camera_panel,
            text="Tunjukkan kedua telapak terbuka dan utuh di depan kamera.",
            bg=CARD, fg=MUTED, font=("Segoe UI", 9),
            wraplength=410, justify="left")
        self.status.pack(side="left", fill="x", expand=True, padx=10)

        self.canvas = tk.Canvas(
            self.window, bg="#172236", highlightthickness=0, takefocus=True)
        self.canvas.pack(fill="both", expand=True, padx=12, pady=(8, 0))
        footer = tk.Frame(self.window, bg=BG, padx=12, pady=8)
        footer.pack(fill="x")
        tk.Label(
            footer,
            text="Tahan kedua telapak saat verifikasi. 🤟 Angkat telunjuk dan kelingking, "
                 "lipat dua jari tengah untuk menembakkan jaring.",
            bg=BG, fg=MUTED, font=("Segoe UI", 8),
            wraplength=580, justify="left").pack(side="left", fill="x", expand=True)

        self.canvas.bind("<Configure>", self.draw)
        self.refresh_cameras()
        self.draw()
        self.window.after(120, self.poll)

    def refresh_cameras(self):
        self.refresh_button.configure(text="Mencari...", state="disabled")

        def scan():
            try:
                cameras = HandScrollDetector.list_cameras(max_devices=6)
                message = ("Kamera siap dipilih." if cameras else
                           "Kamera tidak ditemukan. Periksa koneksi dan izin kamera.")
            except Exception as error:
                cameras = []
                message = f"Pemindaian kamera gagal: {error}"
            try:
                self.root.after(0, lambda: self.update_cameras(cameras, message))
            except tk.TclError:
                return

        threading.Thread(target=scan, daemon=True).start()

    def update_cameras(self, cameras, message):
        if not self.window.winfo_exists():
            return
        self.refresh_button.configure(text="Cari kamera", state="normal")
        menu = self.camera_menu["menu"]
        menu.delete(0, "end")
        self.camera_choices = {
            f"{name}  (kamera {index})": index for index, name in cameras
        }
        if self.camera_choices:
            for label in self.camera_choices:
                menu.add_command(
                    label=label, command=lambda value=label: self.camera_var.set(value))
            self.camera_var.set(next(iter(self.camera_choices)))
            self.camera_menu.configure(state="normal")
            self.camera_button.configure(state="normal")
        else:
            self.camera_choices = {}
            menu.add_command(label="Tidak ada kamera", state="disabled")
            self.camera_var.set("Tidak ada kamera")
            self.camera_menu.configure(state="disabled")
            self.camera_button.configure(state="disabled")
        if not self.camera_verified:
            self.status.configure(text=message, fg=GREEN if cameras else RED)

    def start_or_restart(self):
        if self.camera_verified and self.camera_thread and self.camera_thread.is_alive():
            self.reset_round()
            return
        camera_index = self.camera_choices.get(self.camera_var.get())
        if camera_index is None:
            self.status.configure(text="Pilih kamera yang tersedia terlebih dahulu.", fg=RED)
            return
        self.stop_event.set()
        self.stop_event = threading.Event()
        self.camera_verified = False
        self.game_active = False
        self.reset_round()
        self.camera_button.configure(text="Menunggu verifikasi...", state="disabled")
        self.camera_menu.configure(state="disabled")
        self.refresh_button.configure(state="disabled")
        self.status.configure(
            text="Memulai kamera. Pastikan kedua telapak terbuka, utuh, dan terlihat.",
            fg=ACCENT)
        self.camera_thread = threading.Thread(
            target=self.camera_worker, args=(camera_index, self.stop_event), daemon=True)
        self.camera_thread.start()

    def camera_worker(self, camera_index, stop_event):
        camera = None
        detector = None
        try:
            import cv2
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision

            model_path = ensure_hand_model()
            if sys.platform == "win32" and hasattr(cv2, "CAP_DSHOW"):
                camera = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
            if camera is None or not camera.isOpened():
                if camera:
                    camera.release()
                camera = cv2.VideoCapture(camera_index)
            if not camera.isOpened():
                raise RuntimeError(f"Kamera {camera_index} tidak bisa dibuka.")
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, 480)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)
            camera.set(cv2.CAP_PROP_FPS, 20)
            if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
                camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            options = vision.HandLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=str(model_path)),
                running_mode=vision.RunningMode.VIDEO,
                num_hands=2,
                min_hand_detection_confidence=0.6,
                min_hand_presence_confidence=0.6,
                min_tracking_confidence=0.55,
            )
            detector = vision.HandLandmarker.create_from_options(options)
            self.messages.put(("status", "Kamera aktif. Verifikasi kedua tangan..."))

            verified = False
            both_hands_since = None
            last_prompt = 0.0
            previous_gesture = False
            previous_timestamp = -1
            next_detection = 0.0
            while not stop_event.is_set():
                ok, frame = camera.read()
                if not ok:
                    raise RuntimeError("Kamera terputus saat game berjalan.")
                now = time.monotonic()
                if now < next_detection:
                    continue
                next_detection = now + self.FRAME_INTERVAL

                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                timestamp = max(int(now * 1000), previous_timestamp + 1)
                previous_timestamp = timestamp
                result = detector.detect_for_video(
                    mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), timestamp)
                hands = result.hand_landmarks or []
                valid_pair = (
                    len(hands) == 2
                    and all(HandScrollDetector._hand_structure_status(hand) is None
                            and HandScrollDetector._is_open_palm(hand)
                            for hand in hands)
                )
                if not verified:
                    if valid_pair:
                        both_hands_since = both_hands_since or now
                        if now - both_hands_since >= 0.9:
                            verified = True
                            self.messages.put((
                                "verified",
                                "Kedua tangan terverifikasi. Game dimulai—tangkap peluru dengan 🤟.",
                            ))
                    else:
                        both_hands_since = None
                        if now - last_prompt > 1:
                            last_prompt = now
                            prompt = (
                                "Terlihat satu tangan; tampilkan kedua telapak."
                                if len(hands) == 1 else
                                "Buka kedua telapak, rentangkan ibu jari, dan pastikan semua jari terlihat."
                            )
                            self.messages.put(("status", prompt))
                elif len(hands) < 2:
                    if now - last_prompt > 1:
                        last_prompt = now
                        self.messages.put((
                            "status", "Game aktif. Tampilkan lagi kedua tangan untuk mengontrol jaring."))

                for hand in hands:
                    for start, end in HAND_CONNECTIONS:
                        first, second = hand[start], hand[end]
                        cv2.line(
                            frame,
                            (int(first.x * frame.shape[1]), int(first.y * frame.shape[0])),
                            (int(second.x * frame.shape[1]), int(second.y * frame.shape[0])),
                            (90, 210, 170), 2)
                    for point in hand:
                        cv2.circle(
                            frame, (int(point.x * frame.shape[1]),
                                    int(point.y * frame.shape[0])),
                            3, (245, 220, 160), -1)

                spider_hand = next(
                    (hand for hand in hands if self.is_spider_gesture(hand)), None)
                gesture = verified and spider_hand is not None
                if gesture and not previous_gesture:
                    aim = sum(spider_hand[index].y for index in (8, 20)) / 2
                    self.messages.put(("shot", aim))
                previous_gesture = gesture
                self.store_frame(rgb)
        except ImportError as error:
            self.messages.put((
                "error", f"Paket {error.name} tidak tersedia. Instalasikan requirements.txt."
            ))
        except Exception as error:
            self.messages.put(("error", f"Kamera game gagal: {error}"))
        finally:
            if detector is not None:
                detector.close()
            if camera is not None:
                camera.release()

    @staticmethod
    def is_spider_gesture(landmarks):
        wrist = landmarks[0]

        def distance(first, second):
            return math.hypot(first.x - second.x, first.y - second.y)

        index_extended = distance(landmarks[8], wrist) > distance(landmarks[6], wrist) * 1.08
        middle_folded = distance(landmarks[12], wrist) < distance(landmarks[10], wrist) * 1.12
        ring_folded = distance(landmarks[16], wrist) < distance(landmarks[14], wrist) * 1.12
        pinky_extended = distance(landmarks[20], wrist) > distance(landmarks[18], wrist) * 1.08
        thumb_extended = distance(landmarks[4], wrist) > distance(landmarks[3], wrist) * 1.04
        return (index_extended and middle_folded and ring_folded
                and pinky_extended and thumb_extended)

    def store_frame(self, frame):
        try:
            self.frames.put_nowait(frame)
        except queue.Full:
            try:
                self.frames.get_nowait()
            except queue.Empty:
                pass
            try:
                self.frames.put_nowait(frame)
            except queue.Full:
                pass

    def poll(self):
        if not self.window.winfo_exists():
            return
        try:
            while True:
                kind, value = self.messages.get_nowait()
                if kind == "status":
                    self.status.configure(text=value, fg=ACCENT)
                elif kind == "verified":
                    self.camera_verified = True
                    self.camera_button.configure(text="Mulai ulang", state="normal")
                    self.reset_round()
                    self.status.configure(text=value, fg=GREEN)
                elif kind == "shot":
                    self.aim_y = max(0.08, min(0.92, float(value)))
                    if self.game_active:
                        height = max(1, self.canvas.winfo_height())
                        self.webs.append({
                            "x": 92, "y": self.aim_y * height, "speed": 780,
                        })
                elif kind == "error":
                    self.status.configure(text=value, fg=RED)
                    self.camera_button.configure(
                        text="Coba verifikasi lagi", state="normal")
                    self.camera_menu.configure(state="normal")
                    self.refresh_button.configure(state="normal")
                    self.camera_verified = False
                    self.game_active = False
        except queue.Empty:
            pass

        frame = None
        try:
            while True:
                frame = self.frames.get_nowait()
        except queue.Empty:
            pass
        if frame is not None:
            preview = Image.fromarray(frame).resize((160, 120), Image.Resampling.BILINEAR)
            self.preview_image = ImageTk.PhotoImage(preview)
            self.preview.configure(image=self.preview_image, text="", width=160, height=120)

        now = time.monotonic()
        elapsed = min(now - self.last_tick, 0.05)
        self.last_tick = now
        if self.game_active:
            self.update_round(elapsed)
            self.draw()
        delay = 33 if self.game_active or (
            self.camera_thread and self.camera_thread.is_alive()) else 250
        self.window.after(delay, self.poll)

    def reset_round(self):
        self.score = 0
        self.misses = 0
        self.bullets = []
        self.webs = []
        self.spawn_timer = 0.7
        self.game_active = self.camera_verified
        self.last_tick = time.monotonic()
        self.draw()

    def update_round(self, elapsed):
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        level = self.score // 10 + 1
        bullet_speed = 230 + min(450, (level - 1) * 38)
        self.spawn_timer -= elapsed
        if self.spawn_timer <= 0:
            self.bullets.append({
                "x": width + 20, "y": random.randint(70, max(85, height - 38)),
            })
            self.spawn_timer = max(0.42, 1.28 - (level - 1) * 0.075)

        for bullet in self.bullets:
            bullet["x"] -= bullet_speed * elapsed
        for web in self.webs:
            web["x"] += web["speed"] * elapsed

        remaining_bullets = []
        remaining_webs = []
        for bullet in self.bullets:
            hit_web_index = next((
                index for index, web in enumerate(self.webs)
                if abs(web["x"] - bullet["x"]) < 24
                and abs(web["y"] - bullet["y"]) < 34
            ), None)
            if hit_web_index is not None:
                self.webs.pop(hit_web_index)
                self.score += 1
            elif bullet["x"] < 65:
                self.misses += 1
                if self.misses >= 3:
                    self.game_active = False
                    self.status.configure(
                        text=f"Tiga peluru lolos! Skor akhir: {self.score}. "
                             "Tekan Mulai ulang untuk mencoba lagi.",
                        fg=RED)
                else:
                    remaining_bullets.append(bullet)
            else:
                remaining_bullets.append(bullet)
        self.bullets = remaining_bullets
        self.webs = [web for web in self.webs if web["x"] < width + 20]

    def draw(self, _event=None):
        if not self.canvas.winfo_exists():
            return
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        self.canvas.delete("all")
        self.canvas.create_rectangle(0, 0, width, height, fill="#172236", outline="")
        ground = height - 28
        for index, building in enumerate((0.16, 0.38, 0.67, 0.87)):
            building_width = max(42, int(width * 0.1))
            building_height = int(height * (0.25 + (index % 2) * 0.12))
            left = width * building - building_width / 2
            top = ground - building_height
            self.canvas.create_rectangle(
                left, top, left + building_width, ground,
                fill="#25344c", outline="")
            for window_y in range(int(top + 12), int(ground - 8), 20):
                for window_x in range(int(left + 8), int(left + building_width - 5), 18):
                    self.canvas.create_rectangle(
                        window_x, window_y, window_x + 5, window_y + 7,
                        fill="#657b91", outline="")
        self.canvas.create_line(0, ground, width, ground, fill="#637b9d", width=2)
        self.canvas.create_text(
            27, height * self.aim_y, text="🕸", fill="#e9e3da",
            font=("Segoe UI Emoji", 25))
        self.canvas.create_line(
            39, height * self.aim_y, 76, height * self.aim_y,
            fill="#b85d76", width=4)
        for bullet in self.bullets:
            self.canvas.create_oval(
                bullet["x"] - 10, bullet["y"] - 10,
                bullet["x"] + 10, bullet["y"] + 10,
                fill="#ee7a70", outline="#ffd2a8", width=2)
            self.canvas.create_line(
                bullet["x"] + 12, bullet["y"], bullet["x"] + 42,
                bullet["y"], fill="#ee7a70", width=3)
        for web in self.webs:
            self.canvas.create_line(
                web["x"] - 22, web["y"] - 12, web["x"] + 22, web["y"] + 12,
                fill="#f3ede1", width=2)
            self.canvas.create_line(
                web["x"] - 22, web["y"] + 12, web["x"] + 22, web["y"] - 12,
                fill="#f3ede1", width=2)
        if self.game_active:
            message = "TANGKAP PELURU DENGAN JARING!"
        elif self.camera_verified and self.misses >= 3:
            message = "GAME OVER — 3 PELURU LOLOS"
        else:
            message = "VERIFIKASI DUA TANGAN UNTUK MULAI"
        self.canvas.create_text(
            width / 2, 27, text=message, fill="#e9e3da",
            font=("Segoe UI", 11, "bold"))
        self.score_label.configure(
            text=f"SKOR {self.score}   •   PELURU LEWAT {self.misses}/3   "
                 f"•   LEVEL {self.score // 10 + 1}")

    def close(self):
        self.game_active = False
        self.stop_event.set()
        if self.window.winfo_exists():
            self.window.destroy()
