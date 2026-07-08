import os
import sys
import shutil
import zipfile
import platform
import subprocess
from pathlib import Path


APP_NAME = "ArtifexDisplayConverter"


def zip_path(src: Path, dst_zip: Path):
    """跨平台 zip。保留可执行权限，避免 macOS / Linux 下 ffmpeg 失去 +x。"""
    with zipfile.ZipFile(dst_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if src.is_dir():
            for p in src.rglob("*"):
                arcname = p.relative_to(src.parent)
                if p.is_dir():
                    info = zipfile.ZipInfo(str(arcname) + "/")
                    info.external_attr = 0o755 << 16
                    zf.writestr(info, "")
                else:
                    info = zipfile.ZipInfo(str(arcname))
                    info.external_attr = p.stat().st_mode << 16
                    with open(p, "rb") as f:
                        zf.writestr(info, f.read())
        else:
            info = zipfile.ZipInfo(src.name)
            info.external_attr = src.stat().st_mode << 16
            with open(src, "rb") as f:
                zf.writestr(info, f.read())


def default_package_name(system: str) -> str:
    if system == "Windows":
        return f"{APP_NAME}-Windows"
    if system == "Darwin":
        machine = platform.machine().lower()
        arch = "arm64" if "arm" in machine or "aarch64" in machine else "x64"
        return f"{APP_NAME}-macOS-{arch}"
    return f"{APP_NAME}-{system}-{platform.machine()}"


def build_output_path(system: str) -> Path:
    dist_dir = Path("dist")
    if system == "Darwin":
        return dist_dir / f"{APP_NAME}.app"
    # build.py 使用 onedir，Windows / Linux 都打包整个文件夹。
    return dist_dir / APP_NAME


def main():
    system = platform.system()

    # 优先级：命令行参数 > PACKAGE_NAME 环境变量 > 自动名称。
    package_name = None
    if len(sys.argv) >= 2 and sys.argv[1].strip():
        package_name = sys.argv[1].strip()
    package_name = package_name or os.environ.get("PACKAGE_NAME") or default_package_name(system)

    src = build_output_path(system)
    if not src.exists():
        raise FileNotFoundError(f"Build output not found: {src}")

    release_dir = Path("release")
    release_dir.mkdir(exist_ok=True)
    dst_zip = release_dir / f"{package_name}.zip"
    if dst_zip.exists():
        dst_zip.unlink()

    if system == "Darwin" and src.suffix == ".app" and shutil.which("ditto"):
        print(f"[PACKAGE] Using ditto for macOS app: {src}")
        subprocess.check_call([
            "ditto",
            "-c",
            "-k",
            "--sequesterRsrc",
            "--keepParent",
            src.name,
            str(dst_zip.resolve()),
        ], cwd=src.parent)
    else:
        print(f"[PACKAGE] Using zipfile: {src}")
        zip_path(src, dst_zip)

    print(f"[PACKAGE] Created: {dst_zip}")
    print(f"[PACKAGE] Size: {dst_zip.stat().st_size} bytes")


if __name__ == "__main__":
    main()
