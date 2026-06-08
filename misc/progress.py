#!/usr/bin/env python3
"""
misc/progress.py — Thread-safe CLI spinner / progress indicator.

Replaces misc/spinner.sh. Uses threading so it can run alongside other work.

Usage (as a module):
  from misc.progress import Spinner
  with Spinner("Installing packages..."):
      time.sleep(5)

Usage (standalone):
  python3 misc/progress.py "Working..." --duration 5
"""

import argparse
import sys
import threading
import time


class Spinner:
    """Context-manager spinner. Shows a braille-dot animation with a message."""

    _FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    _DELAY = 0.12

    def __init__(self, message: str = "Working…") -> None:
        self.message = message
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def _spin(self) -> None:
        frames = self._FRAMES
        idx = 0
        while not self._stop_event.is_set():
            frame = frames[idx % len(frames)]
            sys.stdout.write(f"\r  {frame}  {self.message} ")
            sys.stdout.flush()
            idx += 1
            time.sleep(self._DELAY)

    def start(self) -> "Spinner":
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop_event.set()
        self._thread.join(timeout=1.0)
        sys.stdout.write("\r" + " " * (len(self.message) + 10) + "\r")
        sys.stdout.flush()

    def __enter__(self) -> "Spinner":
        return self.start()

    def __exit__(self, *_) -> None:
        self.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="CLI spinner")
    parser.add_argument("message", nargs="?", default="Working…",
                        help="Message to display")
    parser.add_argument("--duration", type=float, default=0,
                        help="Run for N seconds then exit (0 = run until Ctrl+C)")
    args = parser.parse_args()

    spinner = Spinner(args.message)
    spinner.start()
    try:
        if args.duration > 0:
            time.sleep(args.duration)
        else:
            while True:
                time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        spinner.stop()


if __name__ == "__main__":
    main()
