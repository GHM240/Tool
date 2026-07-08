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


def chmod_executable(path: Path):
    if platform.system() != "Windows" and path.exists():
        current_mode = path.stat().st_mode
        path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def copy_ffmpeg_to_build_assets() -> Path:
    """把 imageio-ffmpeg 提供的 ffmpeg 复制到 build_assets，供 PyInstaller 使用。"""
    ffmpeg_src = Path(imageio_ffmpeg.get_ffmpeg_exe())
    if not ffmpeg_src.exists():
        raise FileNotFoundError(f"FFmpeg source not found: {ffmpeg_src}")

    assets_dir = Path("build_assets")
    assets_dir.mkdir(exist_ok=True)

    ffmpeg_name = "ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"
    ffmpeg_target = assets_dir / ffmpeg_name

    shutil.copy2(ffmpeg_src, ffmpeg_target)
    chmod_executable(ffmpeg_target)

    print(f"[BUILD] system={platform.system()}")
    print(f"[BUILD] machine={platform.machine()}")
    print(f"[BUILD] python={sys.version}")
    print(f"[BUILD] executable={sys.executable}")
    print(f"[BUILD] FFmpeg source: {ffmpeg_src}")
    print(f"[BUILD] FFmpeg copied to build_assets: {ffmpeg_target}")

    return ffmpeg_target


def build_output_path() -> Path:
    system = platform.system()
    if system == "Darwin":
        return Path("dist") / f"{APP_NAME}.app"
    # onedir 模式下 Windows / Linux 都是 dist/APP_NAME 文件夹。
    return Path("dist") / APP_NAME


def stable_ffmpeg_destination(output_path: Path) -> Path:
    """返回发布包里稳定的 ffmpeg 路径。Tool.py 会优先查这里。"""
    system = platform.system()
    if system == "Darwin":
        return output_path / "Contents" / "Resources" / "ffmpeg"
    if system == "Windows":
        return output_path / "ffmpeg.exe"
    return output_path / "ffmpeg"


def copy_ffmpeg_to_stable_location(ffmpeg_target: Path):
    output_path = build_output_path()
    if not output_path.exists():
        raise FileNotFoundError(f"PyInstaller output not found: {output_path}")

    dst = stable_ffmpeg_destination(output_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ffmpeg_target, dst)
    chmod_executable(dst)
    print(f"[BUILD] FFmpeg copied to stable runtime location: {dst}")

    # 直接测试发布包里的 ffmpeg 是否可执行。
    result = subprocess.run([str(dst), "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(
            f"Bundled FFmpeg cannot run: {dst}\n"
            f"stdout={result.stdout.decode(errors='ignore')}\n"
            f"stderr={result.stderr.decode(errors='ignore')}"
        )
    print("[BUILD] Bundled FFmpeg smoke test OK")


def run_pyinstaller(ffmpeg_target: Path):
    add_binary_sep = ";" if platform.system() == "Windows" else ":"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",       # 关键修复：不要使用 onefile，避免 macOS _MEI 临时路径问题。
        "--windowed",
        "--name",
        APP_NAME,
        "--add-binary",
        f"{ffmpeg_target}{add_binary_sep}.",
    ]

    # Windows 保留 tkinterdnd2 拖拽功能。
    # macOS 禁用 tkinterdnd2，避免 tkdnd 在 arm64 打包后闪退。
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


def main():
    ffmpeg_target = copy_ffmpeg_to_build_assets()
    run_pyinstaller(ffmpeg_target)
    copy_ffmpeg_to_stable_location(ffmpeg_target)
    print("[BUILD] done")


if __name__ == "__main__":
    main()
