"""
YTGrab — a YTGet-style YouTube downloader
Modern dark GUI (CustomTkinter) + yt-dlp
Features: download queue, console log, quality presets up to 8K,
paste button, progress bar, skip/stop, folder picker,
PLAYLIST support — paste a playlist link and every video
gets added to the queue (with a confirmation popup first).

Requirements:
    pip install customtkinter yt-dlp
    FFmpeg installed (for merging video+audio and MP3 conversion)
"""

import os
import sys
import json
import threading
import webbrowser
import urllib.request
import queue as thread_queue
from datetime import datetime

import customtkinter as ctk
from tkinter import filedialog, messagebox

try:
    import yt_dlp
except ImportError:
    raise SystemExit("yt-dlp is not installed. Run:  pip install yt-dlp")

APP_NAME = "YTGrab"
VERSION = "v1.6"

# ⚠ EDIT THIS if your GitHub username or repo name is different!
GITHUB_REPO = "astavkhra/YTGrab"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases/latest"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def find_ffmpeg_dir():
    """Find ffmpeg in (1) the PyInstaller bundle, (2) next to the exe/script,
    or (3) fall back to system PATH. Returns a folder path or None."""
    exe_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    candidates = []
    if getattr(sys, "_MEIPASS", None):            # inside a PyInstaller onefile bundle
        candidates.append(sys._MEIPASS)
    candidates.append(os.path.dirname(os.path.abspath(sys.argv[0])))  # next to exe
    candidates.append(os.path.dirname(os.path.abspath(__file__)))     # next to .py
    for folder in candidates:
        if os.path.isfile(os.path.join(folder, exe_name)):
            return folder
    return None  # not bundled — yt-dlp will look in system PATH


FFMPEG_DIR = find_ffmpeg_dir()

# Settings are remembered here (your home folder) between app launches.
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".ytgrab_settings.json")


