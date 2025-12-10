"""
video_recorder_full.py

Full-featured recorder with:
- first-run device selection (ffmpeg DirectShow)
- hidden device menu (Ctrl+D) to change devices
- splash playback via ffplay (storage/splash.mp4)
- embedded camera preview (OpenCV -> Tkinter)
- MP4 recording with audio via ffmpeg (DirectShow)
- manual Stop or 60s max recording
- approve/reject/move logic with 30s post-record timeout
- directories auto-created and delete_daily cleanup at startup
- logs to logs/actions.log
"""

import os, sys, time, json, shutil, threading, subprocess, tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from PIL import Image, ImageTk
import cv2
import datetime

# ---------- CONFIG ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

STORAGE_DIR = os.path.join(BASE_DIR, "storage")
INBOUND_DIR = os.path.join(BASE_DIR, "inbound")
APPROVED_DIR = os.path.join(BASE_DIR, "approved")
DELETE_DAILY_DIR = os.path.join(BASE_DIR, "delete_daily")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

SPLASH_FILENAME = "splash.mp4"
SPLASH_PATH = os.path.join(STORAGE_DIR, SPLASH_FILENAME)

FFMPEG_CMD = "ffmpeg"
FFPLAY_CMD = "ffplay"

MAX_RECORD_SECONDS = 60
POST_RECORD_TIMEOUT = 30
PREVIEW_MAX_W = 960
PREVIEW_MAX_H = 540

FALLBACK_VIDEO_DEVICE = "USB Camera"
FALLBACK_AUDIO_DEVICE = "Microphone (USB 2.0 Camera)"

# ---------- Ensure directories ----------
for d in (STORAGE_DIR, INBOUND_DIR, APPROVED_DIR, DELETE_DAILY_DIR, LOGS_DIR):
    os.makedirs(d, exist_ok=True)

# ---------- Logging ----------
LOG_FILE = os.path.join(LOGS_DIR, "actions.log")
def log(msg):
    ts = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")
    line = f"[{ts}] {msg}"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception: pass
    print(line)

# ---------- Utilities ----------
def safe_move(src, dst_dir, retries=6, delay=0.4):
    if not src or not os.path.exists(src): return False
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, os.path.basename(src))
    for attempt in range(retries):
        try:
            shutil.move(src, dst)
            log(f"Moved {src} -> {dst}")
            return True
        except Exception as e:
            log(f"Move attempt {attempt+1} failed: {e}")
            time.sleep(delay)
    log(f"Failed to move {src} -> {dst}")
    return False

def cleanup_delete_daily():
    removed = 0
    for name in os.listdir(DELETE_DAILY_DIR):
        path = os.path.join(DELETE_DAILY_DIR, name)
        try:
            if os.path.isfile(path): os.remove(path); removed += 1
            elif os.path.isdir(path): shutil.rmtree(path); removed += 1
        except Exception as e:
            log(f"Cleanup error for {path}: {e}")
    log(f"delete_daily cleanup removed {removed} items")
    return removed

def ffmpeg_exists(): return shutil.which(FFMPEG_CMD) is not None
def ffplay_exists(): return shutil.which(FFPLAY_CMD) is not None

