"""Create an isolated Python 3.12 environment, install dependencies, and reproduce.

Usage: python bootstrap.py --workers 4
"""
from pathlib import Path
import argparse
import os
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-dir", type=Path, default=ROOT / ".venv")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--install-only", action="store_true")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        parser.error("Python 3.12 is required by the validated environment; on Windows, try py -3.12 bootstrap.py")
    env_dir = args.env_dir.resolve()
    python = env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not (env_dir / "pyvenv.cfg").exists():
        if env_dir.exists() and any(env_dir.iterdir()):
            parser.error("The requested environment directory is nonempty and is not a virtual environment.")
        print("Creating an isolated Python 3.12 environment.", flush=True)
        venv.EnvBuilder(with_pip=True).create(env_dir)
    if not python.is_file():
        parser.error("The virtual environment has no Python executable; select a new environment directory.")
    env = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME"):
        env.pop(key, None)
    env.update(PYTHONUTF8="1", PYTHONNOUSERSITE="1", PIP_DISABLE_PIP_VERSION_CHECK="1", MPLBACKEND="Agg")
    commands = [
        ["-m", "pip", "install", "--no-compile", "-r", str(ROOT / "requirements-lock.txt")],
        ["-m", "pip", "check"],
        [str(ROOT / "scripts/check_environment.py")],
    ]
    if not args.install_only:
        commands.append([str(ROOT / "run_all.py"), "--workers", str(args.workers)])
    for command in commands:
        result = subprocess.run([str(python), *command], cwd=ROOT, env=env)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