def load_settings():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(data: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass  # settings are a convenience; never crash over them

# Rough average bitrates (Megabits/sec) used to ESTIMATE download size.
# Real size varies with content, but this gives a good ballpark.
BITRATE_ESTIMATES = {
    "YouTube 4320p (8K)": 45.0,
    "YouTube 2160p (4K)": 20.0,
    "YouTube 1440p (2K)": 10.0,
    "YouTube 1080p":      5.0,
    "YouTube 720p":       2.6,
    "YouTube 480p":       1.3,
    "YouTube 360p":       0.8,
    "Audio Only (MP3 320k)": 0.32,
    "Audio Only (MP3 192k)": 0.192,
}

QUALITY_OPTIONS = {
    "YouTube 4320p (8K)": "bestvideo[height<=4320]+bestaudio/best",
    "YouTube 2160p (4K)": "bestvideo[height<=2160]+bestaudio/best",
    "YouTube 1440p (2K)": "bestvideo[height<=1440]+bestaudio/best",
    "YouTube 1080p":      "bestvideo[height<=1080]+bestaudio/best",
    "YouTube 720p":       "bestvideo[height<=720]+bestaudio/best",
    "YouTube 480p":       "bestvideo[height<=480]+bestaudio/best",
    "YouTube 360p":       "bestvideo[height<=360]+bestaudio/best",
    "Audio Only (MP3 320k)": "bestaudio/best",
    "Audio Only (MP3 192k)": "bestaudio/best",
}

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class QueueItem:
    def __init__(self, url, quality="YouTube 1080p"):
        self.url = url
        self.status = "Queued"
        self.title = url
        self.duration = 0  # seconds, used for size estimate
        self.quality = quality  # quality chosen when this item was added
        self.widget = None

    @property
    def quality_tag(self):
        """Short version for display, e.g. '2160p (4K)' or 'MP3 320k'."""
        return (self.quality.replace("YouTube ", "")
                            .replace("Audio Only (", "").replace(")", ""))


class YTGrabApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} {VERSION}")
        self.geometry("1180x720")
        self.minsize(980, 620)

        settings = load_settings()
        saved_dir = settings.get("download_dir", "")
        self.download_dir = (saved_dir if saved_dir and os.path.isdir(saved_dir)
                             else os.path.join(os.path.expanduser("~"), "Downloads"))
        self._saved_quality = settings.get("quality", "YouTube 1080p")
        if self._saved_quality not in QUALITY_OPTIONS:
            self._saved_quality = "YouTube 1080p"
        self.queue_items: list[QueueItem] = []
        self.worker_thread = None
        self.stop_flag = threading.Event()
        self.skip_flag = threading.Event()
        self.is_running = False

        self._build_ui()
        self.log("💡 Welcome to YTGrab! Paste a URL to begin.")
        self.log(f"📁 Default download folder: {self.download_dir}")
        self.log("🔧 Backend: yt-dlp (Python module)")
        if FFMPEG_DIR:
            self.log(f"🔧 Using bundled FFmpeg from: {FFMPEG_DIR}")
        else:
            self.log("🔧 FFmpeg: using system installation (PATH)")
        self.log("💾 Your folder & quality choices are remembered automatically.")
        threading.Thread(target=self._check_for_updates, daemon=True).start()

    # ================================ UI ================================
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=3)
        self.grid_rowconfigure(1, weight=1)

        # ---------- Top bar ----------
        top = ctk.CTkFrame(self, corner_radius=12)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 6))
        top.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(top, text=APP_NAME, font=("Segoe UI", 24, "bold")
                     ).grid(row=0, column=0, padx=(16, 4), pady=12)
        ctk.CTkLabel(top, text=VERSION, text_color="#7f849c"
                     ).grid(row=0, column=1, padx=(0, 12))

        self.url_entry = ctk.CTkEntry(top, placeholder_text="Paste a URL and press Enter",
                                      height=38)
        self.url_entry.grid(row=0, column=2, sticky="ew", padx=6)
        self.url_entry.bind("<Return>", lambda e: self.add_url())

        ctk.CTkButton(top, text="Add", width=64, height=38,
                      command=self.add_url).grid(row=0, column=3, padx=4)
        ctk.CTkButton(top, text="Paste", width=70, height=38,
                      fg_color="#45475a", hover_color="#585b70",
                      command=self.paste_url).grid(row=0, column=4, padx=4)

        self.quality_var = ctk.StringVar(value=self._saved_quality)
        ctk.CTkOptionMenu(top, variable=self.quality_var,
                          values=list(QUALITY_OPTIONS.keys()),
                          width=210, height=38,
                          command=lambda _: self._on_quality_change()
                          ).grid(row=0, column=5, padx=(10, 16))

        # ---------- Queue panel (left) ----------
        left = ctk.CTkFrame(self, corner_radius=12)
        left.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=6)
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        qhead = ctk.CTkFrame(left, fg_color="transparent")
        qhead.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(qhead, text="Queue", font=("Segoe UI", 17, "bold")
                     ).pack(side="left")
        self.queue_count = ctk.CTkLabel(qhead, text="0", fg_color="#313244",
                                        corner_radius=6, width=34)
        self.queue_count.pack(side="left", padx=8)
        ctk.CTkButton(qhead, text="Clear queue", width=90, height=28,
                      fg_color="#45475a", hover_color="#585b70",
                      command=self.clear_queue).pack(side="right")

        self.queue_frame = ctk.CTkScrollableFrame(left, fg_color="#181825",
                                                  corner_radius=10)
        self.queue_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=(4, 12))
        self.empty_label = ctk.CTkLabel(self.queue_frame,
                                        text="Add links to build your queue.",
                                        text_color="#6c7086")
        self.empty_label.pack(pady=40)

        # ---------- Console panel (right) ----------
        right = ctk.CTkFrame(self, corner_radius=12)
        right.grid(row=1, column=1, sticky="nsew", padx=(6, 12), pady=6)
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        chead = ctk.CTkFrame(right, fg_color="transparent")
        chead.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(chead, text="Console", font=("Segoe UI", 17, "bold")
                     ).pack(side="left")
        self.size_label = ctk.CTkLabel(chead, text="Est. size: —",
                                       fg_color="#313244", corner_radius=6,
                                       text_color="#a6e3a1",
                                       font=("Segoe UI", 12, "bold"),
                                       padx=10)
        self.size_label.pack(side="left", padx=10)
        ctk.CTkButton(chead, text="Clear", width=64, height=28,
                      fg_color="#45475a", hover_color="#585b70",
                      command=self.clear_console).pack(side="right", padx=(6, 0))
        ctk.CTkButton(chead, text="Copy all", width=76, height=28,
                      fg_color="#45475a", hover_color="#585b70",
                      command=self.copy_console).pack(side="right")

        self.console = ctk.CTkTextbox(right, fg_color="#181825",
                                      corner_radius=10, font=("Consolas", 12),
                                      wrap="word", state="disabled")
        self.console.grid(row=1, column=0, sticky="nsew", padx=12, pady=(4, 12))

        # ---------- Bottom bar ----------
        bottom = ctk.CTkFrame(self, corner_radius=12)
        bottom.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(6, 12))
        bottom.grid_columnconfigure(3, weight=1)

        self.start_btn = ctk.CTkButton(bottom, text="Start", width=90, height=38,
                                       command=self.start_queue)
        self.start_btn.grid(row=0, column=0, padx=(16, 4), pady=12)
        self.skip_btn = ctk.CTkButton(bottom, text="Skip", width=80, height=38,
                                      fg_color="#45475a", hover_color="#585b70",
                                      command=self.skip_current, state="disabled")
        self.skip_btn.grid(row=0, column=1, padx=4)
        self.stop_btn = ctk.CTkButton(bottom, text="Stop", width=80, height=38,
                                      fg_color="#45475a", hover_color="#585b70",
                                      command=self.stop_queue, state="disabled")
        self.stop_btn.grid(row=0, column=2, padx=4)

        self.progress = ctk.CTkProgressBar(bottom, height=14)
        self.progress.grid(row=0, column=3, sticky="ew", padx=16)
        self.progress.set(0)

        self.speed_label = ctk.CTkLabel(bottom, text="", width=140,
                                        text_color="#a6adc8")
        self.speed_label.grid(row=0, column=4, padx=4)

        self.folder_btn = ctk.CTkButton(bottom, text=self._short_path(),
                                        fg_color="#45475a", hover_color="#585b70",
                                        height=38, command=self.choose_folder)
        self.folder_btn.grid(row=0, column=5, padx=(4, 16))

    def _short_path(self):
        p = self.download_dir
        return p if len(p) <= 34 else "…" + p[-33:]

    # ============================ Console ===============================
    def _check_for_updates(self):
        """Ask GitHub for the newest release; notify if it's newer than us."""
        try:
            req = urllib.request.Request(
                RELEASES_API, headers={"User-Agent": f"YTGrab/{VERSION}"})
            with urllib.request.urlopen(req, timeout=6) as r:
                latest = json.load(r).get("tag_name", "")
        except Exception:
            return  # offline / rate-limited / repo missing — stay silent

        def parse(tag):
            try:
                return tuple(int(x) for x in tag.lstrip("vV").split("."))
            except ValueError:
                return (0,)

        if parse(latest) > parse(VERSION):
            def show():
                self.log(f"⬆ Update available! You have {VERSION}, "
                         f"latest is {latest}.")
                self.log(f"⬆ Get it here: {RELEASES_PAGE}")
                btn = ctk.CTkButton(
                    self, text=f"⬆  Update available: {latest} — click to download",
                    fg_color="#f9e2af", text_color="#11111b",
                    hover_color="#f5c76b", height=34,
                    command=lambda: webbrowser.open(RELEASES_PAGE))
                btn.grid(row=3, column=0, columnspan=2,
                         sticky="ew", padx=12, pady=(0, 12))
            self.after(0, show)

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.console.configure(state="normal")
        self.console.insert("end", f"[{ts}]  {msg}\n")
        self.console.see("end")
        self.console.configure(state="disabled")

    def clear_console(self):
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")

    def copy_console(self):
        self.clipboard_clear()
        self.clipboard_append(self.console.get("1.0", "end"))
        self.log("📋 Console copied to clipboard.")

    # ============================= Queue ================================
    def add_url(self):
        url = self.url_entry.get().strip()
        if not url:
            return
        if not url.lower().startswith(("http://", "https://")):
            messagebox.showwarning("Invalid URL", "Please enter a valid link.")
            return
        self.url_entry.delete(0, "end")

        # Playlist link? Expand it in the background so the UI doesn't freeze.
        if "list=" in url or "/playlist" in url:
            self.log("🔍 Playlist link detected — fetching video list…")
            threading.Thread(target=self._expand_playlist, args=(url,),
                             daemon=True).start()
        else:
            self._add_single(url)

    def _add_single(self, url, title=None, duration=0):
        item = QueueItem(url, quality=self.quality_var.get())
        if title:
            item.title = title
        item.duration = duration or 0
        self.queue_items.append(item)
        self._render_queue_item(item)
        self.log(f"➕ Added to queue: {title or url}")
        self._update_count()
        self._update_size_estimate()
        # No duration known (single link)? Fetch it quietly in the background.
        if not item.duration:
            threading.Thread(target=self._fetch_duration, args=(item,),
                             daemon=True).start()

    def _fetch_duration(self, item: QueueItem):
        try:
            opts = {"quiet": True, "no_warnings": True, "skip_download": True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(item.url, download=False)
            item.duration = info.get("duration") or 0
            title = info.get("title")
            if title:
                item.title = title
                self._set_item_title(item, title)
            self.after(0, self._update_size_estimate)
        except Exception:
            pass  # estimate just stays without this item

    # ------------------------- Size estimate ---------------------------
    def _update_size_estimate(self):
        pending = [i for i in self.queue_items if i.status != "Done"]
        total_secs = sum(i.duration for i in pending)
        if total_secs <= 0:
            self.size_label.configure(text="Est. size: —")
            return
        total_mb = sum(
            i.duration * BITRATE_ESTIMATES.get(i.quality, 5.0) / 8
            for i in pending)
        if total_mb >= 1024:
            text = f"Est. size: ~{total_mb / 1024:.2f} GB"
        else:
            text = f"Est. size: ~{total_mb:.0f} MB"
        hrs, rem = divmod(int(total_secs), 3600)
        mins = rem // 60
        text += f"  ({hrs}h {mins}m)" if hrs else f"  ({mins}m)"
        self.size_label.configure(text=text)

    def _expand_playlist(self, url):
        try:
            opts = {"quiet": True, "no_warnings": True,
                    "extract_flat": "in_playlist", "skip_download": True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            self.after(0, self.log, f"❌ Couldn't read playlist: {str(e)[:200]}")
            return

        entries = [e for e in (info.get("entries") or []) if e]
        if not entries:
            # Not actually a playlist (e.g. a video link with a stray list= param)
            self.after(0, self._add_single, url)
            return

        pl_title = info.get("title", "Playlist")
        count = len(entries)

        def ask_and_add():
            ok = messagebox.askyesno(
                "Playlist detected",
                f'"{pl_title}" contains {count} videos.\n\n'
                f"Add ALL {count} videos to the queue?")
            if not ok:
                self.log("🚫 Playlist add cancelled.")
                return
            for e in entries:
                vid_url = e.get("url") or e.get("webpage_url")
                if vid_url and not vid_url.startswith("http"):
                    vid_url = f"https://www.youtube.com/watch?v={vid_url}"
                if vid_url:
                    self._add_single(vid_url, title=e.get("title"),
                                     duration=e.get("duration") or 0)
            self.log(f"📃 Playlist added: {count} videos from “{pl_title}”.")
            self._update_size_estimate()

        self.after(0, ask_and_add)

    def paste_url(self):
        try:
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, self.clipboard_get().strip())
            self.add_url()
        except Exception:
            self.log("⚠ Clipboard is empty or unreadable.")

    def _render_queue_item(self, item: QueueItem):
        if self.empty_label.winfo_exists():
            self.empty_label.pack_forget()
        card = ctk.CTkFrame(self.queue_frame, fg_color="#1e1e2e", corner_radius=8)
        card.pack(fill="x", pady=4, padx=4)
        card.grid_columnconfigure(0, weight=1)

        item.title_label = ctk.CTkLabel(card, text=item.title, anchor="w",
                                        font=("Segoe UI", 12))
        item.title_label.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 0))
        item.status_label = ctk.CTkLabel(card,
                                         text=f"Queued  •  {item.quality_tag}",
                                         anchor="w",
                                         text_color="#7f849c", font=("Segoe UI", 11))
        item.status_label.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))
        rm = ctk.CTkButton(card, text="✕", width=30, height=30,
                           fg_color="#45475a", hover_color="#f38ba8",
                           command=lambda: self.remove_item(item, card))
        rm.grid(row=0, column=1, rowspan=2, padx=8)
        item.widget = card

    def remove_item(self, item, card):
        if item.status == "Downloading":
            self.log("⚠ Can't remove an item while it's downloading — use Skip.")
            return
        self.queue_items.remove(item)
        card.destroy()
        self._update_count()
        self._update_size_estimate()
        if not self.queue_items:
            self.empty_label.pack(pady=40)

    def clear_queue(self):
        if self.is_running:
            self.log("⚠ Stop the queue before clearing it.")
            return
        for it in self.queue_items:
            if it.widget:
                it.widget.destroy()
        self.queue_items.clear()
        self._update_count()
        self._update_size_estimate()
        self.empty_label.pack(pady=40)
        self.log("🗑 Queue cleared.")

    def _update_count(self):
        self.queue_count.configure(text=str(len(self.queue_items)))

    def _set_item_status(self, item, text, color="#7f849c"):
        def _apply():
            if item.widget and item.widget.winfo_exists():
                item.status_label.configure(
                    text=f"{text}  •  {item.quality_tag}", text_color=color)
        self.after(0, _apply)

    def _set_item_title(self, item, title):
        def _apply():
            if item.widget and item.widget.winfo_exists():
                item.title_label.configure(text=title)
        self.after(0, _apply)

    # =========================== Downloading ============================
    def choose_folder(self):
        folder = filedialog.askdirectory(initialdir=self.download_dir)
        if folder:
            self.download_dir = folder
            self.folder_btn.configure(text=self._short_path())
            self._save_current_settings()
            self.log(f"📁 Default download folder set: {folder}")
            self.log("💾 Saved — the app will use this folder from now on.")

    def _on_quality_change(self):
        self._update_size_estimate()
        self._save_current_settings()

    def _save_current_settings(self):
        save_settings({
            "download_dir": self.download_dir,
            "quality": self.quality_var.get(),
        })

    def start_queue(self):
        if self.is_running:
            return
        pending = [i for i in self.queue_items if i.status in ("Queued", "Skipped", "Error")]
        if not pending:
            self.log("⚠ Nothing to download — add some links first.")
            return
        self.is_running = True
        self.stop_flag.clear()
        self.start_btn.configure(state="disabled")
        self.skip_btn.configure(state="normal")
        self.stop_btn.configure(state="normal")
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()

    def skip_current(self):
        self.skip_flag.set()
        self.log("⏭ Skipping current download…")

    def stop_queue(self):
        self.stop_flag.set()
        self.skip_flag.set()
        self.log("⛔ Stopping after current item…")

    def _worker(self):
        for item in list(self.queue_items):
            if self.stop_flag.is_set():
                break
            if item.status not in ("Queued", "Skipped", "Error"):
                continue
            self.skip_flag.clear()
            item.status = "Downloading"
            self._set_item_status(item, "Downloading…", "#89b4fa")
            self.after(0, self.log, f"⬇ Starting: {item.url}")
            try:
                self._download_one(item)
                if self.skip_flag.is_set():
                    item.status = "Skipped"
                    self._set_item_status(item, "Skipped", "#f9e2af")
                else:
                    item.status = "Done"
                    self._set_item_status(item, "Completed ✔", "#a6e3a1")
                    self.after(0, self.log, f"✅ Finished: {item.title}")
                    self.after(0, self._update_size_estimate)
            except SkipDownload:
                item.status = "Skipped"
                self._set_item_status(item, "Skipped", "#f9e2af")
                self.after(0, self.log, "⏭ Item skipped.")
            except Exception as e:
                item.status = "Error"
                self._set_item_status(item, "Error ✖", "#f38ba8")
                self.after(0, self.log, f"❌ Error: {str(e)[:300]}")
        self.after(0, self._worker_done)

    def _worker_done(self):
        self.is_running = False
        self.start_btn.configure(state="normal")
        self.skip_btn.configure(state="disabled")
        self.stop_btn.configure(state="disabled")
        self.progress.set(0)
        self.speed_label.configure(text="")
        self.log("🏁 Queue finished.")

    def _download_one(self, item: QueueItem):
        choice = item.quality  # quality locked in when the item was added
        fmt = QUALITY_OPTIONS[choice]

        def hook(d):
            if self.skip_flag.is_set():
                raise SkipDownload()
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes", 0)
                pct = done / total if total else 0
                speed = (d.get("speed") or 0) / 1_048_576
                self.after(0, self.progress.set, pct)
                self.after(0, self.speed_label.configure,
                           {"text": f"{pct*100:5.1f}%  {speed:.2f} MB/s"})
                self._set_item_status(item, f"Downloading… {pct*100:.1f}%", "#89b4fa")
            elif d["status"] == "finished":
                self.after(0, self.speed_label.configure, {"text": "Merging…"})
                self._set_item_status(item, "Processing / merging…", "#cba6f7")

        ydl_opts = {
            "format": fmt,
            "outtmpl": os.path.join(self.download_dir, "%(title)s.%(ext)s"),
            "progress_hooks": [hook],
            "noplaylist": True,
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
        }
        if FFMPEG_DIR:
            ydl_opts["ffmpeg_location"] = FFMPEG_DIR

        if choice.startswith("Audio Only"):
            bitrate = "320" if "320" in choice else "192"
            ydl_opts.pop("merge_output_format", None)
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": bitrate,
            }]

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(item.url, download=True)
            item.title = info.get("title", item.url)
            self._set_item_title(item, item.title)


class SkipDownload(Exception):
    """Raised inside the progress hook to abort the current download."""


if __name__ == "__main__":
    app = YTGrabApp()
    app.mainloop()
