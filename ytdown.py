import os
import threading
import urllib.request
from io import BytesIO
from tkinter import filedialog, messagebox

import customtkinter as ctk
import yt_dlp
from PIL import Image


class DownloadCancelled(Exception):
    pass


class SilentLogger:
    def debug(self, message):
        pass

    def warning(self, message):
        pass

    def error(self, message):
        pass


FORMAT_OPTIONS = {
    "Best Video": {
        "format": "bestvideo+bestaudio/best",
        "postprocessors": [],
        "merge_output_format": "mp4",
    },
    "Audio Only": {
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "merge_output_format": None,
    },
    "Video Only": {
        "format": "bestvideo/best",
        "postprocessors": [],
        "merge_output_format": "mp4",
    },
}


def format_speed(bytes_per_second):
    if not bytes_per_second:
        return "-"
    units = ["B/s", "KB/s", "MB/s", "GB/s"]
    value = float(bytes_per_second)
    for unit in units:
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB/s"


def format_eta(seconds):
    if seconds is None:
        return "-"
    seconds = int(seconds)
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_duration(seconds):
    if seconds is None:
        return "Unknown"
    seconds = int(seconds)
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:d}:{secs:02d}"


def pick_thumbnail_url(info):
    thumbnail = info.get("thumbnail")
    if thumbnail:
        return thumbnail
    thumbnails = info.get("thumbnails") or []
    if thumbnails:
        return thumbnails[-1].get("url")
    return None


def download_thumbnail_image(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=10) as response:
        raw_bytes = response.read()
    return Image.open(BytesIO(raw_bytes)).convert("RGB")


