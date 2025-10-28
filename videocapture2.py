import os
import sys
import subprocess
import zipfile
import urllib.request
import shutil

# =============== Helper Functions ===============

def run_command(cmd, description):
    """Run a shell command and print friendly status."""
    print(f"\n🛠 {description} ...")
    try:
        subprocess.check_call(cmd, shell=True)
        print(f"✅ {description} complete.")
    except subprocess.CalledProcessError:
        print(f"❌ Failed during: {description}")
        sys.exit(1)

def pip_install(package):
    """Install a Python package."""
    run_command(f"{sys.executable} -m pip install --upgrade {package}", f"Installing {package}")

def ensure_ffmpeg():
    """Download and install FFmpeg if not installed."""
    ffmpeg_check = shutil.which("ffmpeg")
    if ffmpeg_check:
        print(f"✅ FFmpeg already installed at: {ffmpeg_check}")
        return

    print("\n🔽 Downloading FFmpeg (Windows build from gyan.dev)...")
    url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    zip_path = "ffmpeg-release-essentials.zip"
    urllib.request.urlretrieve(url, zip_path)
    print("✅ Download complete.")

    extract_path = "C:\\ffmpeg"
    os.makedirs(extract_path, exist_ok=True)
    print(f"📦 Extracting to {extract_path} ...")

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(extract_path)

    # Find bin folder
    bin_path = None
    for root, dirs, files in os.walk(extract_path):
        if "ffmpeg.exe" in files:
            bin_path = root
            break

    if not bin_path:
        print("❌ FFmpeg binary not found after extraction.")
        sys.exit(1)

    print(f"🛠 Found ffmpeg.exe at: {bin_path}")

    # Add to PATH
    print("🔧 Adding FFmpeg to system PATH...")
    try:
        subprocess.run(f'setx PATH "%PATH%;{bin_path}"', shell=True, check=True)
        print("✅ FFmpeg added to PATH.")
    except Exception as e:
        print(f"⚠ Could not modify PATH automatically: {e}")
        print(f"Please manually add {bin_path} to your PATH.")

    os.remove(zip_path)
    print("🧹 Cleanup complete.")

    # Verify
    try:
        output = subprocess.check_output(["ffmpeg", "-version"], text=True)
        print(f"🎉 FFmpeg installed successfully: {output.splitlines()[0]}")
    except Exception as e:
        print(f"❌ Could not verify FFmpeg: {e}")

def verify_installations():
    """Check camera, audio, and Python modules."""
    print("\n🔍 Verifying installations...")

    try:
        import cv2
        print(f"✅ OpenCV version: {cv2.__version__}")
    except ImportError:
        print("❌ OpenCV not found")

    try:
        import PIL
        print(f"✅ Pillow version: {PIL.__version__}")
    except ImportError:
        print("❌ Pillow not found")

    try:
        import tkinter
        print("✅ Tkinter is available.")
    except ImportError:
        print("❌ Tkinter is missing (install Python with Tcl/Tk).")

    print("\n🧠 Checking FFmpeg availability...")
    try:
        out = subprocess.check_output(["ffmpeg", "-version"], text=True)
        print(f"✅ FFmpeg detected: {out.splitlines()[0]}")
    except Exception:
        print("❌ FFmpeg not found. Try restarting your computer after install.")

# =============== Main Script ===============

def main():
    print("=====================================")
    print("🎥 Video App Environment Installer")
    print("=====================================")

    # Upgrade pip
    pip_install("pip")

    # Core Python dependencies
    pip_install("opencv-python")
    pip_install("Pillow")

    # Optional helpful libs (for future email features)
    pip_install("requests")
    pip_install("smtplib")

    # Ensure FFmpeg is installed
    ensure_ffmpeg()

    # Verify everything
    verify_installations()

    print("\n✅ Installation complete!")
    print("💡 You can now run your program: video_recorder_ffmpeg_gui.py")

if __name__ == "__main__":
    main()