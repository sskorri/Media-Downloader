import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import storage
from ui.gui import _fit_window_position


class WindowPositionTests(unittest.TestCase):
    def test_placement_survives_monitor_changes(self):
        left = (-1920, 0, 0, 1040)
        primary = (0, 0, 1920, 1040)
        areas = [left, primary]
        scaled_size = (1200, 800)
        self.assertEqual(_fit_window_position((-1500, 40), scaled_size, areas), (-1500, 40))
        self.assertEqual(_fit_window_position((-500, 40), scaled_size, areas), (-500, 40))
        self.assertEqual(_fit_window_position((-1500, 40), scaled_size, [primary]), (0, 40))
        self.assertEqual(_fit_window_position((1300, 900), scaled_size, [primary]), (720, 240))
        self.assertEqual(_fit_window_position((400, 80), scaled_size, [(0, 0, 1000, 700)]), (0, 0))

    def test_position_shares_existing_settings(self):
        folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        settings = folder / "settings.json"
        self.enterContext(patch.multiple(storage, STATE_DIR=folder, SETTINGS_FILE=settings))
        self.assertIsNone(storage.read_window_position())
        settings.write_text('{"theme":"dark","window_position":[false,2]}', encoding="utf-8")
        self.assertIsNone(storage.read_window_position())
        storage.set_window_position(-840, 100)
        self.assertEqual(storage.read_window_position(), (-840, 100))
        self.assertEqual(json.loads(settings.read_text(encoding="utf-8"))["theme"], "dark")
