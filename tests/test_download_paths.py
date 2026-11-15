import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.downloads import process_urls


class SpotifyRevealTests(unittest.TestCase):
    def test_report_uses_tracks_from_this_job_and_groups_playlists(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        media = root / "My  Music"
        album = media / "Spotify" / "My mix"
        album.mkdir(parents=True)
        tracks = [album / "Artist - One.mp3", album / "Artist - Two.mp3"]
        for path in tracks:
            path.touch()
        unrelated = media / "unrelated.mp3"
        unrelated.touch()

        for count, expected in [(1, tracks[0]), (2, album)]:
            with self.subTest(tracks=count):
                def spotdl(command, *, cwd, **kwargs):
                    report = cwd / command[command.index("--m3u") + 1]
                    entries = [p.relative_to(cwd).as_posix() for p in tracks[:count]]
                    report.write_text("\n".join(["#EXTM3U", "#EXTINF:1,info", *entries,
                                                 str(unrelated), "Spotify/Missing.mp3"]), encoding="utf-8")
                    Path(command[command.index("--save-file") + 1]).write_text("[]", encoding="utf-8")
                    return subprocess.CompletedProcess(command, 0, "", "")

                with patch("src.downloads.subprocess.run", side_effect=spotdl):
                    result, = process_urls(["https://open.spotify.com/playlist/example"], media, root / "data")
                self.assertTrue(result.success, result.error)
                self.assertEqual(result.reveal_path, expected)
                self.assertEqual(set(media.iterdir()), {media / "Spotify", unrelated})