# ---------- Device detection ----------
def ffmpeg_list_devices():
    try:
        proc = subprocess.run([FFMPEG_CMD, "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                              capture_output=True, text=True, check=False)
        return proc.stderr
    except FileNotFoundError:
        return ""

def parse_dshow_devices(stderr_text):
    video, audio = [], []
    mode = None
    for line in stderr_text.splitlines():
        line = line.strip()
        if "DirectShow video devices" in line: mode="video"; continue
        if "DirectShow audio devices" in line: mode="audio"; continue
        if mode and line.startswith('"') and line.endswith('"'):
            name = line.strip('"')
            if mode=="video": video.append(name)
            else: audio.append(name)
    return video, audio

def detect_devices_once():
    out = ffmpeg_list_devices()
    vids, auds = parse_dshow_devices(out)
    if not vids: vids = [FALLBACK_VIDEO_DEVICE]
    if not auds: auds = [FALLBACK_AUDIO_DEVICE]
    return vids, auds

# ---------- Config persistence ----------
def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f: return json.load(f)
        except Exception: pass
    return {}
def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f: json.dump(cfg, f, indent=2); return True
    except Exception as e: log(f"Failed to save config: {e}"); return False

# ---------- Splash ----------
class SplashController:
    def __init__(self, root, on_done):
        self.root = root
        self.on_done = on_done
        self.proc = None; self.overlay = None

    def play(self):
        if not os.path.exists(SPLASH_PATH) or not ffplay_exists():
            self.root.after(10, self.on_done)
            return
        try:
            self.proc = subprocess.Popen([FFPLAY_CMD, "-autoexit", "-fs", "-loglevel", "quiet", SPLASH_PATH])
        except Exception:
            self.root.after(10, self.on_done)
            return
        self.overlay = tk.Toplevel(self.root)
        self.overlay.configure(bg="black"); self.overlay.attributes("-topmost", True)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = 480, 140
        self.overlay.geometry(f"{w}x{h}+{(sw-w)//2}+{sh-h-80}")
        tk.Label(self.overlay, text="Click Continue to open recorder", fg="white", bg="black", font=("Arial", 14)).pack(expand=True, pady=6)
        ttk.Button(self.overlay, text="Continue", command=self._finish).pack(pady=6)
        threading.Thread(target=self._monitor, daemon=True).start()

    def _monitor(self):
        if self.proc: self.proc.wait()
        self.root.after(0, self._finish)
    def _finish(self):
        try: self.overlay.destroy()
        except Exception: pass
        self.on_done()

# ---------- Device dialog ----------
class DeviceSelectDialog(simpledialog.Dialog):
    def __init__(self, parent, video_list, audio_list, selected_video, selected_audio):
        self.video_list = video_list
        self.audio_list = audio_list
        self.selected_video = tk.StringVar(value=selected_video)
        self.selected_audio = tk.StringVar(value=selected_audio)
        super().__init__(parent, title="Select Camera and Microphone")

    def body(self, frame):
        tk.Label(frame, text="Video devices:", anchor="w").grid(row=0, column=0, sticky="w")
        self.video_cb = ttk.Combobox(frame, values=self.video_list, textvariable=self.selected_video, state="readonly", width=50)
        self.video_cb.grid(row=1, column=0, padx=6, pady=4)
        tk.Label(frame, text="Audio devices:", anchor="w").grid(row=2, column=0, sticky="w")
        self.audio_cb = ttk.Combobox(frame, values=self.audio_list, textvariable=self.selected_audio, state="readonly", width=50)
        self.audio_cb.grid(row=3, column=0, padx=6, pady=4)
        return self.video_cb

    def apply(self):
        self.result = {"video": self.selected_video.get(), "audio": self.selected_audio.get()}

# ---------- Main Application ----------
class VideoRecorderApp:
    def __init__(self, root):
        self.root = root; self.root.title("Video Recorder"); self.root.configure(bg="black"); self.root.attributes("-fullscreen", True)
        self.config = load_config()

        vids, auds = detect_devices_once()
        saved_video = self.config.get("video_device", vids[0])
        saved_audio = self.config.get("audio_device", auds[0])
        self.video_device = saved_video; self.audio_device = saved_audio

        # UI
        self.border = tk.Frame(root, bg="white", bd=8); self.border.pack(expand=True, fill="both", padx=24, pady=24)
        self.content = tk.Frame(self.border, bg="black"); self.content.pack(expand=True, fill="both")
        self.preview_label = tk.Label(self.content, bg="black"); self.preview_label.pack(expand=True)
        ctrl = tk.Frame(self.content, bg="black"); ctrl.pack(fill="x", pady=8)
        self.start_btn = ttk.Button(ctrl, text="Start Recording", command=self.start_recording_thread); self.start_btn.pack(side="left", padx=6)
        self.stop_btn = ttk.Button(ctrl, text="Stop Recording", state="disabled", command=self.stop_recording); self.stop_btn.pack(side="left", padx=6)
        self.play_btn = ttk.Button(ctrl, text="Play Last", state="disabled", command=self.play_last); self.play_btn.pack(side="left", padx=6)
        self.approve_btn = ttk.Button(ctrl, text="Approve", state="disabled", command=self.approve_current); self.approve_btn.pack(side="left", padx=6)
        self.reject_btn = ttk.Button(ctrl, text="Reject", state="disabled", command=self.reject_current); self.reject_btn.pack(side="left", padx=6)
        self.status_var = tk.StringVar(value="Ready"); self.status_label = tk.Label(self.content, textvariable=self.status_var, fg="white", bg="black"); self.status_label.pack(pady=6)

        # Variables
        self.cap = None; self.preview_job = None; self.preview_running = False
        self.record_thread = None; self.record_proc = None; self.recording = False
        self.record_start_time = None; self.current_file = None
        self.post_timeout_job = None; self.post_timeout_left = 0

        self.root.bind_all("<Control-d>", lambda e: self.open_device_dialog())
        self.root.bind_all("<Key>", self.reset_post_timeout)
        self.root.bind_all("<Button>", self.reset_post_timeout)
        cleanup_delete_daily()
        if "video_device" not in self.config or "audio_device" not in self.config:
            self.open_device_dialog(first_run=True, video_list=vids, audio_list=auds)

        log(f"Using devices -> video: {self.video_device!r}, audio: {self.audio_device!r}")
        self.open_preview()

    # ---------- Preview ----------
    def open_preview(self):
        if self.cap and self.cap.isOpened(): return
        # match selected video device (Windows index mapping)
        try: self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        except Exception: self.cap = cv2.VideoCapture(0)
        time.sleep(0.12)
        self.preview_running = True
        self._preview_loop()

    def _fit_size(self, w, h, max_w, max_h):
        scale = min(max_w / w, max_h / h, 1.0); return int(w*scale), int(h*scale)

    def _preview_loop(self):
        if not self.cap or not self.preview_running: return
        ret, frame = self.cap.read()
        if ret:
            h, w = frame.shape[:2]
            new_w, new_h = self._fit_size(w, h, PREVIEW_MAX_W, PREVIEW_MAX_H)
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb).resize((new_w, new_h), Image.LANCZOS)
            imgtk = ImageTk.PhotoImage(img)
            self.preview_label.imgtk = imgtk
            self.preview_label.configure(image=imgtk)
        self.preview_job = self.root.after(30, self._preview_loop)

    def close_preview(self):
        self.preview_running = False
        if self.preview_job:
            try: self.root.after_cancel(self.preview_job)
            except Exception: pass
            self.preview_job = None
        if self.cap:
            try: self.cap.release()
            except Exception: pass
            self.cap = None

    # ---------- Device dialog ----------
    def open_device_dialog(self, first_run=False, video_list=None, audio_list=None):
        if video_list is None or audio_list is None: vids, auds = detect_devices_once()
        else: vids, auds = video_list, audio_list
        dlg = DeviceSelectDialog(self.root, vids, auds, self.video_device, self.audio_device)
        res = getattr(dlg, "result", None)
        if res:
            self.video_device = res["video"]; self.audio_device = res["audio"]
            self.config["video_device"] = self.video_device; self.config["audio_device"] = self.audio_device
            save_config(self.config)
            log(f"User selected devices -> video: {self.video_device!r}, audio: {self.audio_device!r}")
            self.close_preview(); self.open_preview()
        elif first_run:
            self.video_device = self.video_device or vids[0]; self.audio_device = self.audio_device or auds[0]
            self.config["video_device"] = self.video_device; self.config["audio_device"] = self.audio_device
            save_config(self.config)
            log("First-run selection fallback used.")

    # ---------- Recording ----------
    def start_recording_thread(self):
        if self.recording: return
        self.record_thread = threading.Thread(target=self._record_worker, daemon=True)
        self.record_thread.start()

    def _record_worker(self):
        self.close_preview()
        time.sleep(0.12)  # ensure camera release
        ts = int(time.time()); filename = f"recording_{ts}.mp4"
        outpath = os.path.join(INBOUND_DIR, filename); self.current_file = outpath
        dshow_spec = f'video={self.video_device}:audio={self.audio_device}'
        cmd = [
            FFMPEG_CMD, "-y", "-f", "dshow", "-video_size", "1920x1080", "-framerate", "30",
            "-i", dshow_spec, "-vcodec", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", outpath
        ]
        # todo:fix command above to start recording 
        log(f"Starting ffmpeg: {' '.join(cmd)}")
        try: self.record_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            log(f"Recording failed: {e}"); self.open_preview(); return

        self.recording = True; self.record_start_time = time.time()
        self.start_btn.config(state="disabled"); self.stop_btn.config(state="normal"); self.status_var.set("Recording...")
        while self.recording and self.record_proc.poll() is None:
            if time.time() - self.record_start_time >= MAX_RECORD_SECONDS: break
            time.sleep(0.1)
        if self.record_proc and self.record_proc.poll() is None:
            try: self.record_proc.terminate()
            except Exception: pass
            try: self.record_proc.wait(timeout=2)
            except Exception: pass
        self.recording = False
        self.start_btn.config(state="normal"); self.stop_btn.config(state="disabled"); self.status_var.set("Recording finished")
        log(f"Recording finished: {self.current_file}")
        time.sleep(0.25); self.open_preview()
        if self.current_file and os.path.exists(self.current_file):
            self.approve_btn.config(state="normal"); self.reject_btn.config(state="normal"); self.play_btn.config(state="normal")
            self.start_post_timeout()

    def stop_recording(self):
        if not self.recording: return
        log("User stopped recording"); self.recording = False
        if self.record_proc and self.record_proc.poll() is None:
            try: self.record_proc.terminate()
            except Exception: pass

    # ---------- Post-record ----------
    def start_post_timeout(self):
        self.cancel_post_timeout(); self.post_timeout_left = POST_RECORD_TIMEOUT
        self.post_timeout_job = self.root.after(1000, self._post_timeout_tick)
        self.status_var.set(f"Awaiting approve/reject ({self.post_timeout_left}s)")

    def _post_timeout_tick(self):
        self.post_timeout_left -= 1
        self.status_var.set(f"Awaiting approve/reject ({self.post_timeout_left}s)")
        if self.post_timeout_left <= 0:
            if self.current_file and os.path.exists(self.current_file):
                safe_move(self.current_file, DELETE_DAILY_DIR)
                messagebox.showinfo("Timed out", f"No action taken — moved to {DELETE_DAILY_DIR}")
                log(f"Auto-moved to delete_daily: {self.current_file}")
                self.current_file = None
                self.approve_btn.config(state="disabled"); self.reject_btn.config(state="disabled"); self.play_btn.config(state="disabled")
            self.cancel_post_timeout(); return
        self.post_timeout_job = self.root.after(1000, self._post_timeout_tick)

    def cancel_post_timeout(self):
        if self.post_timeout_job:
            try: self.root.after_cancel(self.post_timeout_job)
            except Exception: pass
            self.post_timeout_job = None; self.post_timeout_left = 0
        self.status_var.set("Ready")

    def reset_post_timeout(self, event=None):
        if self.current_file and os.path.exists(self.current_file): self.start_post_timeout()

    # ---------- Approve/Reject ----------
    def approve_current(self):
        if self.current_file and os.path.exists(self.current_file):
            if safe_move(self.current_file, APPROVED_DIR):
                messagebox.showinfo("Approved", f"Moved to {APPROVED_DIR}")
                self.current_file = None; self.approve_btn.config(state="disabled"); self.reject_btn.config(state="disabled"); self.play_btn.config(state="disabled")
                self.cancel_post_timeout()
    def reject_current(self):
        if self.current_file and os.path.exists(self.current_file):
            if safe_move(self.current_file, DELETE_DAILY_DIR):
                messagebox.showinfo("Rejected", f"Moved to {DELETE_DAILY_DIR}")
                self.current_file = None; self.approve_btn.config(state="disabled"); self.reject_btn.config(state="disabled"); self.play_btn.config(state="disabled")
                self.cancel_post_timeout()

    # ---------- Play last ----------
    def play_last(self):
        if not self.current_file or not os.path.exists(self.current_file) or not ffplay_exists(): return
        try: subprocess.Popen([FFPLAY_CMD, "-autoexit", "-loglevel", "quiet", self.current_file])
        except Exception as e: log(f"Play failed: {e}")

# ---------- Main ----------
def main():
    root = tk.Tk()
    app = VideoRecorderApp(root)
    SplashController(root, lambda: None).play()  # optional splash at startup
    root.mainloop()

if __name__ == "__main__":
    main()
