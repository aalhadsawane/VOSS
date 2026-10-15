"""SeBS 220.video-processing: transcode the first seconds of a video to a GIF with ffmpeg."""

from __future__ import annotations

import subprocess


def make_input(size_kb: int) -> str:
    path = f"/tmp/voss-video-{size_kb}.mp4"
    seconds = max(1, size_kb // 500)  # ~4 Mbit/s test pattern
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=duration={seconds}:size=1280x720:rate=30",
    ]
    subprocess.run([*cmd, "-b:v", "4M", path], check=True)
    return path


def handler(path: str) -> int:
    out = "/tmp/voss-video.gif"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-t", "3", "-vf", "fps=10,scale=320:-1", out]
    return subprocess.run(cmd, check=True).returncode
