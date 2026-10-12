# claude-snap — Agent Rules

## Project overview

This repository builds a **classic snap** of [Claude Code](https://code.claude.com/docs/en/overview),
Anthropic's agentic coding CLI, using Snapcraft.

Claude Code is **closed source**. Unlike this repo's siblings
(pi-coding-agent-snap, opencode-snap), there is no upstream source to clone
and build — the snap fetches Anthropic's official prebuilt `claude` binary
directly from `anthropics/claude-code`'s GitHub release assets and wraps it
for classic confinement. That repo holds no source, but does publish real
tagged releases with per-platform binaries (`claude-linux-x64.tar.gz`,
`claude-linux-arm64.tar.gz`) and a PGP-signed `SHASUMS256.txt`.

GitHub was chosen over two other channels that also work (npm, and
`downloads.claude.ai` — the channel `claude.ai/install.sh` uses): npm
install is deprecated upstream, and `downloads.claude.ai` enforces
Anthropic's regional service-availability allowlist, which would make the
*build* fail outside supported countries. GitHub release assets have
neither problem and the strongest provenance (a real signature, not just
an unsigned manifest). All three channels serve byte-identical binaries.

### Why not strict confinement

[pfsmorigo/snaps](https://github.com/pfsmorigo/snaps) already publishes a
Claude Code snap using **strict** confinement. Worth knowing why this repo
doesn't:

- Strict confinement's `home` interface doesn't grant access to dotfiles
  (`~/.claude/`), so that snap redirects `HOME`/`XDG_CONFIG_HOME` into a
  snap-private directory instead — config/credentials don't land in the
  user's real `~/.claude`.
- An agent's Bash tool needs arbitrary host tools (make, cargo, docker, ...),
  which strict confinement can't reach. That snap works around it by
  bundling a kitchen-sink toolchain into every snap in that repo regardless
  of need — exactly what classic confinement avoids by using the host's own
  tools.
- Their `snapcraft.yaml` declares `license: Apache-2.0`, which is wrong for
  closed-source, all-rights-reserved software — why this repo leaves
  `license:` unset rather than guess (that's the *bundled binary's*
  license; unrelated to this repo's own Apache-2.0 packaging license, see
  below).
- Their published icon is `snap/gui/icon.png` here too now — Claude Code's
  real launch-screen mascot, sourced from `pfsmorigo/snaps` and verified
  against anthropics/claude-code's own demo.gif. There's no standalone
  asset for it upstream; the CLI renders it itself.

## Build process

1. Fetch the per-arch native binary from `anthropics/claude-code`'s GitHub
   release assets. Both URLs interpolate the top-level `version:` field via
   `$CRAFT_PROJECT_VERSION` (expands at fetch time, before `source:` is
   pulled) — no `adopt-info:`/`craftctl set version=`, since nothing here
   is derived at build time. Renovate only has to touch the one field.
2. Verify the fetched binary's sha256 against a pinned value taken from the
   release's own `SHASUMS256.txt`. `source-checksum` can't do this:
   craft-parts rejects its per-architecture `on <arch> to <arch>` grammar
   outright, and the two architectures need different checksums. Splitting
   into two arch-specific parts wouldn't help either — there's no part-level
   "only build this for arch X" mechanism, so both would still need the
   same `$CRAFT_ARCH_BUILD_FOR` conditional this avoids, just duplicated.
3. Stage the binary at `$SNAP/bin/claude`; `claude.wrapper` execs it
   directly — no bundled runtime needed (standalone ELF binary).
4. Install `wl-clipboard` via `stage-packages` for Wayland clipboard support
   (Claude Code shells out to `wl-copy`/`wl-paste` by name on PATH; X11
   tools are left to the host).
5. Install wrapper script, bash completion, and a static LICENSE notice for
   the bundled binary (the release tarball holds only the bare binary).

## Key files

| File | Purpose |
|---|---|
| `snap/snapcraft.yaml` | Snap build definition with 3 parts |
| `snap/local/claude.wrapper` | Wrapper that unsets `SNAP_*` env vars, sources `claude-onexec.sh`, prepends bundled clipboard tools to PATH |
| `snap/local/claude-onexec.sh` | AppArmor onexec-arming logic, shared with `tests/smoke/apparmor-onexec/task.yaml` |
| `snap/local/claude.completion` | Hand-written bash completion (claude has no completion generator) |
| `snap/local/claude-LICENSE.md` | Static copy of the bundled binary's LICENSE notice |
| `snap/gui/icon.png` | Claude Code's own launch-screen mascot |
| `scripts/update-checksums.py` | Recomputes pinned checksums from `version:`; run by `update-checksums.yml`, safe by hand |
| `renovate.json` | Custom regex managers (`github-releases` datasource against `anthropics/claude-code`) |
| `spread.yaml` | Spread test backend config (image-garden adhoc backend) |
| `.image-garden.mk` | image-garden cloud-init user-data templates (core26) |
| `tests/smoke/claude-code/task.yaml` | Install/help/version/license smoke test |
| `tests/smoke/clipboard/task.yaml` | Verifies bundled wl-copy/wl-paste are on PATH and actually run |
| `tests/smoke/apparmor-onexec/task.yaml` | Verifies the AppArmor onexec workaround |
| `.github/workflows/build.yml` | CI entry point; delegates to `tasteful-crafts.yml` |
| `.github/workflows/tasteful-crafts.yml` | Reusable build → spread-test orchestrator (no publish step) |
| `.github/workflows/snapcraft-pack.yml` | Per-architecture snap build (reusable, uses LXD) |
| `.github/workflows/spread.yml` | Reusable image-garden spread runner |
| `.github/workflows/release.yml` | Create Git tags + GitHub releases from Renovate PRs |
| `.github/workflows/update-checksums.yml` | Auto-fixes stale `EXPECTED_SHA256` values on any PR touching `snap/snapcraft.yaml` |
| `.github/actions/install-cached-snap/` | Composite action: install a snap with caching |
| `.gitignore` | Ignore build artifacts (`*.snap`, `*.comp`, image-garden/spread VM artifacts) |

## Architecture

- **Base**: `core26` (Ubuntu 26.04 LTS)
- **Confinement**: `classic` (needs unrestricted filesystem access to edit
  the user's code and run arbitrary shell commands)
- **Platforms**: amd64, arm64
- **Runtime**: the bundled `claude` binary is a Bun-compiled standalone
  executable (dynamically linked against the host's glibc/libpthread/libdl/
  librt/libm) — no bundled language runtime, unlike pi-coding-agent-snap's
  bundled Node.js
- **CI pipeline**: `build.yml` → `tasteful-crafts.yml` builds the snap for
  both architectures (LXD) and runs image-garden spread integration tests
  against the amd64 build across Ubuntu/Debian cloud systems. It does not
  publish anything — publishing to the Snap Store is handled by
  [Launchpad's snap recipe integration](https://snapcraft.io/claude-code/builds),
  which builds directly from this repository, not by GitHub Actions.

## Version management

Claude Code version is pinned via `snap/snapcraft.yaml`'s top-level
`version:` field (no `source-tag`, since there's no source repo). Renovate's
`github-releases` datasource tracks `anthropics/claude-code` and auto-creates
PRs when a new version is published.

Update the version by changing `version:` AND the expected version in
`tests/smoke/claude-code/task.yaml`. `EXPECTED_SHA256` doesn't need manual
updating: Renovate's datasource only knows version strings, not binary
hashes, so `.github/workflows/update-checksums.yml` runs
`scripts/update-checksums.py` on any PR touching `snap/snapcraft.yaml`
(Renovate's own included), which re-derives the checksums and pushes a
fixup commit if they've drifted. No-op when already correct; safe to run by
hand (`python3 scripts/update-checksums.py`). Skips itself cleanly on fork
PRs, where `GITHUB_TOKEN` can't push back.

## Clipboard strategy

Claude Code shells out to a clipboard tool resolved via PATH:

- **Wayland**: `wl-copy`/`wl-paste` — bundled via `stage-packages`. The
  wrapper prepends `$SNAP/usr/bin` to PATH before exec'ing claude.
- **X11**: `xclip`/`xsel` — left to the host (not bundled).

### ELF patching: enable-patchelf, not manual patchelf

Classic confinement skips snapcraft's automatic ELF interpreter/rpath
patching by default. wl-copy/wl-paste are the exception: they need to
resolve against the base snap's bundled `libwayland-client.so.0`, not the
host's. `wl-clipboard` sets `build-attributes: [enable-patchelf]` rather
than hand-rolling `patchelf` calls (the approach pi-coding-agent-snap and
opencode-snap both use) — it computes the rpath from the binary's real
DT_NEEDED dependencies instead of a hand-typed guess.

That hand-typed guess in both of those templates has a real bug: their
`_RPATH` is built as a single-quoted shell string containing `\$ORIGIN`
(literal backslash), not the special linker token `$ORIGIN` (no backslash),
so the self-relative half of their rpath is dead. It only works because
their fallback leg happens to find a host-provided `libwayland-client0` —
core26 doesn't ship one at all, so the same command would fail outright on
a minimal host. `tests/smoke/clipboard` actually *runs* wl-copy/wl-paste
(`--version`, no compositor needed) rather than just checking they exist on
PATH, to catch a regression here.

## AppArmor onexec workaround

Classic snaps get a complain-mode (log-only) AppArmor profile whose label is
inherited by every process they spawn. If Claude Code spawns a child that is
itself a snap (e.g. `juju debug-log > file`), snap-confine
rejects file descriptors opened under the parent's label, so output
redirection fails with "bad file descriptor" (see
canonical/pi-coding-agent-snap#26, LP: #1849753). `claude.wrapper` arms
AppArmor's onexec transition before exec'ing `claude` so it — and everything
it spawns — runs fully unconfined, matching pi-coding-agent-snap's pi.wrapper.

`tests/smoke/apparmor-onexec/task.yaml` sources `snap/local/claude-onexec.sh`
— the same file `claude.wrapper` sources, not a copy — so the two can't
drift. Unlike opencode, Claude Code's binary doesn't honor `BUN_BE_BUN=1`
(Anthropic's build strips that escape hatch), so the test can't drop into an
inline probe the way opencode's does; it sources the shared file inside a
`snap run --shell claude-code` instead, which gets the same AppArmor label
the real wrapper runs under.

Two things to keep in mind if this test or `claude.wrapper` ever change:

- **Capture `snap run` output via command substitution, never `> file`.** A
  file opened by the unconfined host shell and then inherited across
  snap-confine's launch of the complain-mode process breaks writes through
  it from the other side (same class of bug the onexec workaround itself
  exists for, hit from the opposite direction). Same reason the `doctor`
  check in `tests/smoke/claude-code/task.yaml` avoids file redirection too.
- **Arming onexec only takes effect at the arming task's own next `exec()`**
  — it does not retroactively unconfine a task that keeps running shell
  builtins afterward. `claude.wrapper` gets this right by construction (arm,
  then immediately `exec "$BIN"`); the test probe mirrors it (arm, then
  immediately `exec sh -c '...'`, with all the real work inside that
  already-transitioned shell).

## License

Apache-2.0 for the snap packaging files in this repository. This project
started by copying substantial CI/CD and test infrastructure (reusable
GitHub Actions workflows, `install-cached-snap`, `.image-garden.mk`,
`spread.yaml`'s backend boilerplate, the AppArmor onexec workaround, some
test prose) from pi-coding-agent-snap and opencode-snap, both Apache-2.0
(Canonical Ltd.). `SPDX-FileCopyrightText` headers reflect actual
provenance per file:

- **Canonical Ltd. only** (copied with no functional change beyond the
  header): `snapcraft-pack.yml`, `spread.yml`,
  `install-cached-snap/action.yaml`+`action.sh`, `.image-garden.mk`
- **Canonical Ltd. + Alex Murray** (adapted/modified): `build.yml`,
  `tasteful-crafts.yml`, `release.yml`, `spread.yaml`, `claude.wrapper`,
  `claude-onexec.sh`, the `clipboard` and `apparmor-onexec` smoke tests
- **Alex Murray only** (written for this project): `snap/snapcraft.yaml`,
  `claude.completion`, the `claude-code` smoke test

`renovate.json` has no SPDX header (JSON has no comment syntax) despite
being structurally derived from the same two repos — noted here instead.

`snap/gui/icon.png` is Claude Code's own mascot, not an Apache-2.0 asset —
used to identify the packaged product (nominative use), not under this
repo's license, not implying endorsement.

Claude Code itself is proprietary software — all rights reserved by
Anthropic PBC; see https://code.claude.com/docs/en/overview. This project is
unofficial and not affiliated with or endorsed by Anthropic.
