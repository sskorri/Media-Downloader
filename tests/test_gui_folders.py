import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from src import storage
from src.downloads import DownloadResult
from ui.gui_controller import GuiController


class GuiFolderTests(unittest.TestCase):
    def test_running_job_keeps_its_site_folder_when_destination_changes(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.enterContext(patch.dict(os.environ, {"HOME": str(root), "USERPROFILE": str(root)}))
        self.enterContext(patch.multiple(storage, PROJECT_DIR=root, STATE_DIR=root / "data",
                                         SETTINGS_FILE=root / "data" / "settings.json"))
        release = threading.Event()

        def download(url, destination, *args):
            release.wait(5)
            file = destination / "Instagram" / "creator" / "Reel.mp4"
            file.parent.mkdir(parents=True)
            file.write_bytes(b"video")
            return DownloadResult(url, "yt-dlp", True, reveal_path=file)

        self.enterContext(patch("ui.gui_controller.download_single", side_effect=download))
        gui = GuiController()
        gui.save_dir("media")
        reel = "instagram.com/reel/example/"
        self.assertEqual(gui.snapshot(reel)["preview"]["dir"], "media/Instagram")
        item, = gui.enqueue(reel, video=True)["items"]
        _, worker = gui._active[item["id"]]
        try:
            self.assertFalse(item["canReveal"])
            with self.assertRaises(ValueError):
                gui.action(item["id"], "reveal")
            gui.save_dir("new-media")
            self.assertEqual(gui.snapshot("vm.tiktok.com/example")["preview"]["dir"], "new-media/TikTok")
        finally:
            release.set()
            worker.join(5)
        item, = gui.snapshot()["items"]
        self.assertEqual((item["st"], item["folder"], item["dir"]), ("done", "Instagram", "media/Instagram/creator"))
        self.assertTrue(item["canReveal"])
        with patch("ui.gui_controller.reveal_in_folder") as reveal:
            after, = gui.action(item["id"], "reveal")["items"]
            reveal.assert_called_once_with(root / "media" / "Instagram" / "creator" / "Reel.mp4")
            self.assertEqual(after, item)
