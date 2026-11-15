#!/usr/bin/env python3
"""Download media from the command line, a batch file, or a synced queue."""

import argparse
from pathlib import Path

from src.runtime import use_project_python


if __name__ == "__main__":
    use_project_python(__file__)

try:
    from rich.console import Console
except ModuleNotFoundError as error:
    if error.name != "rich":
        raise
    raise SystemExit("Install requirements.txt into the project .venv using the command in README.md.") from error

from src import storage
from src.downloads import process_urls

console = Console(markup=False, highlight=False)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Download media with yt-dlp or spotDL.")
    parser.add_argument("urls", nargs="*", help="One or more URLs to download")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("-b", "--batch", type=Path, help="Read URLs from a text file")
    modes.add_argument("--cron", action="store_true", help="Process the synced queue once")
    modes.add_argument("--history", action="store_true", help="Show the last 20 download attempts")
    modes.add_argument("--settings", action="store_true", help="Show the active paths")
    modes.add_argument("--set-download-dir", metavar="DIR", help="Save the destination for future downloads")
    parser.add_argument("-v", "--video", action="store_true", help="Keep video on yt-dlp downloads")
    parser.add_argument("--threads", type=int, default=4, help="Concurrent tracks per Spotify playlist")
    parser.add_argument("--parallel", type=int, default=1, help="Concurrent input URLs")
    parser.add_argument("--queue-file", type=Path, help="Queue file to use with --cron")
    args = parser.parse_intermixed_args(argv)
    if args.urls and (args.batch or args.cron or args.history or args.settings or args.set_download_dir is not None):
        parser.error("use direct URLs on their own or choose one of the file, history, or settings modes")
    if args.parallel < 1 or args.threads < 1:
        parser.error("--parallel and --threads must be positive")
    return args


def download(urls, *, video_mode=False, threads=4, parallel=1):
    destination = storage.read_download_dir()
    storage.initialize_state()
    results = process_urls(urls, destination, storage.STATE_DIR, video_mode, threads, parallel)
    exit_code = 0
    for result in results:
        status = "success" if result.success else "failed"
        if result.success:
            console.print(f"OK   {result.url}", style="green")
        else:
            console.print(f"FAIL {result.url} - {result.error[:160]}", style="red")
            exit_code = 1
        storage.log_download(result.url, status, result.tool, result.error)
    return exit_code


def main(argv=None):
    args = parse_args(argv)
    try:
        if args.set_download_dir is not None:
            console.print(f"Download directory: {storage.set_download_dir(args.set_download_dir)}")
        elif args.settings:
            console.print(f"Download directory: {storage.read_download_dir()}")
            console.print(f"Settings file: {storage.SETTINGS_FILE}")
            console.print(f"Queue file: {storage.default_queue_path()}")
        elif args.history:
            entries = list(storage.recent_history())
            if not entries:
                console.print("No history yet.")
            for entry in entries:
                label = "OK  " if entry["status"] == "success" else "FAIL"
                console.print(f"{label} {entry['timestamp'][:19]} {entry['tool']:>8} {entry['url']}")
        elif args.cron:
            queue = args.queue_file or storage.default_queue_path()
            with storage.claimed_queue(queue) as urls:
                if urls is None:
                    console.print(f"Queue file {queue} not found. Nothing to do.")
                elif urls:
                    console.print(f"Processing {len(urls)} links from queue...")
                    return download(urls)
                else:
                    console.print("Queue file contained no valid links.")
        else:
            urls = storage.read_urls(args.batch) if args.batch else args.urls
            if urls:
                return download(urls, video_mode=args.video, threads=args.threads, parallel=args.parallel)
            console.print("No URLs given. Use -h for help.")
    except (OSError, ValueError) as error:
        console.print(f"Error: {error}", style="red")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
