"""The live desktop queue. UI calls may arrive on different WebView threads."""

from dataclasses import dataclass
from pathlib import Path
from threading import RLock, Thread
from urllib.parse import urlsplit

from src import storage
from src.downloads import DownloadControl, DownloadResult, detect_platform, download_single, site_folder
from ui.explorer import reveal_in_folder


def _display_dir(path: Path) -> str:
    return path.relative_to(storage.PROJECT_DIR).as_posix() if path.is_relative_to(storage.PROJECT_DIR) else str(path)


def _media_url(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Enter a media link.")
    url = value.strip()
    if "://" not in url:
        url = "https://" + url
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or any(c.isspace() for c in parts.netloc):
        raise ValueError("Enter an HTTP or HTTPS media link.")
    return url


@dataclass
class QueueItem:
    id: int
    url: str
    platform: str
    folder: str
    video: bool
    state: str = "queue"
    percent: int | None = 0
    error: str = ""
    destination: str = ""
    reveal_path: Path | None = None

    def snapshot(self):
        return {"id": self.id, "url": self.url.split("://", 1)[1], "plat": self.platform, "folder": self.folder,
                "video": self.video, "st": self.state, "pct": self.percent,
                "error": self.error, "dir": self.destination, "canReveal": self.reveal_path is not None}


class GuiController:
    def __init__(self):
        self._lock = RLock()
        self._closed = False
        self._items: dict[int, QueueItem] = {}
        self._active: dict[int, tuple[DownloadControl, Thread]] = {}
        self._next_id = 1
        self._preferences = storage.read_gui_preferences()
        self._destination = storage.read_download_dir()
        self._history = []
        self._history_version = None
        storage.initialize_state()

    def _refresh_history(self):
        path = storage.STATE_DIR / storage.HISTORY_NAME
        try:
            stat = path.stat()
            version = (stat.st_mtime_ns, stat.st_size)
        except FileNotFoundError:
            version = None
        if version != self._history_version:
            self._history = [
                {"ok": entry["status"] == "success", "time": entry["timestamp"][:16].replace("T", " "),
                 "tool": entry["tool"], "url": entry["url"]}
                for entry in reversed(storage.recent_history())
            ]
            self._history_version = version

    def snapshot(self, input_url=""):
        with self._lock:
            self._refresh_history()
            preview = None
            if input_url:
                try:
                    url = _media_url(input_url)
                except ValueError:
                    pass  # A partially typed link has no destination to display yet.
                else:
                    folder = site_folder(url)
                    preview = {"url": input_url, "folder": folder, "spotify": detect_platform(url) == "spotify",
                               "dir": _display_dir(self._destination / folder)}
            return {
                "theme": self._preferences["theme"], "dir": _display_dir(self._destination),
                "par": self._preferences["parallel"], "thr": self._preferences["threads"],
                "items": [item.snapshot() for item in self._items.values()], "hist": list(self._history),
                "preview": preview,
            }

    def enqueue(self, urls, video=False):
        if isinstance(urls, str):
            urls = [urls]
        if not isinstance(urls, (tuple, list)):
            raise ValueError("Expected a list of media links.")
        links = [_media_url(url) for url in urls]
        with self._lock:
            if self._closed:
                raise RuntimeError("The download window is closing.")
            for url in links:
                platform = detect_platform(url)
                item = QueueItem(self._next_id, url, platform, site_folder(url), bool(video) and platform != "spotify")
                self._items[item.id] = item
                self._next_id += 1
            self._schedule()
            return self.snapshot()

    def _schedule(self):
        for item in self._items.values():
            if self._closed or len(self._active) >= self._preferences["parallel"]:
                break
            if item.state != "queue":
                continue
            item.state = "run"
            item.percent = None
            item.destination = _display_dir(self._destination / item.folder)
            control = DownloadControl(lambda value, key=item.id: self._progress(key, value))
            worker = Thread(target=self._download, args=(item, self._destination, self._preferences["threads"], control),
                            name=f"download-{item.id}", daemon=True)
            self._active[item.id] = (control, worker)
            worker.start()

    def _progress(self, key, value):
        with self._lock:
            if key in self._items:
                self._items[key].percent = value

    def _download(self, item, destination, threads, control):
        try:
            destination.mkdir(parents=True, exist_ok=True)
            (storage.STATE_DIR / "tmp").mkdir(parents=True, exist_ok=True)
            result = download_single(item.url, destination, storage.STATE_DIR, item.video, threads, control)
        except Exception as exc:
            tool = "spotdl" if item.platform == "spotify" else "yt-dlp"
            result = DownloadResult(item.url, tool, False, str(exc))

        with self._lock:
            try:
                if item.id in self._items and not control.cancelled:
                    item.state = "done" if result.success else "fail"
                    item.percent = 100 if result.success else 0
                    if result.success and result.reveal_path is not None:
                        item.reveal_path = result.reveal_path
                        folder = item.reveal_path if item.reveal_path.is_dir() else item.reveal_path.parent
                        item.destination = _display_dir(folder)
                    lines = result.error.splitlines()
                    errors = [line for line in lines if line.startswith("ERROR:")]
                    item.error = (errors or lines or [""])[-1][:1200]
                    storage.log_download(item.url, "success" if result.success else "failed",
                                         result.tool, result.error)
            finally:
                self._active.pop(item.id, None)
                self._schedule()

    def action(self, item_id, action):
        control = None
        reveal_path = None
        with self._lock:
            item = self._items.get(item_id)
            if item is None:
                return self.snapshot()
            if action == "reveal" and item.state == "done" and item.reveal_path is not None:
                reveal_path = item.reveal_path
            elif action == "retry" and item.state == "fail":
                item.state, item.error, item.percent = "queue", "", 0
            elif action in ("cancel", "remove"):
                if item.id in self._active:
                    control, _ = self._active[item.id]
                del self._items[item.id]
            else:
                raise ValueError("This action is unavailable for the selected download.")
            self._schedule()
        if control is not None:
            control.cancel()
        if reveal_path is not None:
            reveal_in_folder(reveal_path)
        return self.snapshot()

    def clear_finished(self):
        with self._lock:
            self._items = {key: item for key, item in self._items.items() if item.state != "done"}
            return self.snapshot()

    def set_pref(self, key, value):
        keys = {"theme": "theme", "par": "parallel", "thr": "threads"}
        if key not in keys:
            raise ValueError("Unknown download preference.")
        with self._lock:
            name = keys[key]
            storage.set_gui_preference(name, value)
            self._preferences[name] = value
            self._schedule()
            return self.snapshot()

    def save_dir(self, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("The download directory must be a nonempty path.")
        with self._lock:
            self._destination = storage.set_download_dir(storage.PROJECT_DIR / Path(value.strip()).expanduser())
            return self.snapshot()

    def shutdown(self):
        with self._lock:
            self._closed = True
            active = list(self._active.values())
        for control, _ in active:
            control.cancel()
        for _, worker in active:
            worker.join()
