"""
build.py — Local release build script for Twitch Boxing Ring.

Runs PyInstaller using TwitchBoxingRing.spec, then assembles a release zip
containing the executable plus all user-editable files alongside it.

Usage:
    python3 build.py

Output:
    dist/TwitchBoxingRing-windows.zip   (when run on Windows)
    dist/TwitchBoxingRing-mac.zip       (when run on macOS/Linux)

Requirements:
    pip install pyinstaller
"""

import os
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


# ── Config ────────────────────────────────────────────────────────────────────

SPEC_FILE   = "TwitchBoxingRing.spec"
DIST_DIR    = Path("dist")
BUILD_DIR   = Path("build")
EXE_NAME    = "TwitchBoxingRing"

# Files placed next to the executable in the zip so users can edit them.
# Paths are relative to the repo root.
ALONGSIDE_FILES = [
    "config.py",
    "configs/typechart.json",
    "configs/movepool.json",
    "web/overlay.html",
    "web/overlay.css",
    "web/overlay.js",
    "README.md",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def banner(msg: str):
    print(f"\n{'─' * 60}")
    print(f"  {msg}")
    print(f"{'─' * 60}")


def run(cmd: list[str]):
    print(f"[Build] Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        sys.exit(f"[Build] Command failed with exit code {result.returncode}")


def platform_name() -> str:
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    elif system == "darwin":
        return "mac"
    else:
        return "linux"


def exe_path() -> Path:
    """Path to the built executable inside dist/."""
    system = platform.system().lower()
    if system == "windows":
        return DIST_DIR / f"{EXE_NAME}.exe"
    else:
        return DIST_DIR / EXE_NAME


# ── Build steps ───────────────────────────────────────────────────────────────

def clean():
    banner("Cleaning previous build artifacts")
    for d in (BUILD_DIR, DIST_DIR):
        if d.exists():
            shutil.rmtree(d)
            print(f"[Build] Removed {d}/")


def build_executable():
    banner("Running PyInstaller")
    run([sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", SPEC_FILE])
    exe = exe_path()
    if not exe.exists():
        sys.exit(f"[Build] Expected executable not found at {exe}")
    size_mb = exe.stat().st_size / 1_048_576
    print(f"[Build] Executable built: {exe}  ({size_mb:.1f} MB)")


def assemble_zip():
    banner("Assembling release zip")
    plat     = platform_name()
    zip_name = f"TwitchBoxingRing-{plat}.zip"
    zip_path = DIST_DIR / zip_name

    # The folder name inside the zip — what users see when they extract
    folder = f"TwitchBoxingRing-{plat}"

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:

        # 1. The executable itself
        exe = exe_path()
        zf.write(exe, arcname=f"{folder}/{exe.name}")
        print(f"[Build]   + {exe.name}")

        # 2. User-editable files alongside the executable
        for rel_path in ALONGSIDE_FILES:
            src = Path(rel_path)
            if not src.exists():
                print(f"[Build]   WARNING: {rel_path} not found, skipping")
                continue
            # Flatten all files into the root of the folder (no subdirectories),
            # so users open the zip and see everything in one place.
            zf.write(src, arcname=f"{folder}/{src.name}")
            print(f"[Build]   + {src.name}")

        # 3. A blank configs placeholder so the configs folder exists
        #    (twitch_token.json is gitignored and should NOT be bundled)
        zf.writestr(f"{folder}/configs/", "")

    size_mb = zip_path.stat().st_size / 1_048_576
    print(f"\n[Build] Release zip: {zip_path}  ({size_mb:.1f} MB)")
    return zip_path


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    banner(f"Twitch Boxing Ring — Release Build ({platform_name()})")

    # Verify PyInstaller is available before doing anything else
    try:
        subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            check=True, capture_output=True
        )
    except subprocess.CalledProcessError:
        sys.exit(
            "[Build] PyInstaller not found.\n"
            "Install it with:  pip install pyinstaller"
        )

    clean()
    build_executable()
    zip_path = assemble_zip()

    banner("Build complete")
    print(f"  Release zip: {zip_path.resolve()}")
    print(f"\n  To release:")
    print(f"    1. Push a version tag:  git tag v1.0.0 && git push origin v1.0.0")
    print(f"    2. GitHub Actions will build both platforms automatically.")
    print(f"    3. The zips will appear as assets on the GitHub Release page.")


if __name__ == "__main__":
    main()