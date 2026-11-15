"""Route media URLs and run the download engines using the active interpreter."""

import os
import re
import shutil
import signal
import subprocess
import sys
from collections import deque
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from urllib.parse import urlsplit


@dataclass(frozen=True)
class DownloadResult:
    url: str
    tool: str
    success: bool
    error: str = ""


class DownloadControl:
    """Own one GUI job's process, its descendants, and its progress stream."""

    progress_prefix = "jamd-progress:"

    def __init__(self, report: Callable[[int], None]):
        self.report = report
        self._lock = Lock()
        self._process = None
        self.cancelled = False

    def cancel(self):
        with self._lock:
            self.cancelled = True
            process = self._process
        if process is None or process.poll() is not None:
            return
        if os.name == "nt":
            # yt-dlp and spotDL can have live FFmpeg / JavaScript subprocesses.
            taskkill = Path(os.environ["SystemRoot"]) / "System32" / "taskkill.exe"
            try:
                subprocess.run([str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                               creationflags=subprocess.CREATE_NO_WINDOW,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
            except (OSError, subprocess.TimeoutExpired):
                pass
            finally:
                if process.poll() is None:
                    process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def run(self, command, cwd, env, spotify):
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        with self._lock:
            if self.cancelled:
                return subprocess.CompletedProcess(command, 1, "", "Cancelled")
            process = self._process = subprocess.Popen(
                command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, encoding="utf-8", errors="replace",
                creationflags=flags, start_new_session=os.name != "nt",
            )
        tail = deque(maxlen=20)
        try:
            with process, process.stdout:
                for line in process.stdout:
                    line = line.strip()
                    if line.startswith(self.progress_prefix):
                        percent = line.removeprefix(self.progress_prefix).strip().removesuffix("%")
                        try:
                            progress = round(float(percent))
                        except (ValueError, OverflowError):
                            continue
                        self.report(max(0, min(100, progress)))
                    elif spotify and (count := re.fullmatch(r"(\d{1,8})/(\d{1,8}) complete", line)):
                        complete, total = map(int, count.groups())
                        if total and complete <= total:
                            self.report(round(100 * complete / total))
                    elif line:
                        tail.append(line[-2000:])
            return subprocess.CompletedProcess(command, process.returncode, "", "\n".join(tail))
        finally:
            with self._lock:
                self._process = None


def engine_python() -> str:
    executable = Path(sys.executable)
    if executable.name.lower() == "pythonw.exe":
        return str(executable.with_name("python.exe"))
    return sys.executable


_SITE_FOLDERS = {
    "youtube.com": "YouTube", "youtu.be": "YouTube", "youtube-nocookie.com": "YouTube",
    "soundcloud.com": "SoundCloud", "snd.sc": "SoundCloud",
    "spotify.com": "Spotify",
    "instagram.com": "Instagram", "instagr.am": "Instagram",
    "tiktok.com": "TikTok",
    "facebook.com": "Facebook", "fb.watch": "Facebook", "fb.com": "Facebook",
    "twitter.com": "X", "x.com": "X",
    "bsky.app": "Bluesky",
    "snapchat.com": "Snapchat",
    "reddit.com": "Reddit", "redd.it": "Reddit",
    "vimeo.com": "Vimeo",
    "dailymotion.com": "Dailymotion", "dai.ly": "Dailymotion",
    "bilibili.com": "Bilibili", "b23.tv": "Bilibili",
    "rumble.com": "Rumble",
    "twitch.tv": "Twitch",
    "kick.com": "Kick",
    "bandcamp.com": "Bandcamp",
    "mixcloud.com": "Mixcloud",
    "acast.com": "Acast",
    "bbc.co.uk": "BBC", "bbc.com": "BBC",
    "nbcnews.com": "NBC News",
    "c-span.org": "C-SPAN",
    "archive.org": "Internet Archive",
}


def site_folder(url: str) -> str:
    """Use the pasted link's site for every item in the job, including playlists."""
    try:
        host = (urlsplit(url if "://" in url else "//" + url).hostname or "").rstrip(".")
    except ValueError:
        return "Other"
    for domain, folder in _SITE_FOLDERS.items():
        if host == domain or host.endswith("." + domain):
            return folder

    # Keep unknown hosts to one portable path component, also safe in a yt-dlp template.
    name = re.sub(r"[^\w.-]+", "_", host.removeprefix("www.")).strip(".")[:253].rstrip(".")
    if re.match(r"^(con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(\.|$)", name, re.I):
        name = "_" + name
    return name or "Other"


def detect_platform(url: str) -> str:
    """Return the provider identifier used by the download engines and GUI badges."""
    folder = site_folder(url)
    return folder.lower() if folder in ("Spotify", "SoundCloud", "YouTube") else "other"


def backend_environment(state_dir: Path, temp_dir: Path) -> dict[str, str]:
    """Confine the child tools' profile, caches and temporary files to the app."""
    cache = state_dir / "cache"
    # spotDL uses Path.home() even when a cache path is passed explicitly.
    return {
        **os.environ,
        "HOME": str(state_dir),
        "USERPROFILE": str(state_dir),
        "APPDATA": str(state_dir),
        "LOCALAPPDATA": str(cache),
        "XDG_CONFIG_HOME": str(state_dir / ".config"),
        "XDG_CACHE_HOME": str(cache),
        "XDG_DATA_HOME": str(state_dir),
        "XDG_STATE_HOME": str(state_dir),
        "DENO_DIR": str(cache / "deno"),
        "TEMP": str(temp_dir),
        "TMP": str(temp_dir),
        "TMPDIR": str(temp_dir),
    }


def build_ytdl_cmd(url: str, state_dir: Path, video_mode: bool) -> list[str]:
    folder = site_folder(url)
    mode = "video" if video_mode else "audio"
    entrypoint = ["-m", "yt_dlp"] if video_mode else [str(Path(__file__).resolve())]
    command = [
        engine_python(), "-I", "-X", "utf8", *entrypoint,
        "--ignore-config", "--no-mtime", "--embed-metadata", "--embed-thumbnail",
        "--js-runtimes", "node",
        "--cache-dir", str(state_dir / "cache" / "yt-dlp"),
        "--download-archive", str(state_dir / f".dl_history_ytdl_{mode}.txt"),
        "--output", f"{folder}/%(uploader)s/%(title)s.%(ext)s",
    ]
    if not video_mode:
        command.extend(["-x", "--audio-format", "mp3", "--audio-quality", "0"])
    return [*command, "--", url]


def _run_audio_worker(args: list[str]) -> int:
    """Extract in the job's temp folder so yt-dlp cannot consume a saved video."""
    from yt_dlp import YoutubeDL, parse_options

    library = Path.cwd()
    scratch = Path(os.environ["TMPDIR"])
    options = parse_options(args)
    options.ydl_opts["paths"]["home"] = str(scratch)

    def publish_mp3(filename: str) -> None:
        source = Path(filename)
        target = library / source.relative_to(scratch)
        if target.is_file():
            source.unlink()
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        # The library may be on another drive. Publish a complete file before
        # yt-dlp records this item in the audio archive.
        with TemporaryDirectory(dir=target.parent) as staging:
            staged = Path(staging) / target.name
            shutil.move(source, staged)
            staged.replace(target)

    with YoutubeDL(options.ydl_opts) as engine:
        engine.add_post_hook(publish_mp3)
        return engine.download(options.urls)


def build_spotdl_cmd(url: str, work_dir: Path, threads: int) -> list[str]:
    return [
        engine_python(), "-I", "-X", "utf8", "-m", "spotdl", "download", url,
        "--output", "Spotify/{list-name}/{artists} - {title}.{output-ext}",
        "--lyrics", "genius", "--generate-lrc", "--bitrate", "320k", "--format", "mp3",
        "--save-file", str(work_dir / "tracks.spotdl"),
        "--save-errors", str(work_dir / "errors.txt"),
        "--yt-dlp-args=--ignore-config --js-runtimes node",
        "--threads", str(threads),
    ]


def download_single(
    url: str, download_dir: Path, state_dir: Path,
    video_mode: bool, threads: int, control: DownloadControl | None = None,
) -> DownloadResult:
    platform = detect_platform(url)
    tool = "spotdl" if platform == "spotify" else "yt-dlp"
    try:
        with TemporaryDirectory(dir=state_dir / "tmp") as temp:
            work_dir = Path(temp)
            if platform == "spotify":
                command = build_spotdl_cmd(url, work_dir, threads)
            else:
                command = build_ytdl_cmd(url, state_dir, video_mode)

            env = backend_environment(state_dir, work_dir)
            if control is None:
                process = subprocess.run(command, cwd=download_dir, env=env, capture_output=True,
                                         encoding="utf-8", errors="replace",
                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            else:
                command.insert(1, "-u")
                if platform == "spotify":
                    command.append("--simple-tui")
                else:
                    command[-2:-2] = ["--newline", "--progress", "--color", "never",
                                      "--progress-template", f"download:{control.progress_prefix}%(progress._percent_str)s"]
                process = control.run(command, download_dir, env, platform == "spotify")
            if process.returncode:
                message = process.stderr.strip() or process.stdout.strip()
                return DownloadResult(url, tool, False, message or f"Exit code {process.returncode}")

            if platform == "spotify":
                # spotDL may exit successfully even if individual playlist tracks failed.
                errors = work_dir / "errors.txt"
                if errors.exists() and (detail := errors.read_text(encoding="utf-8").strip()):
                    return DownloadResult(url, tool, False, detail)
                # Each concurrent job writes its own export before publishing it.
                (work_dir / "tracks.spotdl").replace(state_dir / ".spotdl_cache.spotdl")
    except OSError as exc:
        return DownloadResult(url, tool, False, str(exc))
    return DownloadResult(url, tool, True)


def process_urls(
    urls: Iterable[str], download_dir: Path, state_dir: Path,
    video_mode: bool = False, threads: int = 4, parallel: int = 1,
) -> Iterator[DownloadResult]:
    """Yield one result per input URL as downloads finish."""
    download_dir = download_dir.resolve()
    download_dir.mkdir(parents=True, exist_ok=True)
    state_dir = state_dir.resolve()
    (state_dir / "tmp").mkdir(parents=True, exist_ok=True)
    download = partial(
        download_single, download_dir=download_dir, state_dir=state_dir,
        video_mode=video_mode, threads=threads,
    )
    if parallel <= 1:
        yield from map(download, urls)
        return

    with ThreadPoolExecutor(max_workers=parallel) as executor:
        futures = [executor.submit(download, url) for url in urls]
        for future in as_completed(futures):
            yield future.result()


if __name__ == "__main__":
    raise SystemExit(_run_audio_worker(sys.argv[1:]))
