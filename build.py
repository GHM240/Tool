import os
import sys
import shutil
import stat
import subprocess
import platform
from pathlib import Path

import imageio_ffmpeg


APP_NAME = "ArtifexDisplayConverter"
ENTRY_FILE = "Tool.py"


def copy_ffmpeg() -> Path:
    ffmpeg_src = Path(imageio_ffmpeg.get_ffmpeg_exe())
    assets_dir = Path("build_assets")
    assets_dir.mkdir(exist_ok=True)

    ffmpeg_name = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
    ffmpeg_target = assets_dir / ffmpeg_name

    shutil.copy2(ffmpeg_src, ffmpeg_target)

    if platform.system() != "Windows":
        current_mode = ffmpeg_target.stat().st_mode
        ffmpeg_target.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    print(f"[BUILD] system={platform.system()}")
    print(f"[BUILD] machine={platform.machine()}")
    print(f"[BUILD] python={sys.version}")
    print(f"[BUILD] executable={sys.executable}")
    print(f"[BUILD] FFmpeg source: {ffmpeg_src}")
    print(f"[BUILD] FFmpeg bundled as: {ffmpeg_target}")

    return ffmpeg_target


def main():
    ffmpeg_target = copy_ffmpeg()
    add_binary_sep = ";" if platform.system() == "Windows" else ":"

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
    ]

    # Windows 保留 tkinterdnd2 拖拽功能。
    # macOS arm64 禁用 tkinterdnd2，避免 tkdnd: "Unable to load tkdnd library."
    if platform.system() == "Windows":
        cmd.extend(["--collect-all", "tkinterdnd2"])
        print("[BUILD] Windows: collect tkinterdnd2 enabled")
    elif platform.system() == "Darwin":
        print("[BUILD] macOS: tkinterdnd2 collection skipped")
    else:
        print("[BUILD] Linux/other: tkinterdnd2 collection skipped")

    target_arch = os.environ.get("PYINSTALLER_TARGET_ARCH", "").strip()
    if platform.system() == "Darwin" and target_arch:
        cmd.extend(["--target-arch", target_arch])
        print(f"[BUILD] macOS target arch: {target_arch}")

    cmd.append(ENTRY_FILE)

    print("[BUILD] running:")
    print(" ".join(cmd))
    subprocess.check_call(cmd)
    print("[BUILD] done")


if __name__ == "__main__":
    main()
