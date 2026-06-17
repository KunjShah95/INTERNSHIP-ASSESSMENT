"""=== SetupAgent ==============================================================

ROLE:
  One-command project setup: create venv, install deps, seed demo cache data,
  guide the user through .env configuration, and start the app.

SYSTEM PROMPT (module identity):
  "I am the SetupAgent. I prepare the environment for first use. I check Python
   version, create a virtual environment, install requirements, offer to seed
   demo data, check for .env configuration, and start the Streamlit app."

USAGE:
  python setup.py            # interactive setup
  python setup.py --quick    # auto-setup with defaults
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _print_step(n: int, total: int, msg: str) -> None:
    print(f"\n[{n}/{total}] {msg}")


def _run(cmd: list[str], cwd: Path | None = None) -> bool:
    try:
        subprocess.run(cmd, cwd=cwd or ROOT, check=True)
        return True
    except subprocess.CalledProcessError:
        return False


def _check_python() -> bool:
    v = sys.version_info
    if v.major < 3 or (v.major == 3 and v.minor < 10):
        print(f"  ❌ Python 3.10+ required (found {v.major}.{v.minor})")
        return False
    print(f"  ✅ Python {v.major}.{v.minor}.{v.micro}")
    return True


def _check_venv() -> Path:
    venv_path = ROOT / ".venv"
    if venv_path.exists():
        print("  ✅ Virtual environment exists")
        return venv_path
    print("  🔧 Creating virtual environment...")
    _run([sys.executable, "-m", "venv", str(venv_path)])
    print("  ✅ Virtual environment created")
    return venv_path


def _pip(args: list[str]) -> bool:
    pip = str(ROOT / ".venv" / "Scripts" / "pip")
    return _run([pip] + args)


def _install() -> bool:
    print("  🔧 Installing dependencies...")
    ok = _pip(["install", "-r", "requirements.txt"])
    if ok:
        print("  ✅ Dependencies installed")
    else:
        print("  ❌ Failed to install dependencies")
    return ok


def _seed_demo() -> None:
    cache_dir = ROOT / "cache"
    demo_dir = ROOT / ".demo_cache"
    if not demo_dir.exists():
        print("  ⏭️  No demo data found (.demo_cache/ missing)")
        return
    cache_dir.mkdir(exist_ok=True)
    for f in demo_dir.glob("*.json"):
        shutil.copy2(f, cache_dir / f.name)
    count = len(list(demo_dir.glob("*.json")))
    print(f"  ✅ {count} demo reports seeded")


def _check_env() -> bool:
    env_example = ROOT / ".env.example"
    env_file = ROOT / ".env"
    if env_file.exists():
        with open(env_file) as f:
            content = f.read()
        keys_found = [line.split("=")[0] for line in content.splitlines()
                      if "=" in line and line.split("=")[1].strip()]
        if keys_found:
            print(f"  ✅ .env found ({len(keys_found)} values set)")
            return True

    print(f"  ⚠️  No .env configured. Copying from .env.example...")
    if env_example.exists():
        shutil.copy2(env_example, env_file)
        print("  ✅ .env created from .env.example")
        print("  ➡️  Open .env and add at least one API key (GROQ_API_KEY is free)")
    return False


def _start_app() -> None:
    print("\n" + "=" * 50)
    print("🚀 Starting AI Research & Recommendation Agent")
    print("=" * 50)
    print("\nOpen http://localhost:8501 in your browser.")
    print("Press Ctrl+C to stop.\n")

    streamlit = str(ROOT / ".venv" / "Scripts" / "streamlit")
    os.chdir(ROOT)
    _run([streamlit, "run", "app.py"])


def main() -> None:
    total = 6
    print("=" * 50)
    print("🔎 AI Research & Recommendation Agent — Setup")
    print("=" * 50)

    _print_step(1, total, "Checking Python version")
    if not _check_python():
        sys.exit(1)

    _print_step(2, total, "Setting up virtual environment")
    _check_venv()

    _print_step(3, total, "Installing dependencies")
    if not _install():
        sys.exit(1)

    _print_step(4, total, "Checking configuration")
    _check_env()

    _print_step(5, total, "Seeding demo data")
    _seed_demo()

    _print_step(6, total, "Starting application")
    _start_app()


if __name__ == "__main__":
    main()
