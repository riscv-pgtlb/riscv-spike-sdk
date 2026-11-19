#!/usr/bin/env python3
"""Update tools on two stopped Debian disks using temporary QEMU maintenance boots."""
import argparse
from contextlib import ExitStack
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("debian_maintenance", ROOT / "scripts/debian/common/maintenance.py")
maintenance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(maintenance)


def validate_disks(host, guest):
    for disk in (host, guest):
        if not disk.is_file() or not os.access(disk, os.R_OK | os.W_OK):
            raise RuntimeError(f"Disk missing or not readable/writable: {disk}")
    if host.samefile(guest):
        raise RuntimeError("Host and guest disks must be separate files")


check_stopped = maintenance.check_stopped


def update(host, guest):
    validate_disks(host, guest)
    (ROOT / "build").mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        operation = stack.enter_context((ROOT / "build/debian-operation.lock").open("a"))
        try:
            fcntl.flock(operation, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another Debian prepare, update or VM run is active") from error
        # Prevent simultaneous invocations of this updater on either disk.
        for disk in sorted((host, guest)):
            stream = stack.enter_context(disk.open("r+b"))
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RuntimeError(f"Another update is using {disk}") from error
        check_stopped(host, guest)
        subprocess.run(["bash", str(ROOT / "scripts/debian/install/pack-tools.sh")], cwd=ROOT, check=True)
        output = ROOT / "build/debian-updates"
        output.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="update-", dir=output))
        print(f"Update logs: {work}", flush=True)
        state = {"host_disk": str(host), "guest_disk": str(guest), "completed": []}

        def save():
            (work / "status.json").write_text(json.dumps(state, indent=2) + "\n")

        save()
        try:
            (work / "debian-host.raw").symlink_to(host)
            (work / "debian-guest.raw").symlink_to(guest)
            stage = work / "setup"
            stage.mkdir()
            shutil.copyfile(ROOT / "scripts/debian/update/update-system.sh", stage / "update-system.sh")
            for name in ("debian-host-tools.tar.gz", "debian-guest-tools.tar.gz", "SHA256SUMS",
                         "HOST-VERSION", "GUEST-VERSION"):
                shutil.copyfile(ROOT / "build/debian-tools" / name, stage / name)
            state["tools_versions"] = {role: (stage / f"{role.upper()}-VERSION").read_text().strip()
                                       for role in ("host", "guest")}
            save()
            with tarfile.open(work / "setup.tar", "w") as archive:
                for path in sorted(stage.iterdir()):
                    archive.add(path, arcname=path.name)
            maintenance.validate_deploy(work)
            for role in ("host", "guest"):
                maintenance.provision(work, role, action="update")
                state["completed"].append(role)
                save()
        except Exception as error:
            state["error"] = str(error)
            save()
            raise RuntimeError(f"Update stopped; completed={state['completed']}; logs: {work}. No rollback performed. {error}") from error
        print("DUAL DEBIAN UPDATE PASS", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-disk", type=Path, required=True)
    parser.add_argument("--guest-disk", type=Path, required=True)
    args = parser.parse_args()
    update(args.host_disk.resolve(), args.guest_disk.resolve())


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"STOP: {error}", file=sys.stderr)
        sys.exit(1)
