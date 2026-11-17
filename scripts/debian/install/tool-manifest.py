#!/usr/bin/env python3
"""Deterministic installed-file inventories and paired tool versions."""
import argparse
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CHECKER = "scripts/debian/update/check-virt-tools.sh"
HELPER = "scripts/debian/install/install-tools.sh"
HOST = (
    ("build/virt-kvm/src/kvmtool/lkvm-static", "payload/lkvm", "0755", "/usr/bin/lkvm"),
    ("build/virt-kvm/out/pv-user-test", "payload/pv-user-test", "0755", "/usr/bin/pv-user-test"),
    ("build/virt-kvm/out/linux-guest/arch/riscv/boot/Image", "payload/Image", "0644", "/opt/guest/Image"),
    ("tests/pmp-virt/runtime/check-host.sh", None, "0755", "/usr/bin/check-virt-host"),
    ("scripts/debian/run/run-debian-guest.sh", "payload/run-debian-guest", "0755", "/usr/local/bin/run-debian-guest"),
    ("tests/pmp-virt/regression/debian/test-virt-debian-all.sh", None, "0755", "/usr/local/bin/test-virt-debian-all"),
    ("scripts/debian/update/update-virt-tools.sh", None, "0755", "/usr/local/bin/update-virt-tools"),
)
GUEST = (
    ("tests/pmp-virt/runtime/check-guest.sh", None, "0755", "/usr/local/bin/check-virt-guest"),
    ("tests/pmp-virt/regression/debian/virt-guest-test.service", None, "0644", "/etc/systemd/system/virt-guest-test.service"),
    ("scripts/debian/update/update-guest-tools.sh", None, "0755", "/usr/local/bin/update-guest-tools"),
)
COMMON = (
    (CHECKER, None, "0755", "/usr/local/bin/check-virt-tools"),
    ("scripts/debian/update/update-tools.sh", None, "0755", "/usr/local/libexec/virt-tools/update-tools"),
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inventories(root=ROOT):
    bundles = {}
    for role, entries in (("guest", GUEST), ("host", HOST)):
        files, rows = {}, []
        for source, packaged, mode, target in (*entries, *COMMON):
            source_bytes = (root / source).read_bytes()
            packaged = packaged or source
            files[packaged] = source_bytes
            rows.append((target, f"{digest(source_bytes)}\t{mode}\t{packaged}\t{target}\n"))
        if role == "host":
            packaged = "metadata/host/EXPECTED-GUEST-VERSION"
            content = (bundles["guest"]["version"] + "\n").encode()
            files[packaged] = content
            rows.append(("/var/lib/virt-tools/EXPECTED-GUEST-VERSION",
                         f"{digest(content)}\t0644\t{packaged}\t/var/lib/virt-tools/EXPECTED-GUEST-VERSION\n"))
        for source in (HELPER, f"scripts/debian/install/install-{role}.sh"):
            files[source] = (root / source).read_bytes()
        manifest = "".join(row for _, row in sorted(rows)).encode()
        inputs = "".join(f"{digest(data)}  {name}\n" for name, data in sorted(files.items())).encode()
        version = digest((role + "\n").encode() + manifest + inputs)
        bundles[role] = {"files": files, "manifest": manifest, "inputs": inputs, "version": version}
    return bundles


def expected_versions(root=ROOT):
    return {role: bundle["version"] for role, bundle in inventories(root).items()}


def write_bundles(output, root=ROOT):
    bundles = inventories(root)
    for role, bundle in bundles.items():
        folder = output / role
        for name, data in bundle["files"].items():
            path = folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        metadata = folder / "metadata" / role
        metadata.mkdir(parents=True, exist_ok=True)
        for name, data in (("FILES.tsv", bundle["manifest"]), ("INPUTS.SHA256SUMS", bundle["inputs"]),
                           ("VERSION", (bundle["version"] + "\n").encode()), ("ROLE", (role + "\n").encode())):
            (metadata / name).write_bytes(data)
        (output / f"{role.upper()}-VERSION").write_text(bundle["version"] + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_bundles(args.output)
