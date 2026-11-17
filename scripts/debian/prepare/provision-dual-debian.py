#!/usr/bin/env python3
"""Initialize both staged Debian disks using shared maintenance boots."""
import importlib.util
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("debian_maintenance", ROOT / "scripts/debian/common/maintenance.py")
maintenance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(maintenance)


def main():
    if len(sys.argv) != 2:
        raise RuntimeError("Usage: provision-dual-debian.py DEPLOYMENT_DIRECTORY")
    deploy = Path(sys.argv[1]).resolve()
    maintenance.validate_deploy(deploy)

    subprocess.run(
        [sys.executable, str(ROOT / "scripts/build/virt-kvm.py"), "verify"],
        cwd=ROOT, check=True,
    )
    for role in ("host", "guest"):
        maintenance.provision(deploy, role)
    print("DUAL DEBIAN PROVISION PASS")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"STOP: {error}", file=sys.stderr)
        sys.exit(1)
