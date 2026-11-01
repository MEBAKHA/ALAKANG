"""Deteksi gerakan tangan untuk mengirim scroll ke aplikasi desktop."""

import queue
import sys
import threading
import time
from urllib.request import Request, urlopen

from .config import LOG


MODEL_PATH = LOG.parent / "semangat_wallpaper" / "hand_landmarker.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)
HAND_CONNECTIONS = (
    (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15),
    (15, 16), (13, 17), (0, 17), (17, 18), (18, 19), (19, 20),
)


def ensure_hand_model(messages=None):
    if MODEL_PATH.is_file() and MODEL_PATH.stat().st_size > 0:
        return MODEL_PATH

    if messages is not None:
        messages.put(("ready", "Mengunduh model detector tangan (pertama kali saja)..."))
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = MODEL_PATH.with_suffix(".task.download")
    request = Request(MODEL_URL, headers={"User-Agent": "SemangatWallpaper/1.0"})
    try:
        with urlopen(request, timeout=30) as response:
            model_data = response.read(20 * 1024 * 1024 + 1)
        if len(model_data) > 20 * 1024 * 1024:
            raise ValueError("File model detector terlalu besar.")
        if not model_data:
            raise ValueError("File model detector kosong.")
        temporary_path.write_bytes(model_data)
        temporary_path.replace(MODEL_PATH)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return MODEL_PATH


