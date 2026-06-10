#!/usr/bin/env python3
"""End-to-end smoke test: process ONE video from the command line, no UI needed.

Usage:
    cd backend
    python scripts/run_one.py                       # hardcoded test URL
    python scripts/run_one.py <youtube-url>         # your own URL
    python scripts/run_one.py <url> --range 5 12    # only minutes 5-12

Run this first to confirm ffmpeg / whisper / the Anthropic key all work
before touching the UI.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pipeline.runner import process_video  # noqa: E402

# A short, public, dialogue-heavy video for testing (first YouTube video ever, 19s).
# Swap for any podcast/interview URL for a realistic run.
DEFAULT_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?", default=DEFAULT_URL)
    parser.add_argument("--range", nargs=2, type=float, metavar=("START_MIN", "END_MIN"),
                        help="only process minutes START..END")
    args = parser.parse_args()

    def progress(stage: str, frac: float, msg: str) -> None:
        print(f"[{stage:>10}] {frac * 100:5.1f}%  {msg}")

    time_range = (args.range[0] * 60, args.range[1] * 60) if args.range else None
    try:
        result = process_video(args.url, time_range=time_range, progress=progress)
    except Exception as e:
        user_msg = getattr(e, "user_message", None)
        print(f"\nFAILED: {user_msg or e}", file=sys.stderr)
        detail = getattr(e, "detail", None)
        if detail:
            print(f"detail: {detail}", file=sys.stderr)
        return 1

    print(f"\nDone. video={result['video_id']} clips={result['clip_ids']}")
    print("Rendered files are in backend/data/clips/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
