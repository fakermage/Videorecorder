import tkinter as tk
from tkinter import messagebox
import cv2
from PIL import Image, ImageTk
import threading
import os
import time
import shutil
import subprocess

# ---------- CONFIGURATION ----------
FFMPEG_PATH = "C:/ffmpeg/bin/ffmpeg.exe"
INBOUND_DIR = "inbound"
DELETE_DAILY_DIR = "delete_daily"
SPLASH_VIDEO = "splash.mp4"  # Replace with your splash file path
RECORD_DURATION = 8  # seconds

# Create folders if missing
os.makedirs(INBOUND_DIR, exist_ok=True)
os.makedirs(DELETE_DAILY_DIR, exist_ok=True)


# ---------- VIDEO RECORDER CLASS ----------
class VideoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Video Recorder GUI")

        # Unified window border
        self.border = tk.Frame(root, bg="#333", bd=6, relief=tk.RIDGE)
        self.border.pack(padx=20, pady=20)

        # Video display area
        self.display = tk.Label(self.border)
        self.display.pack()

        # Control buttons
        self.btn_frame = tk.Frame(self.border, bg="#333")
        self.btn_frame.pack(pady=10)

        self.record_btn = tk.Button(self.btn_frame, text="🎥 Record", command=self.start_recording_thread)
        self.record_btn.grid(row=0, column=0, padx=10)

        self.quit_btn = tk.Button(self.btn_frame, text="❌ Quit", command=self.quit_app)
        self.quit_btn.grid(row=0, column=1, padx=10)

        self.cap = None
        self.playing_splash = True
        self.video_path = None
        self.stop_recording_flag = threading.Event()

        # Start splash screen
        self.play_splash()

    # ---------- SPLASH SCREEN ----------
    def play_splash(self):
        self.cap = cv2.VideoCapture(SPLASH_VIDEO)
        if not self.cap.isOpened():
            messagebox.showerror("Error", f"Cannot open splash video: {SPLASH_VIDEO}")
            self.start_camera()
            return
        self.update_splash_frame()

    def update_splash_frame(self):
        ret, frame = self.cap.read()
        if ret:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame)
            imgtk = ImageTk.PhotoImage(image=img)
            self.display.imgtk = imgtk
            self.display.configure(image=imgtk)
            self.root.after(30, self.update_splash_frame)
        else:
            self.cap.release()
            self.playing_splash = False
            self.start_camera()

    # ---------- CAMERA PREVIEW ----------
    def start_camera(self):
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            messagebox.showerror("Error", "Cannot access camera.")
            return
        self.update_camera_frame()

    def update_camera_frame(self):
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame)
                imgtk = ImageTk.PhotoImage(image=img)
                self.display.imgtk = imgtk
                self.display.configure(image=imgtk)
            self.root.after(30, self.update_camera_frame)

    # ---------- RECORDING ----------
    def start_recording_thread(self):
        threading.Thread(target=self.start_recording, daemon=True).start()

    def start_recording(self):
        if not self.cap or not self.cap.isOpened():
            messagebox.showerror("Error", "Camera not available.")
            return

        timestamp = int(time.time())
        self.video_path = os.path.join(INBOUND_DIR, f"recording_{timestamp}.mp4")

        # Build FFmpeg command (video + audio)
        cmd = [
            FFMPEG_PATH,
            "-f", "dshow",
            "-i", "video=Integrated Camera:audio=Microphone (Realtek Audio)",
            "-t", str(RECORD_DURATION),
            "-vcodec", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "ultrafast",
            self.video_path
        ]

        try:
            subprocess.run(cmd, check=True)
            self.handle_video_move("inbound")
        except Exception as e:
            print(f"Recording failed: {e}")
            self.handle_video_move("delete_daily")

    # ---------- FILE HANDLER ----------
    def handle_video_move(self, destination):
        try:
            if self.video_path and os.path.exists(self.video_path):
                base = os.path.basename(self.video_path)
                dst = os.path.join(destination, base)
                shutil.move(self.video_path, dst)
                print(f"Moved {base} → {destination}")
        except Exception as e:
            print(f"File move error: {e}")

    # ---------- EXIT ----------
    def quit_app(self):
        if self.cap:
            self.cap.release()
        self.root.destroy()


# ---------- MAIN ----------
if __name__ == "__main__":
    root = tk.Tk()
    app = VideoApp(root)
    root.mainloop()