#!/usr/bin/env python3
# SPDX-FileCopyrightText: Alex Murray
# SPDX-License-Identifier: Apache-2.0
#
# Recompute the sha256 checksums pinned in snap/snapcraft.yaml for whatever
# Claude Code version its top-level `version:` field currently declares, and
# rewrite them in place if they've drifted.
#
# Why this exists: Renovate's github-releases datasource only knows version
# strings, not binary content hashes, so its regex manager can bump the
# `version:` field but has no way to also update the EXPECTED_SHA256 values
# in snap/snapcraft.yaml's override-build. Run by
# .github/workflows/update-checksums.yml on every PR touching
# snap/snapcraft.yaml (Renovate's included) to close that gap automatically.
# Safe to run by hand too: a no-op (exit 0, no changes) when the pinned
# hashes already match.
#
# Both source URLs reference $CRAFT_PROJECT_VERSION, so there's exactly one
# place the version can be wrong — no cross-URL sync check needed here.

from __future__ import annotations

import hashlib
import io
import re
import sys
import tarfile
import urllib.request
from pathlib import Path

SNAPCRAFT_YAML = Path(__file__).resolve().parent.parent / "snap" / "snapcraft.yaml"

CRAFT_ARCHES = ["amd64", "arm64"]

VERSION_RE = re.compile(r'^version:\s*"([0-9]+\.[0-9]+\.[0-9]+)"', re.MULTILINE)


def fetch_claude_binary_sha256(version: str, craft_arch: str) -> str:
    platform = "x64" if craft_arch == "amd64" else craft_arch
    url = (
        f"https://github.com/anthropics/claude-code/releases/download/"
        f"v{version}/claude-linux-{platform}.tar.gz"
    )
    print(f"Fetching {url}", file=sys.stderr)
    with urllib.request.urlopen(url) as resp:  # noqa: S310 - fixed https github.com release URL
        data = resp.read()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        member = tar.extractfile("claude")
        if member is None:
            raise RuntimeError(f"claude not found in {url}")
        digest = hashlib.sha256(member.read()).hexdigest()
    print(f"  sha256: {digest}", file=sys.stderr)
    return digest


def main() -> int:
    text = SNAPCRAFT_YAML.read_text()

    version_match = VERSION_RE.search(text)
    if version_match is None:
        print(
            f"ERROR: could not find a top-level version: \"X.Y.Z\" field in "
            f"{SNAPCRAFT_YAML}",
            file=sys.stderr,
        )
        return 1
    version = version_match.group(1)

    changed = False
    for craft_arch in CRAFT_ARCHES:
        expected = fetch_claude_binary_sha256(version, craft_arch)

        # Scope the replacement to this arch's own `case` block, so updating
        # amd64's hash can never accidentally touch arm64's (or vice versa).
        block_re = re.compile(
            rf'({re.escape(craft_arch)}\)\s*\n\s*EXPECTED_SHA256=)[0-9a-f]{{64}}'
        )
        new_text, n = block_re.subn(rf"\g<1>{expected}", text, count=1)
        if n != 1:
            print(
                f"ERROR: could not find a {craft_arch}) EXPECTED_SHA256= line "
                f"to update in {SNAPCRAFT_YAML}",
                file=sys.stderr,
            )
            return 1

        if new_text != text:
            print(f"Updated {craft_arch} checksum to {expected}", file=sys.stderr)
            changed = True
        else:
            print(f"{craft_arch} checksum already up to date ({expected})", file=sys.stderr)
        text = new_text

    if changed:
        SNAPCRAFT_YAML.write_text(text)
        print("changed=true")
    else:
        print("changed=false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
