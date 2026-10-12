#!/usr/bin/env python3
# SPDX-FileCopyrightText: Alex Murray
# SPDX-License-Identifier: Apache-2.0
#
# Recompute the sha256 checksums pinned in snap/snapcraft.yaml for whatever
# Claude Code version its top-level `version:` field currently declares
# (EXPECTED_SHA256), and for whatever Claude Desktop version the
# claude-desktop part's .deb URL declares (EXPECTED_DEB_SHA256), and rewrite
# them in place if they've drifted.
#
# Why this exists: Renovate's datasources (github-releases for the CLI, deb
# for Claude Desktop) only know version strings, not binary content hashes,
# so its regex managers can bump the versions but have no way to also update
# the pinned checksums in snap/snapcraft.yaml's override-build scripts. Run by
# .github/workflows/update-checksums.yml on every PR touching
# snap/snapcraft.yaml (Renovate's included) to close that gap automatically.
# Safe to run by hand too: a no-op (exit 0, no changes) when the pinned
# hashes already match.
#
# Both CLI source URLs reference $CRAFT_PROJECT_VERSION, and the single
# desktop .deb URL references $CRAFT_ARCH_BUILD_FOR, so each version lives in
# exactly one place — no cross-URL sync check needed here.

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

DESKTOP_REPO = "https://downloads.claude.ai/claude-desktop/apt/stable"

DESKTOP_VERSION_RE = re.compile(r"/claude-desktop_([^_/]+)_\$CRAFT_ARCH_BUILD_FOR\.deb")


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


def fetch_claude_desktop_deb_sha256(version: str, craft_arch: str) -> str | None:
    # The repository's Packages index already carries each .deb's SHA256
    # (and is itself covered by the PGP-signed InRelease), so there's no
    # need to download the ~180 MB .deb just to hash it. Debian's
    # architecture names match craft's for both supported arches.
    #
    # Returns None if this arch's index doesn't list `version` (yet):
    # Renovate only watches the amd64 index, so a bump can land before the
    # same version is published for arm64.
    url = f"{DESKTOP_REPO}/dists/stable/main/binary-{craft_arch}/Packages"
    print(f"Fetching {url}", file=sys.stderr)
    with urllib.request.urlopen(url) as resp:  # noqa: S310 - fixed https downloads.claude.ai URL
        index = resp.read().decode()
    for stanza in index.split("\n\n"):
        fields = dict(
            line.split(": ", 1) for line in stanza.splitlines() if ": " in line and not line.startswith(" ")
        )
        if fields.get("Package") == "claude-desktop" and fields.get("Version") == version:
            digest = fields["SHA256"]
            print(f"  sha256: {digest}", file=sys.stderr)
            return digest
    print(f"  claude-desktop {version} not found in {url}", file=sys.stderr)
    return None


def update_case_block(text: str, var: str, craft_arch: str, digest: str) -> str | None:
    """Replace the digest assigned to `var` in this arch's own `case` block.

    Scoped to the block so updating amd64's hash can never accidentally touch
    arm64's (or vice versa), and keyed on the variable name so the CLI's and
    the desktop app's blocks can't be confused either. Returns None if the
    block isn't found.
    """
    block_re = re.compile(rf"({re.escape(craft_arch)}\)\s*\n\s*{var}=)\S+")
    new_text, n = block_re.subn(rf"\g<1>{digest}", text, count=1)
    return new_text if n == 1 else None


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

    desktop_match = DESKTOP_VERSION_RE.search(text)
    if desktop_match is None:
        print(
            f"ERROR: could not find a claude-desktop_<version>_$CRAFT_ARCH_BUILD_FOR.deb "
            f"source URL in {SNAPCRAFT_YAML}",
            file=sys.stderr,
        )
        return 1
    desktop_version = desktop_match.group(1)

    pins = [
        ("EXPECTED_SHA256", lambda arch: fetch_claude_binary_sha256(version, arch)),
        ("EXPECTED_DEB_SHA256", lambda arch: fetch_claude_desktop_deb_sha256(desktop_version, arch)),
    ]

    changed = False
    missing = []
    for var, fetch in pins:
        for craft_arch in CRAFT_ARCHES:
            expected = fetch(craft_arch)
            if expected is None:
                # Leave this arch's pin alone, but still update the others,
                # then report it below.
                missing.append(f"{craft_arch} {var}")
                continue
            new_text = update_case_block(text, var, craft_arch, expected)
            if new_text is None:
                print(
                    f"ERROR: could not find a {craft_arch}) {var}= line "
                    f"to update in {SNAPCRAFT_YAML}",
                    file=sys.stderr,
                )
                return 1

            if new_text != text:
                print(f"Updated {craft_arch} {var} to {expected}", file=sys.stderr)
                changed = True
            else:
                print(f"{craft_arch} {var} already up to date ({expected})", file=sys.stderr)
            text = new_text

    if changed:
        SNAPCRAFT_YAML.write_text(text)
        print("changed=true")
    else:
        print("changed=false")

    if missing:
        # Exit 2 (distinct from 1, a real error) so update-checksums.yml can
        # still commit the arches that were updated, then fail visibly.
        print(
            f"ERROR: version not published yet for: {', '.join(missing)}. "
            f"Their pins were left unchanged; re-run once it is.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
