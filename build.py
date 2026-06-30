#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build helper for GitHub Actions and local PyInstaller packaging.

It downloads/locates the platform-matching FFmpeg executable from imageio-ffmpeg,
renames it to ffmpeg/ffmpeg.exe, and bundles it into the PyInstaller app.
This matches Tool.py's runtime search logic, so end users do not need to
install FFmpeg separately.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

APP_NAME = "ArtifexDisplayConverter"
ENTRY_FILE = "Tool.py"


def prepare_ffmpeg_binary() -> Path:
    source = Path(imageio_ffmpeg.get_ffmpeg_exe()).resolve()
    if not source.exists():
        raise FileNotFoundError(f"imageio-ffmpeg returned a missing file: {source}")

    out_dir = Path("build_assets").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    exe_name = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
    target = out_dir / exe_name
    shutil.copy2(source, target)

    if platform.system() != "Windows":
        target.chmod(target.stat().st_mode | 0o111)

    print(f"Bundled FFmpeg: {target}")
    return target


def main() -> int:
    ffmpeg_target = prepare_ffmpeg_binary()
    add_binary_sep = os.pathsep  # ';' on Windows, ':' on macOS/Linux

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        APP_NAME,
        "--add-binary",
        f"{ffmpeg_target}{add_binary_sep}.",
        "--collect-all",
        "tkinterdnd2",
        ENTRY_FILE,
    ]

    print("Running:")
    print(" ".join(str(x) for x in cmd))
    subprocess.check_call(cmd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
