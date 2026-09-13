"""Stage the analytics Lambda's zip payload.

Terraform calls this before `archive_file` zips the output directory. It exists
because the payload comes from three places -- this module's handler, the
analytics package in data-pipeline/, and Linux wheels for shapely/pyproj -- and
doing that in shell would need different commands on Windows and POSIX.

Wheels are fetched for the Lambda runtime's platform rather than the build
machine's, so this works from Windows without Docker.

    python build.py --out build
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
LAMBDA_DIR = MODULE_DIR / "lambda"
REPO_ROOT = MODULE_DIR.parents[2]
PIPELINE_DIR = REPO_ROOT / "data-pipeline"

# config/districts.json points at the map with a repo-relative path
# ("../../frontend/public/Map_NewTaipei.json"), so the package mirrors the repo
# layout instead of rewriting the config -- a deployed config that differs from
# the one in the repo is exactly the drift this project keeps getting bitten by.
BOUNDARY_FILE = Path("frontend/public/Map_NewTaipei.json")
PACKAGED_CONFIG_DIR = Path("data-pipeline/config")

# Must match the runtime in main.tf.
PYTHON_VERSION = "3.12"
PLATFORM = "manylinux2014_x86_64"

IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")


def build(out: Path) -> None:
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)

    subprocess.run(
        [
            sys.executable, "-m", "pip", "install", "--quiet", "--no-compile",
            "--platform", PLATFORM,
            "--only-binary=:all:",
            "--python-version", PYTHON_VERSION,
            "--implementation", "cp",
            "--target", str(out),
            "-r", str(LAMBDA_DIR / "requirements.txt"),
        ],
        check=True,
    )

    # Pure-Python packages published only as sdists (jieba has no wheel), which
    # `--only-binary` above cannot install. Being pure Python, a wheel built on
    # the build machine runs unchanged on the Lambda runtime.
    subprocess.run(
        [
            sys.executable, "-m", "pip", "install", "--quiet", "--no-compile", "--no-deps",
            "--target", str(out),
            "-r", str(LAMBDA_DIR / "requirements-sdist.txt"),
        ],
        check=True,
    )

    # handler.py and dynamodb_projection.py at the zip root, where the Lambda
    # runtime looks for the entrypoint.
    shutil.copytree(LAMBDA_DIR, out, dirs_exist_ok=True, ignore=IGNORE)

    # data-pipeline/src/ is flattened into the root so `import analytics...`
    # resolves off /var/task without needing PYTHONPATH, exactly as it resolves
    # off PYTHONPATH=src locally.
    shutil.copytree(PIPELINE_DIR / "src", out, dirs_exist_ok=True, ignore=IGNORE)

    # Kept at their repo-relative positions so districts.json's boundary_file
    # ("../../frontend/public/...") resolves inside the package unchanged.
    shutil.copytree(
        PIPELINE_DIR / "config", out / PACKAGED_CONFIG_DIR, dirs_exist_ok=True, ignore=IGNORE
    )
    boundary = out / BOUNDARY_FILE
    boundary.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / BOUNDARY_FILE, boundary)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="staging directory to (re)create")
    build(Path(parser.parse_args().out))


if __name__ == "__main__":
    main()
