"""Settings, download history, and text queues for the local downloader."""

import json
import locale
import os
import shutil
from collections import deque
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4


PROJECT_DIR = Path(__file__).resolve().parents[1]
STATE_DIR = PROJECT_DIR / "data"
SETTINGS_FILE = STATE_DIR / "settings.json"
HISTORY_NAME = ".dl_history.json"
QUEUE_NAME = "download_queue.txt"
DEFAULT_QUEUE_FILE = STATE_DIR / QUEUE_NAME


def _move_if_missing(source: Path, destination: Path) -> None:
    """Publish a complete file without replacing another process's file."""
    if os.name == "nt":
        source.rename(destination)  # Windows rename fails if the target exists.
    else:
        os.link(source, destination)
        source.unlink()


def _import_legacy_file(old_name: str, new_name: str) -> Path:
    destination = STATE_DIR / new_name
    original = Path.home() / old_name
    if destination.exists() or not original.is_file():
        return destination

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=STATE_DIR) as temporary:
        staged = Path(temporary) / new_name
        shutil.copyfile(original, staged)
        try:
            _move_if_missing(staged, destination)
        except FileExistsError:
            pass  # Another invocation has already imported this file.
    return destination


def initialize_state() -> None:
    """Create the project data directory and retain earlier download records."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _import_legacy_file(HISTORY_NAME, HISTORY_NAME)
    _import_legacy_file(".dl_history_ytdl.txt", ".dl_history_ytdl.txt")
    _import_legacy_file(".spotdl_cache.json", ".spotdl_cache.spotdl")


def _settings() -> dict:
    try:
        settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read {SETTINGS_FILE}: {exc}") from exc
    if not isinstance(settings, dict):
        raise ValueError(f"Expected a JSON object in {SETTINGS_FILE}")
    return settings


@contextmanager
def _settings_write_lock():
    """Serialize read/modify/write across GUI instances and the CLI."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with (STATE_DIR / ".settings.lock").open("a+b") as lock:
        lock.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
        # Closing the handle releases either type of lock, including on failure.
        yield


def _update_setting(key: str, value) -> None:
    with _settings_write_lock():
        settings = _settings()
        settings[key] = value
        with TemporaryDirectory(dir=STATE_DIR) as temporary:
            staged = Path(temporary) / SETTINGS_FILE.name
            staged.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            staged.replace(SETTINGS_FILE)


def _gui_preference(key, value):
    if key == "theme" and value in ("light", "dark"):
        return value
    maximum = {"parallel": 8, "threads": 16}.get(key)
    if maximum and type(value) is int and 1 <= value <= maximum:
        return value
    raise ValueError(f"Invalid {key} preference.")


def read_gui_preferences() -> dict:
    saved = _settings()
    defaults = {"theme": "light", "parallel": 1, "threads": 4}
    return {k: _gui_preference(k, saved.get(k, v)) for k, v in defaults.items()}


def set_gui_preference(key: str, value) -> None:
    _update_setting(key, _gui_preference(key, value))


def read_window_position() -> tuple[int, int] | None:
    position = _settings().get("window_position")
    if (isinstance(position, list) and len(position) == 2
            and all(type(n) is int and -(2**31) <= n < 2**31 for n in position)):
        return position[0], position[1]
    return None


def set_window_position(x: int, y: int) -> None:
    _update_setting("window_position", [x, y])


def _directory(value: str, relative_to: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("The download directory must be a nonempty path.")
    directory = (relative_to / Path(value).expanduser()).resolve()
    if directory.exists() and not directory.is_dir():
        raise NotADirectoryError(f"Download path is not a directory: {directory}")
    return directory


def read_download_dir() -> Path:
    settings = _settings()
    if "download_dir" not in settings:
        return Path.home() / "Downloads"
    return _directory(settings["download_dir"], PROJECT_DIR)


def set_download_dir(value: str | Path) -> Path:
    directory = _directory(os.fspath(value), Path.cwd())
    directory.mkdir(parents=True, exist_ok=True)
    if directory.is_relative_to(PROJECT_DIR):
        setting = directory.relative_to(PROJECT_DIR).as_posix()
    else:
        setting = str(directory)
    _update_setting("download_dir", setting)
    return directory


def log_download(url: str, status: str, tool: str, extra: str = "") -> None:
    path = _import_legacy_file(HISTORY_NAME, HISTORY_NAME)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = dict(url=url, status=status, tool=tool, timestamp=datetime.now().isoformat(), extra=extra)
    with path.open("a", encoding="utf-8") as history:
        history.write(json.dumps(entry) + "\n")


def recent_history(n: int = 20) -> list[dict]:
    path = _import_legacy_file(HISTORY_NAME, HISTORY_NAME)
    if not path.exists() or n <= 0:
        return []
    with path.open(encoding="utf-8-sig", errors="replace") as history:
        entries = deque(maxlen=n)
        for line in history:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict) or entry.get("status") not in ("success", "failed"):
                continue
            if all(isinstance(entry.get(key), str) for key in ("timestamp", "tool", "url")):
                entries.append(entry)
    return list(entries)


def read_urls(path: Path) -> list[str]:
    path = Path(path)
    try:
        content = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        # Older batch and queue files can use the operating system's text encoding.
        content = path.read_text(encoding=locale.getpreferredencoding(False))
    lines = (line.strip() for line in content.splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def default_queue_path() -> Path:
    legacy = Path.home() / QUEUE_NAME
    return legacy if not DEFAULT_QUEUE_FILE.exists() and legacy.is_file() else DEFAULT_QUEUE_FILE


@contextmanager
def claimed_queue(path: Path):
    """Consume one snapshot. New arrivals at the original path wait for the next run."""
    path = Path(path)
    if path.exists() and not path.is_file():
        raise OSError(f"Queue is not a file: {path}")
    processing = path.with_name(f"{path.name}.{uuid4().hex}.processing")
    try:
        path.rename(processing)
    except FileNotFoundError:
        yield None
        return

    try:
        yield read_urls(processing)
    except BaseException as exc:
        try:
            _move_if_missing(processing, path)
        except OSError:
            raise OSError(f"Queue interrupted. Its unconsumed snapshot is at {processing}") from exc
        raise
    else:
        processing.unlink()
