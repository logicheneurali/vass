#!/usr/bin/env python3
"""Bump VASS version: bump.py [major|minor|patch]"""

import os
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
VERSION_FILE = BASE / "VERSION"


def bump(current, part):
    major, minor, patch = map(int, current.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    elif part == "minor":
        return f"{major}.{minor + 1}.0"
    else:
        return f"{major}.{minor}.{patch + 1}"


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("major", "minor", "patch"):
        print("Usage: python bump.py [major|minor|patch]")
        sys.exit(1)

    part = sys.argv[1]
    current = VERSION_FILE.read_text().strip()
    new = bump(current, part)
    tag = f"v{new}"

    VERSION_FILE.write_text(new + "\n")
    print(f"Bump: {current} -> {new}")

    try:
        subprocess.run(["git", "add", str(VERSION_FILE)], check=True, cwd=str(BASE))
        subprocess.run(["git", "commit", "-m", f"Bump version {current} -> {new}"], check=True, cwd=str(BASE))
        subprocess.run(["git", "tag", tag], check=True, cwd=str(BASE))
        print(f"Tag created: {tag}")
        print("Push with: git push && git push --tags")
    except subprocess.CalledProcessError as e:
        print(f"Git error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