class HandScrollDetector:
    """Reads a webcam in a worker thread and converts vertical hand motion to scroll."""

    # Movement speed controls scroll speed; partial wheel events keep it smooth.
    MIN_SCROLL_INTERVAL = 0.02
    MIN_HAND_SPEED = 0.05
    SPEED_TO_WHEEL_DELTA = 36
    MAX_WHEEL_DELTA = 54
    LANDMARK_SMOOTHING = 0.68
    VELOCITY_SMOOTHING = 0.52
    MIN_FRAME_INTERVAL = 1 / 20

    def __init__(self):
        self.messages = queue.Queue()
        self.frames = queue.Queue(maxsize=1)
        self._stop_event = threading.Event()
        self._scroll_enabled = threading.Event()
        self._thread = None
        self.camera_index = 0

    @staticmethod
    def list_cameras(max_devices=8):
        """Return (OpenCV index, friendly name) pairs for available cameras."""
        import cv2

        try:
            from pygrabber.dshow_graph import FilterGraph
            device_names = FilterGraph().get_input_devices()
        except (ImportError, OSError, RuntimeError):
            device_names = []

        available = []
        for index in range(max_devices):
            camera = None
            try:
                if sys.platform == "win32" and hasattr(cv2, "CAP_DSHOW"):
                    camera = cv2.VideoCapture(index, cv2.CAP_DSHOW)
                if camera is None or not camera.isOpened():
                    if camera:
                        camera.release()
                    camera = cv2.VideoCapture(index)
                if camera.isOpened():
                    name = (device_names[index] if index < len(device_names)
                            else f"Webcam {index + 1}")
                    available.append((index, name))
            except Exception:
                pass
            finally:
                if camera is not None:
                    camera.release()
        return available

    def start(self, camera_index=0):
        if self._thread and self._thread.is_alive():
            return
        self.camera_index = int(camera_index)
        self._stop_event.clear()
        self._scroll_enabled.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def set_scrolling(self, enabled):
        if enabled:
            self._scroll_enabled.set()
        else:
            self._scroll_enabled.clear()

    def stop(self):
        self._stop_event.set()

    def _send_frame(self, frame):
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

    def _ensure_model(self):
        return ensure_hand_model(self.messages)

    @staticmethod
    def _is_index_pointing(landmarks):
        """Detect a raised index finger while the other three fingers are folded."""
        wrist = landmarks[0]

        def distance(first, second):
            return ((first.x - second.x) ** 2 + (first.y - second.y) ** 2) ** 0.5

        index_extended = distance(landmarks[8], wrist) > distance(landmarks[6], wrist) * 1.08
        other_fingers_folded = all(
            distance(landmarks[tip], wrist) < distance(landmarks[pip], wrist) * 1.12
            for tip, pip in ((12, 10), (16, 14), (20, 18))
        )
        return index_extended and other_fingers_folded

    @staticmethod
    def _is_open_palm(landmarks):
        """Detect 🤚 when all four non-thumb fingers are extended."""
        wrist = landmarks[0]

        def distance(first, second):
            return ((first.x - second.x) ** 2 + (first.y - second.y) ** 2) ** 0.5

        extended_fingers = sum(
            distance(landmarks[tip], wrist) > distance(landmarks[pip], wrist) * 1.08
            for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18))
        )
        return extended_fingers == 4

    @classmethod
    def _hand_structure_status(cls, landmarks):
        """Return None when the complete hand structure is visible and plausible."""
        if len(landmarks) != 21:
            return "Pastikan seluruh tangan terlihat di kamera."

        if any(not (0.015 <= point.x <= 0.985 and 0.015 <= point.y <= 0.985)
               for point in landmarks):
            return "Tangan terpotong. Mundurkan tangan agar semua jari masuk ke frame."

        xs = [point.x for point in landmarks]
        ys = [point.y for point in landmarks]
        if max(xs) - min(xs) < 0.12 or max(ys) - min(ys) < 0.16:
            return "Tangan terlalu jauh atau kurang jelas. Dekatkan telapak ke kamera."

        if not cls._is_open_palm(landmarks):
            return "Buka semua jari dan hadapkan telapak ke kamera."

        thumb, index_tip = landmarks[4], landmarks[8]
        palm_width = ((landmarks[5].x - landmarks[17].x) ** 2 +
                      (landmarks[5].y - landmarks[17].y) ** 2) ** 0.5
        thumb_gap = ((thumb.x - index_tip.x) ** 2 +
                     (thumb.y - index_tip.y) ** 2) ** 0.5
        wrist = landmarks[0]
        thumb_tip_reach = ((thumb.x - wrist.x) ** 2 +
                           (thumb.y - wrist.y) ** 2) ** 0.5
        thumb_joint_reach = ((landmarks[3].x - wrist.x) ** 2 +
                             (landmarks[3].y - wrist.y) ** 2) ** 0.5
        if thumb_tip_reach < thumb_joint_reach * 1.08:
            return "Rentangkan ibu jari."
        if palm_width <= 0 or thumb_gap < palm_width * 0.28:
            return "Rentangkan ibu jari menjauh dari telunjuk agar semua jari terverifikasi."
        return None

    @staticmethod
    def _send_scroll_delta(delta, pyautogui):
        """Send a fine-grained Windows wheel delta; use notches elsewhere."""
        if sys.platform != "win32":
            pyautogui.scroll(1 if delta > 0 else -1)
            return

        x, y = pyautogui.position()
        width, height = pyautogui.size()
        if pyautogui.FAILSAFE and (x <= 0 or y <= 0 or x >= width - 1 or y >= height - 1):
            raise pyautogui.FailSafeException(
                "Mouse berada di pojok layar (FailSafe PyAutoGUI). "
                "Pindahkan pointer dari pojok lalu aktifkan ulang scroll.")

        import ctypes
        ctypes.windll.user32.mouse_event(0x0800, 0, 0, delta & 0xFFFFFFFF, 0)

    @classmethod
    def _wheel_delta_for_velocity(cls, velocity):
        """Map vertical hand speed to a signed, capped wheel delta."""
        if abs(velocity) < cls.MIN_HAND_SPEED:
            return 0
        amount = round(min(
            cls.MAX_WHEEL_DELTA,
            max(3, abs(velocity) * cls.SPEED_TO_WHEEL_DELTA),
        ))
        return amount if velocity > 0 else -amount

    def _run(self):
        try:
            import cv2
            import mediapipe as mp
            import pyautogui
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision
        except ImportError as error:
            self.messages.put((
                "error",
                f"Paket {error.name} tidak ada di Python yang menjalankan aplikasi. "
                "Tutup lalu jalankan semangat_wallpaper.py; launcher akan memilih .venv "
                "otomatis. Jika .venv belum ada, pasang requirements.txt di environment itu.",
            ))
            return

        camera = None
        detector = None
        try:
            model_path = self._ensure_model()
            if sys.platform == "win32" and hasattr(cv2, "CAP_DSHOW"):
                camera = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            if camera is None or not camera.isOpened():
                if camera:
                    camera.release()
                camera = cv2.VideoCapture(self.camera_index)
            if not camera.isOpened():
                self.messages.put((
                    "error", f"Kamera {self.camera_index} tidak bisa dibuka. "
                    "Periksa koneksi/izin kamera atau pilih kamera lain."))
                return

            camera.set(cv2.CAP_PROP_FRAME_WIDTH, 480)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)
            if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
                camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            options = vision.HandLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=str(model_path)),
                running_mode=vision.RunningMode.VIDEO,
                num_hands=1,
                min_hand_detection_confidence=0.65,
                min_hand_presence_confidence=0.65,
                min_tracking_confidence=0.6,
            )
            detector = vision.HandLandmarker.create_from_options(options)
            self.messages.put((
                "ready", "Kamera aktif. Buka telapak penuh menghadap kamera untuk verifikasi."))

            previous_y = None
            previous_motion_time = None
            smoothed_y = None
            smoothed_velocity = 0.0
            last_scroll_time = 0.0
            was_tracking = False
            verification_complete = False
            verification_started = None
            verification_message = None
            frame_count = 0
            previous_timestamp_ms = -1
            next_detection_time = 0.0
            active_gesture = None
            gesture_candidate = None
            gesture_candidate_frames = 0

            while not self._stop_event.is_set():
                ok, frame = camera.read()
                if not ok:
                    if not self._stop_event.is_set():
                        self.messages.put(("error", "Kamera terputus. Scroll tangan dimatikan."))
                    return

                now = time.monotonic()
                if now < next_detection_time:
                    continue
                next_detection_time = now + self.MIN_FRAME_INTERVAL

                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                timestamp_ms = max(int(time.monotonic() * 1000), previous_timestamp_ms + 1)
                previous_timestamp_ms = timestamp_ms
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                result = detector.detect_for_video(mp_image, timestamp_ms)
                if result.hand_landmarks:
                    landmarks = result.hand_landmarks[0]
                    if not verification_complete:
                        structure_problem = self._hand_structure_status(landmarks)
                        if structure_problem:
                            verification_started = None
                            if structure_problem != verification_message:
                                self.messages.put(("verification", structure_problem))
                                verification_message = structure_problem
                        else:
                            verification_started = verification_started or now
                            remaining = max(0.0, 0.8 - (now - verification_started))
                            if remaining > 0:
                                status = f"Struktur tangan terlihat. Tahan telapak... {remaining:.1f} dtk"
                                if status != verification_message:
                                    self.messages.put(("verification", status))
                                    verification_message = status
                            else:
                                verification_complete = True
                                self.messages.put((
                                    "verification_complete",
                                    "Verifikasi selesai ✓ Semua 21 titik dan 5 jari terlihat. "
                                    "Angkat ☝️ telunjuk untuk scroll, buka 🤚 telapak untuk berhenti.",
                                ))

                    palm_points = [landmarks[index] for index in (0, 5, 9, 13, 17)]
                    current_y = sum(point.y for point in palm_points) / len(palm_points)
                    point_x = sum(point.x for point in palm_points) / len(palm_points)
                    smoothed_y = current_y if smoothed_y is None else (
                        self.LANDMARK_SMOOTHING * smoothed_y
                        + (1 - self.LANDMARK_SMOOTHING) * current_y)
                    cv2.circle(
                        frame,
                        (int(point_x * frame.shape[1]), int(smoothed_y * frame.shape[0])),
                        10, (61, 220, 132), -1)
                    detected_gesture = (
                        "open" if self._is_open_palm(landmarks)
                        else "index" if self._is_index_pointing(landmarks)
                        else None
                    )
                    if detected_gesture == "open":
                        gesture_candidate = "open"
                        gesture_candidate_frames = 0
                        if active_gesture != "open":
                            active_gesture = "open"
                            previous_y = None
                            previous_motion_time = None
                            smoothed_velocity = 0.0
                            self.messages.put(("gesture", "Telapak terbuka 🤚 — scroll berhenti."))
                    elif detected_gesture != gesture_candidate:
                        gesture_candidate = detected_gesture
                        gesture_candidate_frames = 1
                    else:
                        gesture_candidate_frames += 1

                    if (detected_gesture == "index" and gesture_candidate_frames >= 2
                            and active_gesture != "index"):
                        active_gesture = "index"
                        previous_y = landmarks[8].y
                        previous_motion_time = now
                        smoothed_velocity = 0.0
                        status = (
                            "Telunjuk ☝️ terdeteksi — gerakkan ujung jari naik/turun untuk scroll."
                            if self._scroll_enabled.is_set()
                            else "Telunjuk terdeteksi. Aktifkan scroll pada panel dulu."
                        )
                        self.messages.put(("gesture", status))
                    elif (detected_gesture is None and gesture_candidate_frames >= 3
                          and active_gesture == "index"):
                        active_gesture = None
                        previous_y = None
                        previous_motion_time = None
                        smoothed_velocity = 0.0
                        self.messages.put(("gesture", "Telunjuk tidak terdeteksi — scroll berhenti."))

                    scroll_y = landmarks[8].y if active_gesture == "index" else smoothed_y
                    if (self._scroll_enabled.is_set() and active_gesture == "index"
                            and previous_y is not None):
                        movement = previous_y - scroll_y
                        elapsed = max(now - previous_motion_time, 1 / 120) if previous_motion_time else 1 / 30
                        instant_velocity = movement / elapsed
                        smoothed_velocity = (
                            self.VELOCITY_SMOOTHING * smoothed_velocity
                            + (1 - self.VELOCITY_SMOOTHING) * instant_velocity
                        )
                        delta = self._wheel_delta_for_velocity(smoothed_velocity)
                        if delta and now - last_scroll_time >= self.MIN_SCROLL_INTERVAL:
                            try:
                                self._send_scroll_delta(delta, pyautogui)
                            except pyautogui.FailSafeException as error:
                                raise RuntimeError(str(error)) from error
                            last_scroll_time = now
                            direction = "bawah" if delta < 0 else "atas"
                            self.messages.put((
                                "scroll", f"Scroll adaptif ke {direction} terkirim. "
                                "Gerakan tangan menentukan kecepatannya."))
                        previous_motion_time = now
                    if active_gesture == "index":
                        previous_y = scroll_y
                    elif active_gesture == "open":
                        previous_y = None
                        previous_motion_time = None
                    if not was_tracking:
                        self.messages.put((
                            "tracking", "Tangan terlihat. Verifikasi berhasil; gerakkan tangan untuk scroll."))
                    was_tracking = True
                    instruction = (
                        "🤚 TELAPAK TERBUKA - SCROLL BERHENTI"
                        if active_gesture == "open"
                        else (
                            "☝️ GERAKKAN TELUNJUK NAIK / TURUN"
                            if active_gesture == "index" and self._scroll_enabled.is_set()
                            else "TANGAN TERVERIFIKASI - ANGKAT TELUNJUK"
                        )
                    )
                    cv2.putText(
                        frame, instruction, (12, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (61, 220, 132), 2)

                    for start, end in HAND_CONNECTIONS:
                        start_point = landmarks[start]
                        end_point = landmarks[end]
                        start_xy = (int(start_point.x * frame.shape[1]),
                                    int(start_point.y * frame.shape[0]))
                        end_xy = (int(end_point.x * frame.shape[1]),
                                  int(end_point.y * frame.shape[0]))
                        cv2.line(frame, start_xy, end_xy, (61, 220, 132), 2)
                    for point in landmarks:
                        cv2.circle(
                            frame, (int(point.x * frame.shape[1]),
                                    int(point.y * frame.shape[0])),
                            3, (255, 255, 255), -1)
                else:
                    previous_y = None
                    smoothed_y = None
                    previous_motion_time = None
                    smoothed_velocity = 0.0
                    if was_tracking:
                        self.messages.put(("tracking", "Tangan tidak terlihat. Tunjukkan lagi ke kamera."))
                    was_tracking = False
                    active_gesture = None
                    gesture_candidate = None
                    gesture_candidate_frames = 0
                    if not verification_complete:
                        verification_started = None
                        if verification_message != "Tangan belum terlihat. Letakkan telapak terbuka di depan kamera.":
                            verification_message = "Tangan belum terlihat. Letakkan telapak terbuka di depan kamera."
                            self.messages.put(("verification", verification_message))
                    cv2.putText(
                        frame, "Tunjukkan telapak tangan ke kamera", (12, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (230, 237, 242), 2)

                frame_count += 1
                if frame_count % 3 == 0:
                    self._send_frame(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        except Exception as error:
            self.messages.put(("error", f"Detector scroll berhenti: {error}"))
        finally:
            if detector is not None:
                detector.close()
            if camera is not None:
                camera.release()
