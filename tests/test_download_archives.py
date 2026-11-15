import functools
import http.server
import importlib.util
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from src.downloads import build_ytdl_cmd, process_urls, site_folder


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class DownloadArchiveTests(unittest.TestCase):
    def test_site_folder_for_audio_and_video(self):
        links = {
            "https://www.instagram.com/reel/example": "Instagram",
            "https://vm.tiktok.com/example": "TikTok",
            "https://www.tiktok.com/@creator/video/123": "TikTok",
            "https://www.facebook.com/reel/123": "Facebook",
            "https://fb.watch/example": "Facebook",
            "https://www.twitch.tv/videos/123": "Twitch",
            "https://clips.twitch.tv/example": "Twitch",
            "https://kick.com/creator/clips/example": "Kick",
            "https://youtu.be/example": "YouTube",
            "https://on.soundcloud.com/example": "SoundCloud",
            "https://soundcloud.com/creator/track": "SoundCloud",
            "https://open.spotify.com/track/example": "Spotify",
            "artist.bandcamp.com/album/example": "Bandcamp",
            "https://v.redd.it/example": "Reddit",
            "https://dai.ly/example": "Dailymotion",
            "https://www.example.co.uk:8443/video": "example.co.uk",
            "https://videos.example.org/w/example": "videos.example.org",
            "https://notinstagram.com/video": "notinstagram.com",
            "https://example.com@cdn.example.net/video": "cdn.example.net",
            "https://con.example/video": "_con.example",
            "https://[::1]/video": "_1",
        }
        for url, folder in links.items():
            with self.subTest(url=url):
                self.assertEqual(site_folder(url), folder)
                for video_mode in (False, True):
                    command = build_ytdl_cmd(url, Path("data"), video_mode)
                    self.assertEqual(command[command.index("--output") + 1],
                                     f"{folder}/%(uploader)s/%(title)s.%(ext)s")

    @unittest.skipUnless(
        importlib.util.find_spec("yt_dlp") and shutil.which("ffmpeg") and shutil.which("ffprobe"),
        "requires yt-dlp, FFmpeg and ffprobe",
    )
    def test_each_mode_downloads_once_and_preserves_the_other_file(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        source = root / "source"
        source.mkdir()
        subprocess.run([
            "ffmpeg", "-nostdin", "-v", "error",
            "-f", "lavfi", "-i", "color=size=64x64:rate=5:duration=1",
            "-f", "lavfi", "-i", "sine=duration=1",
            "-c:v", "mpeg4", "-c:a", "aac", str(source / "clip.mp4"),
        ], check=True)
        handler = functools.partial(QuietHandler, directory=str(source))
        server = self.enterContext(http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.shutdown)
        url = f"http://127.0.0.1:{server.server_port}/clip.mp4"

        for first_mode in (False, True):
            with self.subTest(video_first=first_mode):
                case = root / ("video-first" if first_mode else "audio-first")
                state, media, repeat = case / "data", case / "media", case / "repeat"
                state.mkdir(parents=True)
                legacy = state / ".dl_history_ytdl.txt"
                legacy.write_text("generic clip\n", encoding="utf-8")
                self.assertEqual(list(process_urls([], media, state)), [])
                self.assertEqual(list(media.iterdir()), [])

                assets = {}
                for mode in (first_mode, not first_mode):
                    result, = process_urls([url], media, state, video_mode=mode)
                    self.assertTrue(result.success, result.error)
                    suffix = ".mp4" if mode else ".mp3"
                    files = list(media.rglob(f"*{suffix}"))
                    self.assertEqual(len(files), 1, files)
                    self.assertEqual(files[0].relative_to(media).parts[0], "127.0.0.1")
                    self.assertEqual([p.name for p in media.iterdir()], ["127.0.0.1"])
                    assets[files[0]] = files[0].read_bytes()
                    self.assertTrue(assets[files[0]])

                for path, original in assets.items():
                    self.assertEqual(path.read_bytes(), original)

                # Simulate a download archived before site folders were introduced.
                old_file = repeat / "YouTube" / "NA" / "clip.mp4"
                old_file.parent.mkdir(parents=True)
                old_file.write_bytes(b"old copy")
                for mode in (False, True):
                    result, = process_urls([url], repeat, state, video_mode=mode)
                    self.assertTrue(result.success, result.error)
                self.assertEqual([p for p in repeat.rglob("*") if p.is_file()], [old_file])
                self.assertEqual(old_file.read_bytes(), b"old copy")
                self.assertEqual(legacy.read_text(encoding="utf-8"), "generic clip\n")

        with self.subTest(retry_after_save_failure=True):
            state, media = root / "retry-data", root / "retry-media"
            # Block the final MP3 path after conversion, then allow a retry.
            target = media / "127.0.0.1" / "NA" / "clip.mp3"
            target.mkdir(parents=True)
            failed, = process_urls([url], media, state)
            self.assertFalse(failed.success)
            target.rmdir()
            retried, = process_urls([url], media, state)
            self.assertTrue(retried.success, retried.error)
            self.assertTrue(target.is_file())
