"""
Builds the ZIP package for AWS Lambda.
Includes:
  api.py
  processing.py
  lambda_handler.py
  data/
  Lambda requirements
"""

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
BUILD = ROOT / "build"
ZIP_PATH = ROOT / "lambda_package.zip"

LAMBDA_PYTHON = "3.13"
CODE_FILES = ["api.py", "processing.py", "lambda_handler.py"]


def install_dependencies() -> None:
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "-r",
        str(ROOT / "requirements-lambda.txt"),
        "--target",
        str(BUILD),
        "--platform",
        "manylinux2014_x86_64",
        "--platform",
        "manylinux_2_28_x86_64",
        "--python-version",
        LAMBDA_PYTHON,
        "--implementation",
        "cp",
        "--only-binary=:all:",
        "--upgrade",
    ]

    subprocess.run(cmd, check=True)


def main(skip_install: bool = False) -> None:
    if BUILD.exists():
        shutil.rmtree(BUILD)

    BUILD.mkdir()

    if not skip_install:
        install_dependencies()

    # Copy the project files
    for name in CODE_FILES:
        shutil.copy(ROOT / name, BUILD / name)

    # Copy the data folder
    shutil.copytree(ROOT / "data", BUILD / "data")

    # Create the ZIP file
    with zipfile.ZipFile(
        ZIP_PATH,
        "w",
        zipfile.ZIP_DEFLATED,
    ) as zf:
        for path in sorted(BUILD.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                zf.write(
                    path,
                    path.relative_to(BUILD).as_posix(),
                )

    size_mb = ZIP_PATH.stat().st_size / 1_000_000
    print(f"Done: {ZIP_PATH.name} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main(skip_install="--skip-install" in sys.argv)
