"""Build script to package TIDAL-Downloader-NG GUI as an executable.

This script supports compilation using PyInstaller or Nuitka, handles
resource bundling, platform-specific settings, and virtual environment path
resolution.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def get_venv_bin_dir() -> Path:
    """Locate the virtual environment binary directory.

    Returns:
        Path: Path to the binary directory (Scripts on Windows, bin on Unix).

    Raises:
        FileNotFoundError: If the virtual environment directory is not found.
    """
    project_root = Path(__file__).parent.resolve()
    venv_dir = project_root / ".venv"

    if not venv_dir.is_dir():
        msg = "Virtual environment (.venv) not found in the project root."
        raise FileNotFoundError(msg)

    if sys.platform == "win32":
        return venv_dir / "Scripts"
    return venv_dir / "bin"


def run_command(args: list[str]) -> None:
    """Run a system command using the current process environments.

    Args:
        args (list[str]): The command and its arguments.

    Raises:
        subprocess.CalledProcessError: If the command returns a non-zero exit
            status.
    """
    sys.stdout.write(f"Running: {' '.join(args)}\n")
    sys.stdout.flush()
    subprocess.run(args, check=True)  # noqa: S603


def build_with_pyinstaller(onefile: bool, console: bool) -> None:
    """Build the executable using PyInstaller.

    Args:
        onefile (bool): Whether to build as a single executable file.
        console (bool): Whether to keep the console window visible.
    """
    bin_dir = get_venv_bin_dir()
    python_name = "python.exe" if sys.platform == "win32" else "python"
    python_exe = bin_dir / python_name

    # Install PyInstaller if not present
    try:
        subprocess.run(  # noqa: S603
            [str(python_exe), "-c", "import PyInstaller"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        sys.stdout.write(
            "PyInstaller not found. Installing it inside .venv...\n"
        )
        sys.stdout.flush()
        run_command([str(python_exe), "-m", "pip", "install", "pyinstaller"])

    entry_point = Path("tidal_dl_ng/gui/activate.py")
    icon_path = Path("tidal_dl_ng/ui/icon.ico")

    cmd = [
        str(python_exe),
        "-m",
        "PyInstaller",
        "--name=TIDAL-Downloader-NG",
        "--clean",
        "--noconfirm",
        "--collect-submodules=tidal_dl_ng",
        "--hidden-import=qdarktheme",
    ]

    if not console:
        cmd.append("--noconsole")

    if onefile:
        cmd.append("--onefile")

    if icon_path.is_file():
        cmd.append(f"--icon={icon_path}")

    # Add the ui assets directory
    separator = ";" if sys.platform == "win32" else ":"
    cmd.append(f"--add-data=tidal_dl_ng/ui{separator}tidal_dl_ng/ui")

    cmd.append(str(entry_point))

    run_command(cmd)
    sys.stdout.write(
        "\nBuild successful! Executable can be found in the 'dist' folder.\n"
    )
    sys.stdout.flush()


def build_with_nuitka(console: bool) -> None:
    """Build the executable using Nuitka.

    Args:
        console (bool): Whether to keep the console window visible.
    """
    bin_dir = get_venv_bin_dir()
    python_name = "python.exe" if sys.platform == "win32" else "python"
    python_exe = bin_dir / python_name

    # Check if Nuitka is installed
    try:
        subprocess.run(  # noqa: S603
            [str(python_exe), "-c", "import nuitka"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        sys.stdout.write("Nuitka not found. Installing it inside .venv...\n")
        sys.stdout.flush()
        run_command([str(python_exe), "-m", "pip", "install", "nuitka"])

    entry_point = Path("tidal_dl_ng/gui/activate.py")
    icon_path = Path("tidal_dl_ng/ui/icon.ico")

    cmd = [
        str(python_exe),
        "-m",
        "nuitka",
        "--standalone",
        "--enable-plugin=pyside6",
        "--output-dir=dist",
        "--include-package=tidal_dl_ng",
        "--include-package=qdarktheme",
    ]

    if sys.platform == "win32":
        if not console:
            cmd.append("--windows-console-mode=disable")
        if icon_path.is_file():
            cmd.append(f"--windows-icon-from-ico={icon_path}")
    elif sys.platform == "darwin":
        cmd.append("--macos-create-app-bundle")

    cmd.append("--include-data-dir=tidal_dl_ng/ui=tidal_dl_ng/ui")
    cmd.append(str(entry_point))

    run_command(cmd)
    sys.stdout.write(
        "\nBuild successful! Executable can be found in "
        "'dist/activate.dist'.\n"
    )
    sys.stdout.flush()


def main() -> None:
    """Main entry point for build script."""
    parser = argparse.ArgumentParser(
        description=(
            "Build TIDAL-Downloader-NG GUI into a standalone executable."
        )
    )
    parser.add_argument(
        "--tool",
        choices=["pyinstaller", "nuitka"],
        default="pyinstaller",
        help="The packaging tool to use (default: pyinstaller).",
    )
    parser.add_argument(
        "--onefile",
        action="store_true",
        help="Build as a single executable file (PyInstaller only).",
    )
    parser.add_argument(
        "--console",
        action="store_true",
        help="Keep the console window visible for logging/debugging.",
    )

    args = parser.parse_args()

    try:
        if args.tool == "pyinstaller":
            build_with_pyinstaller(onefile=args.onefile, console=args.console)
        elif args.tool == "nuitka":
            build_with_nuitka(console=args.console)
    except (subprocess.SubprocessError, OSError) as e:
        sys.stderr.write(f"Error during build: {e}\n")
        sys.stderr.flush()
        sys.exit(1)


if __name__ == "__main__":
    main()
