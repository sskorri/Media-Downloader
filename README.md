# Just Another Media Downloader

## Windows desktop app

Open `Media Downloader.exe` beside `cli.py` to launch the desktop app. It uses a local `.venv`, your installed media tools, and Microsoft Edge WebView2. Keep the EXE beside the app files when you move it.

Paste a link, choose **Audio MP3** or **Video**, and select **Add to queue**. **Import batch file** reads one link per line. The theme switch applies immediately, including during downloads. **Settings** saves the theme, download folder, parallel downloads, and Spotify playlist threads in the app's `data/settings.json`.

The interface lives in `ui/index.html`, including its embedded React renderer, fonts, and animations. A normal launch shows real jobs and history. To see the original sample queue, run this from the project directory in PowerShell:

```powershell
& ".\Media Downloader.exe" --preview
```

For a source checkout, create the project `.venv` as described below, then run:

```powershell
.\.venv\Scripts\python.exe -m pip --disable-pip-version-check --no-cache-dir install -r ui/requirements.txt
python -m ui.gui
```

Run `.\ui\windows\build_gui.ps1` on Windows to build the launcher in the project root. The GUI and CLI in that folder share settings, history, and a download destination.

### Sharing

For GitHub, commit `cli.py`, `src/`, `ui/`, `tests/`, `requirements.txt`, `README.md`, `LICENSE`, and `.gitignore`. The root EXE, virtual environment, downloaded media, local app data and release ZIP are generated or machine-specific.

After building, run `python ui/windows/package_release.py` to create `dist/Media-Downloader-Windows-x64.zip`. Send this ZIP to someone who already has 64-bit Python 3.11 or newer with venv support, Node.js, FFmpeg (including ffprobe), and WebView2 on Windows. Node.js, FFmpeg and ffprobe should be on PATH. Extract the whole ZIP to a writable folder and open `Media Downloader.exe`. The first launch sets up `.venv` there and needs internet access for missing Python packages. The ZIP includes fresh settings and an empty `media/` folder.

To build for a PC without Python or the media tools, use `.\ui\windows\build_gui.ps1 -BundleRuntime` followed by `python ui/windows/package_release.py --bundle-runtime`. This produces a separate `dist/Media-Downloader-Windows-x64-Full.zip`. Both editions use the PC’s WebView2 installation.

## Supported links

The GUI and CLI accept the same links. Choose **Video** in the GUI or use `-v` in the CLI to keep video. **Audio MP3** extracts a soundtrack when the source has audio.

| Source | Examples |
| --- | --- |
| Instagram | Public Reels, video posts, and videos in carousels. Photo-only posts are unsupported. Stories and private posts can require a login. The app has no cookie-import control. |
| Social video | TikTok, Facebook Reels and videos, X/Twitter video posts, Reddit videos, Bluesky videos, Snapchat Spotlight |
| Video platforms | YouTube videos, Shorts and playlists, Vimeo, Dailymotion, Bilibili, Rumble, PeerTube |
| Streams and recordings | Public Twitch and Kick clips, past broadcasts, and supported live channels |
| Music and podcasts | SoundCloud tracks and sets, Bandcamp tracks and albums, Mixcloud mixes, Acast podcast episodes |
| News and archives | Supported BBC and NBC News videos, C-SPAN recordings, Internet Archive media |
| Direct links and embeds | Public audio or video files, unprotected HLS or DASH streams, and webpages with supported embedded players |
| Spotify | Music tracks, albums, playlists and artist links. spotDL matches songs on YouTube and saves MP3s with Spotify metadata. |

