"""Windows desktop host for the supplied Media Downloader HTML design."""

import argparse
import os
import sys
from pathlib import Path

if __name__ == "__main__" and not __package__:
    # Direct script launches also need the shared src package beside ui.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.runtime import use_project_python

if __name__ == "__main__":
    use_project_python(__file__)

from src import storage
from ui.gui_view import render_page


class WindowControls:
    def __init__(self):
        self._window = None

    def minimize(self):
        self._window.minimize()

    def close_window(self):
        self._window.destroy()


class DownloadApi(WindowControls):
    def __init__(self, controller):
        super().__init__()
        self._controller = controller

    def snapshot(self, input_url=""):
        return self._controller.snapshot(input_url)

    def enqueue(self, urls, video):
        return self._controller.enqueue(urls, video)

    def import_batch(self, video):
        from webview import FileDialog

        selected = self._window.create_file_dialog(
            FileDialog.OPEN, file_types=("Text files (*.txt)", "All files (*.*)")
        )
        if selected:
            return self.enqueue(storage.read_urls(Path(selected[0])), video)
        return self.snapshot()

    def action(self, id, action):
        return self._controller.action(id, action)

    def clear_finished(self):
        return self._controller.clear_finished()

    def save_dir(self, value):
        return self._controller.save_dir(value)

    def set_pref(self, key, value):
        return self._controller.set_pref(key, value)


def create_window(webview, page, api):
    window = webview.create_window(
        "Media Downloader", html=page, js_api=api, width=960, height=640, min_size=(960, 640),
        frameless=True, easy_drag=False, resizable=False, text_select=True,
        background_color="#FFF9FA",
    )
    api._window = window

    # This local document has a native bridge. Keep pasted or dropped links
    # from navigating the WebView away from the application's own HTML.
    def configure_browser():
        initial_page = True

        def local_document_only(sender, args):
            nonlocal initial_page
            uri = str(args.Uri)
            if uri == "about:blank":
                return
            # WebView2 reports NavigateToString as a data URL on some releases.
            if initial_page and not args.IsUserInitiated and uri.startswith("data:text/html"):
                initial_page = False
                return
            args.Cancel = True

        browser = window.native.webview
        browser.AllowExternalDrop = False
        browser.NavigationStarting += local_document_only

        def enable_title_bar(sender, event):
            if event.IsSuccess:
                sender.CoreWebView2.Settings.IsNonClientRegionSupportEnabled = True

        browser.CoreWebView2InitializationCompleted += enable_title_bar

    window.events.before_show += configure_browser
    return window


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", action="store_true", help="Show the interface with its simulated queue")
    args = parser.parse_args(argv)

    if os.name != "nt":
        raise RuntimeError("The desktop build uses Microsoft Edge WebView2 on Windows.")
    try:
        import webview
        from webview.guilib import initialize
    except ImportError as exc:
        raise RuntimeError("Install the desktop dependencies in the project's .venv as described in README.md.") from exc
    if initialize("edgechromium").renderer != "edgechromium":
        raise RuntimeError("Install the Microsoft Edge WebView2 Runtime to open Media Downloader.")

    page = render_page(storage.PROJECT_DIR, preview=args.preview)
    controller = None
    api = WindowControls()
    if not args.preview:
        from ui.gui_controller import GuiController

        controller = GuiController()
        api = DownloadApi(controller)
    try:
        create_window(webview, page, api)
        webview.settings["ALLOW_FILE_URLS"] = False
        webview.start(gui="edgechromium", storage_path=str(storage.STATE_DIR / "webview"), private_mode=False)
    finally:
        if controller is not None:
            controller.shutdown()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        if sys.stderr is not None:
            raise
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, str(exc), "Media Downloader", 0x10)
        raise SystemExit(1)
