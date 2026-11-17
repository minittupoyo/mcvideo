"""Locating and calling ffmpeg / ffprobe."""
import os
import shutil
import subprocess


class ToolError(RuntimeError):
    """A required external tool is missing or failed."""


def find_tool(name):
    """Return the path of an executable (``ffmpeg`` / ``ffprobe``).

    Order: the environment variable (``FFMPEG`` / ``FFPROBE``), then ``PATH``, then ``C:\\ffmpeg`` on Windows.
    """
    env = os.environ.get(name.upper())
    if env and os.path.exists(env):
        return env
    path = shutil.which(name)
    if path:
        return path
    for folder in (r"C:\ffmpeg", r"C:\ffmpeg\bin"):
        candidate = os.path.join(folder, name + ".exe")
        if os.path.exists(candidate):
            return candidate
    raise ToolError(f"{name} not found: install ffmpeg and put it on PATH (or set the {name.upper()} variable)")


def probe_video(ffprobe, path):
    """Return ``(width, height, has_audio)`` of the first video stream of ``path``."""
    video = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0",
         path], capture_output=True, text=True, check=True).stdout.strip()
    if not video:
        raise ToolError(f"no video stream in {path}")
    width, height = map(int, video.split(",")[:2])
    audio = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True).stdout.strip()
    return width, height, bool(audio)
