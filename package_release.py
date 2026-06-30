#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Create a clean zip package from PyInstaller output.

macOS .app bundles should be packaged with ditto when available, because it
preserves app-bundle metadata, symlinks, executable bits, and resource forks
better than a generic Python zip walk. This avoids common "app cannot be opened"
issues after downloading/unzipping on macOS.
"""

from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

APP_NAME = "ArtifexDisplayConverter"


def make_executable_if_needed(path: Path) -> None:
    if path.exists() and path.is_file() and os.name != "nt":
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def add_path_to_zip(zf: zipfile.ZipFile, path: Path, arc_root: str | None = None) -> None:
    path = path.resolve()
    if path.is_file():
        make_executable_if_needed(path)
        arcname = Path(arc_root) / path.name if arc_root else Path(path.name)
        zf.write(path, arcname.as_posix())
        return

    base = path.parent
    for p in path.rglob("*"):
        # Store symlinks as their targets when using generic zip fallback.
        # On macOS .app, ditto path below is preferred and avoids this fallback.
        if p.is_file():
            make_executable_if_needed(p)
            zf.write(p, p.relative_to(base).as_posix())


def find_target(dist: Path) -> Path:
    candidates = [
        dist / f"{APP_NAME}.exe",
        dist / f"{APP_NAME}.app",
        dist / APP_NAME,
    ]
    target = next((p for p in candidates if p.exists()), None)
    if target is None:
        raise FileNotFoundError(f"No PyInstaller output found in {dist.resolve()}")
    return target


def zip_with_ditto(target: Path, zip_path: Path, readme: Path | None = None) -> bool:
    """Use macOS ditto for .app bundle packaging when available."""
    if platform.system() != "Darwin" or target.suffix != ".app":
        return False
    if shutil.which("ditto") is None:
        return False

    staging = Path("release_staging").resolve()
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    shutil.copytree(target, staging / target.name, symlinks=True)
    if readme and readme.exists():
        shutil.copy2(readme, staging / "README.md")

    # Ensure main executable bit exists before packaging.
    main_bin = staging / target.name / "Contents" / "MacOS" / APP_NAME
    make_executable_if_needed(main_bin)

    subprocess.check_call([
        "ditto",
        "-c",
        "-k",
        "--sequesterRsrc",
        "--keepParent",
        str(staging / target.name),
        str(zip_path),
    ], cwd=str(staging.parent))

    # The command above with --keepParent only includes the app. Add README via generic zip append.
    if readme and readme.exists():
        with zipfile.ZipFile(zip_path, "a", zipfile.ZIP_DEFLATED) as zf:
            zf.write(readme, "README.md")

    return True


def main() -> int:
    package_name = sys.argv[1] if len(sys.argv) > 1 else APP_NAME
    dist = Path("dist")
    release = Path("release")
    release.mkdir(exist_ok=True)

    target = find_target(dist)
    readme = Path("README.md")
    zip_path = release / f"{package_name}.zip"

    if target.is_file():
        make_executable_if_needed(target)

    if not zip_with_ditto(target, zip_path, readme if readme.exists() else None):
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            add_path_to_zip(zf, target)
            if readme.exists():
                zf.write(readme, "README.md")

    print(f"Created package: {zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