Support depends on the installed yt-dlp version and what a site makes available to an unsigned visitor. DRM-protected streams are unsupported. To see the extractors in your installation, run `.\.venv\Scripts\python.exe -m yt_dlp --list-extractors` from the app folder. [yt-dlp site catalog](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md) · [How spotDL sources audio](https://github.com/spotDL/spotify-downloader#music-sourcing-and-audio-quality)

## Why I made this

The standard way to download media, using "free" online converter websites is fundamentally broken. Most of those sites are riddled with pop-up ads, and aggressive tracking.
I wanted a way to download media that was:

1. **Private:** The tool keeps its settings and download history locally. The download engines contact the media and metadata providers.
2. **Transparent:** No hidden redirects or malware.
3. **Local:** The tool runs on my machine, using my credentials, and saves files directly to my folders.

## Why it's better

* **No Clipboard Spying:** Most browser extensions or web-based downloaders watch your clipboard or inject scripts into your page. This script does exactly what you tell it to do, and nothing else.
* **No Ad-ware:** You aren't being served ads while waiting for a download.
* **Actually Reliable:** By using `yt-dlp` and `spotdl` as the backend, you get the benefit of massive, actively maintained open-source projects.
* **Full Control:** You can automate it with cron, run it in parallel, or keep a local history log. It integrates into your workflow, not the other way around.

## Features

* **Format Flexibility:** Downloads audio by default (mp3); optional video mode.
* **Download folders.** New downloads use the site in the link you submit, for example `media/Instagram/<uploader>/`, `media/TikTok/<uploader>/`, `media/Facebook/<uploader>/`, `media/Twitch/<uploader>/`, `media/Kick/<uploader>/`, or `media/SoundCloud/<uploader>/`. Other sites use their hostname when there is no named folder. Spotify keeps its list folder and artist/title filenames. Site folders are created as downloads write their files. Updating the app leaves earlier downloads in place and continues to honor the existing audio and video archives.
* **Archive and history:** yt-dlp keeps separate MP3 and video archives. You can download both formats for the same link in either order. Repeating a download in the same mode skips IDs already in that mode's archive. The history log records successes and failures from both engines.
* **Batch/Queue Support:** Process lists of links or run it as a background job via a synced `.txt` file (perfect for syncing with phone apps like Syncthing).
* **Parallel Downloads:** Supports concurrent downloads to speed up large playlists.

## Quick Start

### 1. Requirements

Use Python 3.11 or newer with venv support, and put FFmpeg and ffprobe on PATH. For full YouTube support, install a supported Deno or Node.js runtime. See [yt-dlp's JavaScript runtime guide](https://github.com/yt-dlp/yt-dlp/wiki/EJS).

* **macOS:** `brew install ffmpeg`
* **Linux:** Ubuntu `sudo apt update && sudo apt install ffmpeg`
             Debian `sudo apt update && sudo apt install ffmpeg`

* **Enable RPM Fusion repositories for Fedora**
`sudo dnf install https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm` then `sudo dnf install ffmpeg`
* **Windows:** Download from [ffmpeg.org](https://ffmpeg.org/) and add to PATH.

### 2. Install

Run these commands from the project directory. On Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip --disable-pip-version-check --no-cache-dir install -r requirements.txt
```

On macOS or Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip --disable-pip-version-check --no-cache-dir install -r requirements.txt
```

After setup, `python cli.py` automatically uses the project's `.venv` for both the CLI and its engines. Activation is optional. On systems where the interpreter is named `python3`, use `python3 cli.py`.

### 3. Usage

Download a single track:

```bash
python cli.py "https://youtube.com/watch?v=..."

```

Download a list from a file:

```bash
python cli.py -b links.txt

```

Process your synced queue (for automation):

```bash
python cli.py --cron

```

Show last 20 downloads:

```bash
python cli.py --history

```

Use `-v` to keep video for yt-dlp links. For direct URLs and batch files, `--parallel N` runs up to N URLs at once and `--threads N` sets spotDL's tracks per playlist. Queue mode processes one snapshot, sequentially, in audio mode. A scheduler can call it repeatedly. Completed snapshots are consumed even when an individual URL fails. Use `--history` to find failed links.

### 4. Download directory and local files

The shared ZIP starts with `media/` beside the EXE. A source checkout without a saved destination defaults to `~/Downloads`. To keep downloads with the application, run the following from the project directory:

```powershell
python cli.py --set-download-dir "./media"
python cli.py --settings
```

Saving the destination creates both the download folder and the project's `data/` folder. A download also creates either folder if needed.

You can also supply an absolute path such as `D:\Music`. The setting applies to future direct, batch, and queue downloads. Both archives stay with the project when you change the download directory. Paths inside the project are saved relative to the project, so subsequent commands work from another directory.

The project keeps settings in `data/settings.json` and stores history, download archives, backend configuration, caches, and conversion files under `data/`. The default queue is `data/download_queue.txt`. Use `--cron --queue-file PATH` for a queue synced elsewhere.

When present, earlier home-directory history and archive files are copied into `data/` on first use. If the project queue is absent, `--cron` can still consume an existing `~/download_queue.txt`.

The old `.dl_history_ytdl.txt` archive recorded only media IDs. It is kept for reference. The audio and video archives start empty, so a link from before the split may be processed once per mode.

---

*This tool is intended for personal use and archival purposes. Please respect the copyright of the content creators.*
