import os
import shutil
import zipfile
import platform
import subprocess
from pathlib import Path


APP_NAME = "ArtifexDisplayConverter"


def zip_path(src: Path, dst_zip: Path):
    with zipfile.ZipFile(dst_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if src.is_dir():
            for p in src.rglob("*"):
                arcname = p.relative_to(src.parent)
                info = zipfile.ZipInfo(str(arcname))
                if p.is_dir():
                    info.external_attr = 0o755 << 16
                    zf.writestr(info, "")
                else:
                    info.external_attr = p.stat().st_mode << 16
                    with open(p, "rb") as f:
                        zf.writestr(info, f.read())
        else:
            info = zipfile.ZipInfo(src.name)
            info.external_attr = src.stat().st_mode << 16
            with open(src, "rb") as f:
                zf.writestr(info, f.read())


def main():
    system = platform.system()
    package_name = os.environ.get("PACKAGE_NAME")

    if not package_name:
        if system == "Windows":
            package_name = f"{APP_NAME}-Windows"
        elif system == "Darwin":
            package_name = f"{APP_NAME}-macOS-arm64"
        else:
            package_name = f"{APP_NAME}-{system}"

    dist_dir = Path("dist")
    release_dir = Path("release")
    release_dir.mkdir(exist_ok=True)

    if system == "Windows":
        src = dist_dir / f"{APP_NAME}.exe"
    elif system == "Darwin":
        src = dist_dir / f"{APP_NAME}.app"
    else:
        src = dist_dir / APP_NAME

    if not src.exists():
        raise FileNotFoundError(f"Build output not found: {src}")

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
