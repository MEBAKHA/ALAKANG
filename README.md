# ALAKANG

> A lightweight Windows desktop companion for animated video wallpapers, hand gestures, and quick breaks.

ALAKANG lets you use a local video or a supported online video as a desktop wallpaper. It also brings together webcam-based hand controls, floating stickers, Spotify playlist shortcuts, and two small games in one desktop app.

The interface is designed to be easy to navigate, including for first-time users. Video playback is handled by [mpv](https://mpv.io/), a separate media player installed on your computer.

## GitHub repository description

Use this text in GitHub's **Description** field:

> A lightweight Windows desktop companion for video wallpapers, webcam hand controls, floating stickers, Spotify shortcuts, and mini-games.

## Features

- **Animated wallpapers:** Play a local video or enter a supported online video URL. Videos loop automatically.
- **Resume playback:** Save the last playback position and continue from it.
- **Windows startup:** Optionally restore the wallpaper when you sign in to Windows. The computer must be on and signed in; a wallpaper cannot keep playing while the laptop is shut down.
- **Hand controls:** Use a webcam and MediaPipe hand tracking to scroll with an index-finger gesture. Camera frames are processed locally by the app.
- **Floating desktop extras:** Add a custom image sticker and a Spotify playlist shortcut.
- **Mini-games:** Play Kucing Dash, a cat-themed obstacle runner, or WEB HERO, a webcam-controlled hand-gesture game.
- **Performance-minded playback:** Online sources are limited to up to 1080p and 30 FPS, with H.264 preferred when available. Hardware decoding is requested when supported.

Actual playback smoothness depends on your video, internet connection, graphics hardware, and other running apps. Local videos keep their original quality, so large or high-resolution files may need more system resources.

## Requirements

- Windows 10 or Windows 11 (64-bit).
- Python 3.13 (64-bit), with Tkinter included. Python 3.13.4 was used to verify this setup.
- Git, to clone the repository.
- mpv installed separately.
- A webcam for hand controls and WEB HERO. The wallpaper and Kucing Dash do not require a webcam.
- An internet connection to install Python packages, use online video sources, or download the hand-tracking model the first time a webcam feature is used.

## Install and run

Follow these steps in **Windows PowerShell**.

### 1. Install Git and Python

Install Git for Windows and Python 3.13 (64-bit):

- [Git for Windows](https://git-scm.com/download/win)
- [Python for Windows](https://www.python.org/downloads/windows/)

During Python setup, enable the option to install the Python launcher (`py`). Make sure **Tcl/Tk and IDLE** is selected so that Tkinter is available.

Open a new PowerShell window and check the installations:

```powershell
git --version
py -3.13 --version
```

### 2. Install mpv

ALAKANG needs the separate `mpv.exe` program to display video wallpapers. One option is [Scoop](https://scoop.sh/). After installing Scoop using its official instructions, run:

```powershell
scoop bucket add extras
scoop install mpv
mpv --version
```

If you install mpv another way, make sure `mpv.exe` is on your `PATH` or installed in a location the app can find, such as `C:\mpv\mpv.exe`.

### 3. Clone the repository

Replace `YOUR-USERNAME` with your GitHub username:

```powershell
git clone https://github.com/YOUR-USERNAME/ALAKANG.git
cd ALAKANG
```

### 4. Create an environment and install Python packages

Run these commands from the repository folder:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The virtual environment keeps ALAKANG's packages separate from other Python projects on your computer.

### 5. Check the environment and launch ALAKANG

First, check that the required webcam-related Python packages can be imported:

```powershell
.\.venv\Scripts\python.exe .\semangat_wallpaper.py --check-env
```

Then start the app:

```powershell
.\.venv\Scripts\python.exe .\semangat_wallpaper.py
```

The launcher is named `semangat_wallpaper.py` for compatibility with the current project; the app itself is named **ALAKANG**. On Windows, the launcher uses the repository's `.venv` automatically when it is present.

## Set up a wallpaper

The current app interface is in Indonesian. English translations are included below so you can match each instruction to the button on screen.

1. Open ALAKANG.
2. Select **Pilih file** (Choose file) to choose a video already on your computer, or paste a supported online video URL into the source field.
3. Select **Simpan** (Save).
4. Select **Nyalakan wallpaper** (Start wallpaper).
5. Use **Lanjutkan** (Resume) to continue from a saved position, or **Mulai dari awal** (Start from beginning) to restart the video.

For offline playback, select a video file that is already stored on your computer. An online URL needs an internet connection and may stop working if the source changes or is unavailable.

To restore the wallpaper after Windows sign-in, enable **Nyalakan wallpaper otomatis saat masuk Windows** (Start wallpaper automatically when I sign in to Windows) in Preferences. The video itself stops when the computer shuts down; it can resume only after Windows starts and you sign in.

The global shortcut **Ctrl+Alt+W** toggles the wallpaper.

## Use hand controls and games

### Hand scrolling

1. Connect a webcam and close other apps that may be using it.
2. Select a camera in **SCROLL ACTIVE** and choose **Verifikasi kamera & tangan** (Verify camera and hand).
3. Hold an open palm fully in view until verification completes.
4. Choose the button to enable hand scrolling. Raise your index finger and move it up or down to scroll the page under the mouse pointer. Open your palm to stop scrolling.

The first webcam use downloads a MediaPipe hand-tracking model and caches it on your computer. The app processes webcam frames locally; it does not upload those frames.

### Kucing Dash

Open **Kucing Dash**, then press **Space** or click the game area to jump over obstacles. Select **Mulai ulang** (Restart) to play again.

### WEB HERO

Open **WEB HERO**, select a camera, and choose **Verifikasi 2 tangan & mulai** (Verify both hands and start). Hold both open hands in view until they are verified. Make the spider gesture by extending your index finger and pinky while folding your middle and ring fingers. Aim at incoming bullets; three missed bullets end the game. Difficulty increases as your score grows.

## Performance and video quality

- Online playback is limited to 1080p and 30 FPS, and prefers H.264 when the source provides it.
- The app requests safe hardware decoding through mpv when your system supports it.
- Local videos are not automatically reduced in resolution. If a local file stutters, try a lower-resolution or lower-bitrate copy.
- Online playback needs a stable connection. Buffering can still happen if the connection or video host is slow.
- Close other camera applications before using hand controls or WEB HERO if the webcam is unavailable.

These settings are intended to balance quality and system load. They cannot guarantee smooth playback on every computer or with every video.

## Troubleshooting

### "mpv tidak ditemukan" / mpv is not found

Install mpv, then check `mpv --version` in a new PowerShell window. If Windows cannot find the command, add mpv to `PATH` or install `mpv.exe` in one of the locations listed above.

### A Python package is missing

Make sure you ran the install command from the repository folder, and use the Python executable inside `.venv`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### The camera is not available

Check Windows camera privacy settings, close other apps that use the webcam, and use **Cari** or **Cari kamera** to scan again. The camera must be enabled for desktop apps.

### A video is not playing or is stuttering

Confirm that the file plays in mpv. For online sources, check your connection and update yt-dlp inside the environment:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade yt-dlp
```

For local files, try a smaller 1080p/30 FPS copy. Some codecs or high-bitrate videos may be too demanding for a particular computer.

### The wallpaper does not return after a restart

Enable the automatic startup option in ALAKANG and make sure you sign in to the same Windows account. The selected local video must still be in the same location.

## Project files

```text
semangat_wallpaper.py       App launcher
requirements.txt            Python dependencies
wallpaper_app/
  config.py                 Settings and shared UI colors
  engine.py                 mpv playback and Windows startup integration
  games.py                  Kucing Dash and WEB HERO
  gui.py                    Main ALAKANG interface
  scroll_detector.py        Webcam hand detection and scrolling
```

## Notes

- This project is actively developed. Some online video sources, camera drivers, and graphics hardware may behave differently.
- Only use video sources and media that you are allowed to access and use. ALAKANG does not bypass DRM or other access controls.
- The project does not include an installer; run it from the cloned folder using the steps above.
