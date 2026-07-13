# YTGrab ⬇

**A free, open-source video downloader for Windows — queue whole playlists, pick your quality, zero setup.**

🌐 **Website:** https://astavkhra.github.io/YTGrab/
📦 **Download:** [Latest release](https://github.com/astavkhra/YTGrab/releases/latest)

<!-- Add a screenshot: drag an image of the app into this file while editing on GitHub,
     and it will insert the link automatically. -->

---

## ✨ Features

- **Batch queue** — add 5 or 500 videos, hit Start once, walk away
- **Playlist support** — paste a playlist link and add every video in one go (with a confirmation first)
- **Quality options** — 360p up to 8K, or audio-only MP3 (320k / 192k)
- **Per-video quality** — each queued item remembers the quality it was added with, so you can mix and match
- **Size estimates** — see the estimated total size and watch-time of your queue before downloading
- **Live progress** — per-video status, download speed, skip and stop controls
- **Remembers your settings** — download folder and favorite quality persist between sessions
- **Update notices** — the app tells you when a newer version is available
- **All-in-one** — FFmpeg and the yt-dlp engine are bundled inside the exe. No Python, no command line, nothing to install.

## 🚀 Getting started (no setup needed)

1. Download **YTGrab.zip** from the [latest release](https://github.com/astavkhra/YTGrab/releases/latest)
2. Right-click the zip → **Extract All** → open the folder
3. Double-click **YTGrab.exe**
4. Paste a video or playlist URL → choose a quality → **Start**

Videos are saved to your Downloads folder by default — click the folder button (bottom-right) to change it. Your choice is remembered.

### ⚠ "Windows protected your PC"?

That blue SmartScreen warning appears for any app from an independent developer that isn't code-signed (certificates cost hundreds of dollars a year). Click **More info → Run anyway**.

This app is open source — the complete code is in [`ytgrab.py`](ytgrab.py) in this repository, so you can read exactly what it does, or build it yourself (below).

## 🐍 Running from source (Mac / Linux / the curious)

```bash
pip install customtkinter yt-dlp
# also install ffmpeg:  winget install ffmpeg  |  brew install ffmpeg  |  sudo apt install ffmpeg
python ytgrab.py
```

## 🔨 Building the exe yourself

With `ffmpeg.exe` and `ffprobe.exe` in the same folder as `ytgrab.py`:

```bash
pip install customtkinter yt-dlp pyinstaller
python -m PyInstaller --onefile --noconsole --collect-all customtkinter --add-binary "ffmpeg.exe;." --add-binary "ffprobe.exe;." --name YTGrab ytgrab.py
```

The finished exe appears in the `dist` folder.

## 🔄 Updating

When a newer version exists, the app shows a yellow banner on launch — click it, download the new zip, and replace your old YTGrab.exe. Your settings are kept automatically.

If downloads suddenly start failing, an update is almost always the fix — YouTube changes things regularly, and updates keep the downloader compatible.

## ❓ FAQ

**Is it free?** Yes — free and open source under the MIT license. No ads, no accounts.

**I picked 4K but the video is only 1080p?** You automatically get the best quality that actually exists — never an error.

**Where do playlist videos go?** Same folder as everything else, each as its own file.

**Antivirus flagged it?** PyInstaller-built apps trigger false positives sometimes. The source is public — build it yourself if you'd rather not trust a prebuilt exe.

## ⚖ Disclaimer

YTGrab is a tool for downloading content you own or have permission to download — your own uploads, Creative Commons material, and similar. Downloading most YouTube content violates YouTube's Terms of Service. You are responsible for how you use this tool. **Respect creators.**

## 🙏 Built with

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — the download engine
- [FFmpeg](https://ffmpeg.org/) — merging & audio conversion
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) — the UI

## 📄 License

MIT — see [LICENSE](LICENSE).
