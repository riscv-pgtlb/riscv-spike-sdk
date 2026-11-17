#!/usr/bin/env python3
"""Validate fixed Debian targets and publish a fully provisioned disk pair."""
import argparse
import importlib.util
from pathlib import Path
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
NAMES = ("debian-host.raw", "debian-guest.raw")


def validate(base, recreate):
    targets = [base / name for name in NAMES]
    existing = []
    for target in targets:
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise RuntimeError(f"Target must be a regular disk file: {target}")
        if target.exists():
            existing.append(target)
    if existing and not recreate:
        raise RuntimeError("Debian disks already exist. Use make debian-update to update tools, "
                           "or make debian-prepare DEBIAN_RECREATE=1 to back up and recreate them.")
    if len(existing) == 2 and existing[0].samefile(existing[1]):
        raise RuntimeError("Host and guest targets must be separate files")
    return existing


def check(base, recreate):
    existing = validate(base, recreate)
    if existing:
        spec = importlib.util.spec_from_file_location("disk_target_update", ROOT / "scripts/debian/common/maintenance.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.check_stopped(*existing)


def publish(base, staged, recreate):
    if base.resolve() == staged.resolve():
        raise RuntimeError("Staged disks must be in a separate directory")
    existing = validate(base, recreate)
    for name in NAMES:
        disk = staged / name
        if disk.is_symlink() or not disk.is_file():
            raise RuntimeError(f"Missing staged disk: {disk}")
    if (staged / NAMES[0]).samefile(staged / NAMES[1]):
        raise RuntimeError("Staged disks must be separate files")
    backup = Path(tempfile.mkdtemp(prefix="backup-", dir=base)) if existing else None
    moved_old, moved_new = [], []
    try:
        for disk in existing:
            os.replace(disk, backup / disk.name)
            moved_old.append(disk.name)
        for name in NAMES:
            os.replace(staged / name, base / name)
            moved_new.append(name)
    except OSError as error:
        recovery_errors = []
        for name in reversed(moved_new):
            try:
                os.replace(base / name, staged / name)
            except OSError as recovery:
                recovery_errors.append(str(recovery))
        for name in reversed(moved_old):
            try:
                os.replace(backup / name, base / name)
            except OSError as recovery:
                recovery_errors.append(str(recovery))
        raise RuntimeError(f"Disk replacement failed: {error}; backup={backup}; "
                           f"recovery errors={recovery_errors}") from error
    if backup:
        print(f"Previous disks backed up to: {backup}")
    print(f"Debian disks ready: {base}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "publish"))
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--staged", type=Path)
    parser.add_argument("--recreate", choices=("0", "1"), default="0")
    args = parser.parse_args()
    base = args.base.resolve()
    if args.action == "check":
        check(base, args.recreate == "1")
    else:
        if args.staged is None:
            parser.error("publish requires --staged")
        check(base, args.recreate == "1")
        publish(base, args.staged.resolve(), args.recreate == "1")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"STOP: {error}", file=sys.stderr)
        sys.exit(1)