class VideoDownloaderApp(ctk.CTk):
    THUMBNAIL_SIZE = (320, 180)

    def __init__(self):
        super().__init__()
        self.title("Video Downloader")
        self.geometry("640x820")
        self.minsize(580, 480)

        self.video_info = None
        self.output_directory = os.path.join(os.path.expanduser("~"), "Downloads")
        self.cancel_requested = False
        self.fetch_thread = None
        self.download_thread = None

        self.build_layout()

    def build_layout(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        container = ctk.CTkScrollableFrame(self, corner_radius=0, fg_color="transparent")
        container.grid(row=0, column=0, sticky="nsew", padx=24, pady=24)
        container.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            container, text="Video Downloader", font=ctk.CTkFont(size=22, weight="bold")
        ).grid(row=0, column=0, sticky="w", pady=(0, 16))

        self.build_url_section(container, row=1)
        self.build_info_section(container, row=2)
        self.build_output_section(container, row=3)
        self.build_format_section(container, row=4)
        self.build_progress_section(container, row=5)
        self.build_action_section(container, row=6)
        self.build_status_section(container, row=7)

    def build_url_section(self, parent, row):
        frame = ctk.CTkFrame(parent, corner_radius=12)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 16))
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frame, text="Video URL", font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 4)
        )

        self.url_entry = ctk.CTkEntry(
            frame, placeholder_text="Paste a video URL here", height=38, corner_radius=8
        )
        self.url_entry.grid(row=1, column=0, sticky="ew", padx=(16, 8), pady=(0, 14))

        self.fetch_info_button = ctk.CTkButton(
            frame,
            text="Fetch Info",
            width=120,
            height=38,
            corner_radius=8,
            command=self.on_fetch_info_clicked,
        )
        self.fetch_info_button.grid(row=1, column=1, sticky="e", padx=(0, 16), pady=(0, 14))

    def build_info_section(self, parent, row):
        frame = ctk.CTkFrame(parent, corner_radius=12)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 16))
        frame.grid_columnconfigure(1, weight=1)

        self.thumbnail_label = ctk.CTkLabel(
            frame,
            text="No preview",
            width=self.THUMBNAIL_SIZE[0],
            height=self.THUMBNAIL_SIZE[1],
            corner_radius=8,
            fg_color=("gray85", "gray20"),
        )
        self.thumbnail_label.grid(row=0, column=0, rowspan=3, padx=16, pady=16)

        self.title_label = ctk.CTkLabel(
            frame,
            text="Title: -",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
            justify="left",
            wraplength=260,
        )
        self.title_label.grid(row=0, column=1, sticky="ew", padx=(0, 16), pady=(20, 4))

        self.duration_label = ctk.CTkLabel(
            frame, text="Duration: -", anchor="w", justify="left"
        )
        self.duration_label.grid(row=1, column=1, sticky="ew", padx=(0, 16), pady=4)

        self.uploader_label = ctk.CTkLabel(
            frame, text="Channel: -", anchor="w", justify="left"
        )
        self.uploader_label.grid(row=2, column=1, sticky="ew", padx=(0, 16), pady=(4, 16))

    def build_output_section(self, parent, row):
        frame = ctk.CTkFrame(parent, corner_radius=12)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 16))
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frame, text="Output Folder", font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 4)
        )

        self.output_entry = ctk.CTkEntry(frame, height=38, corner_radius=8)
        self.output_entry.insert(0, self.output_directory)
        self.output_entry.grid(row=1, column=0, sticky="ew", padx=(16, 8), pady=(0, 14))

        browse_button = ctk.CTkButton(
            frame,
            text="Browse",
            width=100,
            height=38,
            corner_radius=8,
            command=self.on_browse_folder_clicked,
        )
        browse_button.grid(row=1, column=1, sticky="e", padx=(0, 16), pady=(0, 14))

    def build_format_section(self, parent, row):
        frame = ctk.CTkFrame(parent, corner_radius=12)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 16))
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frame, text="Format", font=ctk.CTkFont(size=13, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 4)
        )

        self.format_menu = ctk.CTkOptionMenu(
            frame, values=list(FORMAT_OPTIONS.keys()), height=38, corner_radius=8
        )
        self.format_menu.set("Best Video")
        self.format_menu.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))

    def build_progress_section(self, parent, row):
        frame = ctk.CTkFrame(parent, corner_radius=12)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 16))
        frame.grid_columnconfigure(0, weight=1)

        self.progress_bar = ctk.CTkProgressBar(frame, height=14, corner_radius=7)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=0, column=0, columnspan=3, sticky="ew", padx=16, pady=(16, 10))

        self.percent_label = ctk.CTkLabel(frame, text="0%")
        self.percent_label.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 16))

        self.speed_label = ctk.CTkLabel(frame, text="Speed: -")
        self.speed_label.grid(row=1, column=1, sticky="w", pady=(0, 16))

        self.eta_label = ctk.CTkLabel(frame, text="ETA: -")
        self.eta_label.grid(row=1, column=2, sticky="e", padx=16, pady=(0, 16))

    def build_action_section(self, parent, row):
        frame = ctk.CTkFrame(parent, corner_radius=0, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 16))
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=1)

        self.download_button = ctk.CTkButton(
            frame,
            text="Download",
            height=42,
            corner_radius=8,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.on_download_clicked,
        )
        self.download_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.cancel_button = ctk.CTkButton(
            frame,
            text="Cancel",
            height=42,
            corner_radius=8,
            fg_color="#8B2E2E",
            hover_color="#6E2323",
            state="disabled",
            command=self.on_cancel_clicked,
        )
        self.cancel_button.grid(row=0, column=1, sticky="ew", padx=(8, 0))

    def build_status_section(self, parent, row):
        self.status_label = ctk.CTkLabel(parent, text="Ready", anchor="w")
        self.status_label.grid(row=row, column=0, sticky="ew")

    def on_browse_folder_clicked(self):
        selected_directory = filedialog.askdirectory(initialdir=self.output_directory)
        if selected_directory:
            self.output_directory = selected_directory
            self.output_entry.delete(0, "end")
            self.output_entry.insert(0, selected_directory)

    def on_fetch_info_clicked(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Please enter a video URL first.")
            return
        if self.fetch_thread and self.fetch_thread.is_alive():
            return

        self.set_fetch_controls_enabled(False)
        self.status_label.configure(text="Fetching video information...")
        self.fetch_thread = threading.Thread(target=self.fetch_info_worker, args=(url,), daemon=True)
        self.fetch_thread.start()

    def fetch_info_worker(self, url):
        options = {
            "quiet": True,
            "no_warnings": True,
            "logger": SilentLogger(),
            "skip_download": True,
            "noplaylist": True,
        }
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as error:
            self.after(0, lambda: self.on_fetch_error(self.friendly_error_message(str(error))))
            return
        except Exception as error:
            self.after(0, lambda: self.on_fetch_error(self.friendly_error_message(str(error))))
            return

        thumbnail_image = None
        thumbnail_url = pick_thumbnail_url(info)
        if thumbnail_url:
            try:
                thumbnail_image = download_thumbnail_image(thumbnail_url)
            except Exception:
                thumbnail_image = None

        self.after(0, lambda: self.on_fetch_success(info, thumbnail_image))

    def on_fetch_success(self, info, thumbnail_image):
        self.video_info = info
        self.title_label.configure(text=f"Title: {info.get('title', 'Unknown')}")
        self.duration_label.configure(text=f"Duration: {format_duration(info.get('duration'))}")
        self.uploader_label.configure(text=f"Channel: {info.get('uploader', 'Unknown')}")

        if thumbnail_image is not None:
            resized_image = thumbnail_image.resize(self.THUMBNAIL_SIZE)
            ctk_image = ctk.CTkImage(
                light_image=resized_image, dark_image=resized_image, size=self.THUMBNAIL_SIZE
            )
            self.thumbnail_label.configure(image=ctk_image, text="")
            self.thumbnail_label.image = ctk_image
        else:
            self.thumbnail_label.configure(image=None, text="No thumbnail available")

        self.status_label.configure(text="Video information loaded")
        self.set_fetch_controls_enabled(True)

    def on_fetch_error(self, message):
        self.status_label.configure(text="Failed to fetch video information")
        self.set_fetch_controls_enabled(True)
        messagebox.showerror("Fetch Error", message)

    def set_fetch_controls_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        self.fetch_info_button.configure(state=state)

    def on_download_clicked(self):
        if self.video_info is None:
            messagebox.showwarning(
                "Video Not Loaded", "Please fetch the video information before downloading."
            )
            return

        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Please enter a video URL first.")
            return

        output_dir = self.output_entry.get().strip() or self.output_directory
        if not os.path.isdir(output_dir):
            try:
                os.makedirs(output_dir, exist_ok=True)
            except OSError as error:
                messagebox.showerror("Invalid Folder", f"Could not use this output folder:\n{error}")
                return

        self.output_directory = output_dir
        format_key = self.format_menu.get()

        self.cancel_requested = False
        self.progress_bar.set(0)
        self.percent_label.configure(text="0%")
        self.speed_label.configure(text="Speed: -")
        self.eta_label.configure(text="ETA: -")
        self.status_label.configure(text="Starting download...")
        self.set_download_controls_enabled(downloading=True)

        self.download_thread = threading.Thread(
            target=self.download_worker, args=(url, format_key, output_dir), daemon=True
        )
        self.download_thread.start()

    def build_ydl_options(self, format_key, output_dir):
        format_config = FORMAT_OPTIONS[format_key]
        options = {
            "format": format_config["format"],
            "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
            "postprocessors": list(format_config["postprocessors"]),
            "progress_hooks": [self.progress_hook],
            "quiet": True,
            "no_warnings": True,
            "logger": SilentLogger(),
            "noplaylist": True,
        }
        if format_config["merge_output_format"]:
            options["merge_output_format"] = format_config["merge_output_format"]
        return options

    def download_worker(self, url, format_key, output_dir):
        options = self.build_ydl_options(format_key, output_dir)
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([url])
        except DownloadCancelled:
            self.after(0, self.on_download_cancelled)
            return
        except yt_dlp.utils.DownloadError as error:
            self.after(0, lambda: self.on_download_error(self.friendly_error_message(str(error))))
            return
        except Exception as error:
            self.after(0, lambda: self.on_download_error(self.friendly_error_message(str(error))))
            return

        self.after(0, self.on_download_finished)

    def progress_hook(self, status):
        if self.cancel_requested:
            raise DownloadCancelled("Download cancelled by user")

        if status["status"] == "downloading":
            downloaded_bytes = status.get("downloaded_bytes", 0)
            total_bytes = status.get("total_bytes") or status.get("total_bytes_estimate")
            fraction = downloaded_bytes / total_bytes if total_bytes else 0
            speed = status.get("speed")
            eta = status.get("eta")
            self.after(0, lambda: self.update_progress_ui(fraction, speed, eta, "Downloading..."))
        elif status["status"] == "finished":
            self.after(0, lambda: self.update_progress_ui(1.0, None, 0, "Processing..."))

    def update_progress_ui(self, fraction, speed, eta, status_text):
        fraction = max(0.0, min(1.0, fraction))
        self.progress_bar.set(fraction)
        self.percent_label.configure(text=f"{fraction * 100:.1f}%")
        self.speed_label.configure(text=f"Speed: {format_speed(speed)}")
        self.eta_label.configure(text=f"ETA: {format_eta(eta)}")
        self.status_label.configure(text=status_text)

    def on_download_finished(self):
        self.progress_bar.set(1.0)
        self.percent_label.configure(text="100%")
        self.status_label.configure(text="Download completed")
        self.set_download_controls_enabled(downloading=False)
        messagebox.showinfo("Download Complete", "The video has been downloaded successfully.")

    def on_download_cancelled(self):
        self.status_label.configure(text="Download cancelled")
        self.set_download_controls_enabled(downloading=False)

    def on_download_error(self, message):
        self.status_label.configure(text="Download failed")
        self.set_download_controls_enabled(downloading=False)
        messagebox.showerror("Download Error", message)

    def on_cancel_clicked(self):
        self.cancel_requested = True
        self.status_label.configure(text="Cancelling...")
        self.cancel_button.configure(state="disabled")

    def set_download_controls_enabled(self, downloading):
        self.download_button.configure(state="disabled" if downloading else "normal")
        self.cancel_button.configure(state="normal" if downloading else "disabled")
        self.fetch_info_button.configure(state="disabled" if downloading else "normal")

    @staticmethod
    def friendly_error_message(raw_message):
        lowered = raw_message.lower()
        if "unsupported url" in lowered:
            return "This URL is not supported. Please check the link and try again."
        if "video unavailable" in lowered:
            return "This video is unavailable. It may be private, deleted, or region-locked."
        if "network" in lowered or "urlopen" in lowered or "timed out" in lowered:
            return "A network error occurred. Please check your internet connection and try again."
        if "ffmpeg" in lowered:
            return "FFmpeg is required for this operation but was not found on your system."
        return raw_message


def main():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = VideoDownloaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
