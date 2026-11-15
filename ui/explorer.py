"""Reveal a finished download in Windows File Explorer."""

import ctypes
import os
from pathlib import Path


def reveal_in_folder(path: Path) -> None:
    path = path.absolute()
    if path.is_dir():
        os.startfile(path, "explore")
        return
    if not path.is_file():
        raise FileNotFoundError(f"The download was moved or deleted: {path}")

    # pywebview dispatches button clicks on worker threads. The Shell API
    # requires COM and also accepts a thread already in another apartment.
    ole = ctypes.oledll.ole32
    initialized = False
    try:
        ole.CoInitialize(None)
        initialized = True
    except OSError as error:
        if error.winerror != -2147417850:  # RPC_E_CHANGED_MODE
            raise

    item = ctypes.c_void_p()
    try:
        shell = ctypes.oledll.shell32
        shell.SHParseDisplayName(str(path), None, ctypes.byref(item), 0, None)
        # With zero children, Explorer opens the parent and selects this item.
        shell.SHOpenFolderAndSelectItems(item, 0, None, 0)
    finally:
        if item:
            ctypes.windll.ole32.CoTaskMemFree(item)
        if initialized:
            ctypes.windll.ole32.CoUninitialize()
