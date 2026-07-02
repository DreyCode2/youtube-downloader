# Video Downloader

A simple desktop app for downloading videos with yt-dlp, built with a CustomTkinter interface. No terminal commands to remember: paste the URL, pick a format, done.

Everything lives in a single file (`ytdown.py`), no complicated project structure or weird dependencies.

## What it does

- Paste a URL and it pulls the title, duration, and thumbnail before you download anything.
- Three formats: full video (best quality), audio only (MP3), or video only, no audio track.
- You choose the destination folder.
- Live progress bar with percentage, speed, and ETA.
- Cancel button to stop a download mid-way.
- Errors show up as plain, readable messages instead of a Python traceback.

Downloads run on a background thread, so the interface never freezes while something heavy is downloading.

## Requirements

- Python 3.9 or newer.

## Installation

```bash
pip install -r requirements.txt
```

That installs CustomTkinter, yt-dlp, and Pillow:

## Usage

```bash
python ytdown.py
```

1. Paste the video URL.
2. Click "Fetch Info" to see the title, duration, and thumbnail.
3. Pick a format and an output folder.
4. Click "Download".

Changed your mind mid-download? "Cancel" stops it cleanly without leaving half-finished files scattered around.

## Available formats

| Option | What it gets |
|---|---|
| Best Video | Best video + best audio, merged into MP4 |
| Audio Only | Audio only, converted to MP3 |
| Video Only | Video only, no audio track |
