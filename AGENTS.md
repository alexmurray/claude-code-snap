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

The snap also has an optional **`desktop` component** carrying Claude
Desktop (beta), Anthropic's Electron desktop app — modeled on
opencode-snap's `desktop` component. See
[Claude Desktop component](#claude-desktop-component) below; it has a
different upstream channel and version from the CLI.

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
6. Fetch Claude Desktop's `.deb` from Anthropic's apt repository, verify its
   sha256 against a value pinned from the repository's `Packages` index,
   unpack it, and route the app tree into the `desktop` component (see
   [Claude Desktop component](#claude-desktop-component)).

## Key files

| File | Purpose |
|---|---|
| `snap/snapcraft.yaml` | Snap build definition with 5 parts and the `desktop` component |
| `snap/local/claude.wrapper` | Wrapper that unsets `SNAP_*` env vars, sources `claude-onexec.sh`, prepends bundled clipboard tools to PATH |
| `snap/local/claude-onexec.sh` | AppArmor onexec-arming logic, shared with `tests/smoke/apparmor-onexec/task.yaml` |
| `snap/local/claude.completion` | Hand-written bash completion (claude has no completion generator) |
| `snap/local/claude-LICENSE.md` | Static copy of the bundled binary's LICENSE notice |
| `snap/local/claude-desktop.wrapper` | Desktop app wrapper: checks the component is installed, notifies about missing Cowork prerequisites, sources `claude-onexec.sh`, picks `--no-sandbox` only where needed, execs the component's Electron binary |
| `snap/local/claude-desktop-cowork-check.sh` | Mirrors the app's Cowork prerequisite checks; sets `COWORK_HINT`. Sourced by the wrapper and `tests/smoke/desktop` |
| `snap/gui/icon.png` | Claude Code's own launch-screen mascot |
| `scripts/update-checksums.py` | Recomputes pinned CLI and desktop `.deb` checksums from the pinned versions; run by `update-checksums.yml`, safe by hand |
| `renovate.json` | Custom regex managers (`github-releases` datasource against `anthropics/claude-code`, `deb` datasource against the Claude Desktop apt repo) |
| `spread.yaml` | Spread test backend config (image-garden adhoc backend) |
| `.image-garden.mk` | image-garden cloud-init user-data templates (core26) |
| `tests/smoke/claude-code/task.yaml` | Install/help/version/license smoke test |
| `tests/smoke/clipboard/task.yaml` | Verifies bundled wl-copy/wl-paste are on PATH and actually run |
| `tests/smoke/apparmor-onexec/task.yaml` | Verifies the AppArmor onexec workaround |
| `tests/smoke/desktop/task.yaml` | Verifies the `desktop` component installs, its desktop entry is exported, and Claude Desktop launches under Xvfb: unconfined, a process it spawns can redirect a strict snap's output (LP: #1849753), sandbox only disabled where needed, Cowork hint remembered, and the missing-component message |
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
- **Components**: `desktop` (standard) — Claude Desktop, installed
  separately with `snap install claude-code+desktop`
- **Runtime**: the bundled `claude` binary is a Bun-compiled standalone
  executable (dynamically linked against the host's glibc/libpthread/libdl/
  librt/libm) — no bundled language runtime, unlike pi-coding-agent-snap's
  bundled Node.js
- **CI pipeline**: `build.yml` → `tasteful-crafts.yml` builds the snap for
  both architectures (LXD) and runs image-garden spread integration tests
  against the amd64 build (snap + `desktop` component) across
  Ubuntu/Debian/Fedora cloud systems. It does not
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

Claude Desktop is versioned independently (e.g. `2.31226.1` vs the CLI's
`2.1.295`) and pinned separately, in the `claude-desktop` part's single
`.deb` source URL (`claude-desktop_<version>_$CRAFT_ARCH_BUILD_FOR.deb` —
craft-parts expands `$CRAFT_ARCH_BUILD_FOR` in `source:`, and Debian's arch
names match craft's). Renovate's `deb` datasource tracks it against the apt
repository's amd64 index, and the same `update-checksums.py` run fixes
`EXPECTED_DEB_SHA256`, taking it from each arch's `Packages` index rather
than downloading the ~180 MB `.deb`. The component's version is read from
the `.deb`'s own control file at build time
(`craftctl set components.desktop.version=`), so it can't drift from the
URL. A desktop-only bump doesn't change the snap's `version:`, so
`release.yml`'s tags (which track the CLI version) are unaffected.

Since Renovate only watches the amd64 index, a bump can land before arm64
publishes the same version. `update-checksums.py` then updates the arches
it can, leaves the missing one's pin alone and exits 2;
`update-checksums.yml` commits the partial update and fails with a "re-run
once it's published" error rather than a confusing checksum mismatch
later.

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

## Claude Desktop component

Claude Desktop (beta) is Anthropic's Electron desktop app
([docs](https://code.claude.com/docs/en/desktop-linux)). It ships as the
snap's `desktop` component (~590 MB unpacked), so CLI-only users don't
download it, and launches via the `claude-code.desktop` app / the "Claude"
launcher entry.

### Source: Anthropic's apt repository, not GitHub

Unlike the CLI, Claude Desktop is published *only* as a `.deb` in
Anthropic's apt repository on `downloads.claude.ai` — the channel the CLI
avoids because that host enforces Anthropic's regional
service-availability allowlist. There's no alternative, so **building the
`desktop` component (and therefore the snap) requires a builder in a
supported country**. Launchpad's and GitHub Actions' builders currently
are; a contributor building from an unsupported region will see the
`claude-desktop` part's fetch fail.

The launcher entry is upstream's own `com.anthropic.Claude.desktop`, taken
from the `.deb` at build time: the part rewrites each `Exec=` (including
the desktop actions') to `claude-code.desktop` and `Icon=` to the bundled
icon, and installs it straight into `meta/gui/desktop.desktop` (snapd
exports it as `claude-code_desktop.desktop`), so upstream's new actions,
MIME types etc. carry over without a hand-maintained copy. Two things it
works around: snapcraft's own rewrite (an app's `desktop:` key) would
overwrite `Icon=` with the snap-level icon (`snap/gui/icon.png`, the CLI's
mascot), and snapd only accepts `Exec=` lines that run one of the snap's
own apps. The build fails if any `Exec=`/`Icon=` line isn't as expected
after the rewrite (e.g. upstream starts launching via `env FOO=1
claude-desktop`), rather than shipping a broken launcher.
`tests/smoke/desktop` checks the exported entry, actions included.

The part takes the `.deb`'s payload only (`dpkg-deb -x`); its maintainer
scripts never run. On a host they'd register the apt repository and
unattended-upgrades origin (irrelevant: the snap updates through the
store), an AppArmor userns profile for `/usr/lib/claude-desktop/...`
(doesn't apply to snap paths — see below), a GNOME Shell search provider
and the `.mcpb`/`.skill` MIME types (system-wide registrations a snap
can't make: not provided), and a `/usr/bin/ccd` link (not shipped by
current builds).

Runtime libraries (GTK 3, NSS, libsecret, ...) come from the host, as with
opencode-snap's desktop component, matching the upstream `.deb`'s Debian-
based-distro support; nothing is bundled. Cowork needs the host's QEMU/KVM
exactly as documented upstream.

### Deliberately not bundled: QEMU, firmware, GTK and friends

The boundary is the process: the snap ships Anthropic's binaries, the host
provides what they load or run. Don't re-propose bundling these without new
information:

- **Cowork (QEMU/OVMF/virtiofsd/KVM)**: the app finds `qemu-system-*` via
  `PATH`, but checks the UEFI firmware (`/usr/share/OVMF/...`,
  `/usr/share/AAVMF/...`) and `virtiofsd` (`/usr/libexec/virtiofsd`,
  `/usr/bin/virtiofsd`) only at hardcoded host paths, and only uses its own
  bundled `virtiofsd` on Ubuntu 22.04. A classic snap can't supply files at
  those paths, and `/dev/kvm`/`vhost_vsock`/`kvm` group membership are host
  kernel/admin state anyway. Bundling QEMU alone would still leave users
  installing `ovmf virtiofsd` from apt, so it buys nothing; making the rest
  work would mean patching Anthropic's `app.asar`, which this repo doesn't
  do.
- **GTK/NSS/Mesa and the rest of Electron's ~20 non-core26 libraries**:
  mechanically easy (`stage-packages` + `enable-patchelf`), but bundled
  GTK/GIO/gdk-pixbuf/Mesa still load plugins from compiled-in host paths
  (ABI mismatches across host releases), and redirecting them needs env
  vars (`GTK_PATH`, `GIO_MODULE_DIR`, `LIBGL_DRIVERS_PATH`, ...) that the
  app would leak into its integrated terminal and Claude Code's tools — the
  VS Code classic snap's long-running bug class, which the wrappers'
  `SNAP_*` unsetting exists to avoid. These libraries are present on any
  desktop host the app makes sense on.

Since the host must provide these, the wrapper at least says what's
missing: the app only reports it inside the Cowork tab (whose visibility
is controlled by claude.ai's web UI, so it may not show at all) and logs
just `status=unsupported`. `claude-desktop-cowork-check.sh` mirrors the
app's checks (read from its bundle; keep in sync if a release changes
them) and the wrapper sends a desktop notification with the exact
`apt install`/`usermod -aG kvm` fix, once per distinct set of problems
(remembered in `$SNAP_USER_COMMON/cowork-hint`, written only once the
notification is accepted, so a launch with no notification daemon doesn't
count as shown), plus a stderr line on every launch.

The notification goes straight to the `org.freedesktop.Notifications`
D-Bus service via a bundled `gdbus` (the `gdbus` part), not `notify-send`:
`libnotify-bin` is optional on many distros, and bundling it would pull in
gdk-pixbuf and its host-path loader plugins. `gdbus` needs only GLib/GIO,
which core26 already has (core26's own `dbus-send` can't encode
`Notify`'s `a{sv}` argument). It lives in `$SNAP/usr/libexec/claude-code/`,
not `$SNAP/usr/bin/`, so the wrappers' PATH prepend (for `wl-copy`/
`wl-paste`) doesn't shadow the host's `gdbus` for the app and Claude Code;
and it runs with `GIO_MODULE_DIR` pointed at a nonexistent directory, for
that one command only, so core26's GIO never loads the host's GIO modules.
Two gotchas if it changes: `gdbus call` needs `--` before the arguments,
or it reads the trailing `-1` (server-default expiry) as an option; and in
`tests/smoke/desktop`, the bus must be the user's systemd instance's
(lingering + `dbus-user-session`), not a bare `dbus-run-session` one —
with a session bus present, `snap run` asks the systemd user instance on
it to track the app's processes and refuses to run without one.

### Confinement and Chromium's sandbox

`claude-desktop.wrapper` sources the same `claude-onexec.sh` as
`claude.wrapper`, so the app and everything it spawns run unconfined (same
LP: #1849753 reasoning). opencode-snap instead keeps its main process under
the snap label and patches its *own* JS bundle to arm onexec for children
only; this snap can't reasonably patch Anthropic's `app.asar`, and doesn't
need the snap label for dock grouping either — the desktop entry's
`StartupWMClass=com.anthropic.Claude` matches the app's WM_CLASS/app_id.

Running unconfined has a consequence for Chromium's renderer sandbox,
which needs either unprivileged user namespaces or the setuid
`chrome-sandbox` helper. A snap can't ship a working setuid binary (the
part deletes it), and on Ubuntu 23.10+
(`kernel.apparmor_restrict_unprivileged_userns=1`) unconfined processes
can't use user namespaces either — the upstream `.deb` solves that with an
AppArmor profile attached to its own `/usr/lib` path, which doesn't cover
`/snap/...`. So the wrapper passes `--no-sandbox` **only** when that sysctl
(or Debian's `kernel.unprivileged_userns_clone=0`) blocks it, and keeps the
sandbox everywhere else. opencode-snap passes `--no-sandbox`
unconditionally. `tests/smoke/desktop` checks both branches: `--no-sandbox`
present on Ubuntu, and on Debian absent with renderers actually in their
own user namespace.

`tests/smoke/desktop` also checks the onexec workaround end to end, from a
process the app itself spawns: at every startup (before any sign-in) the
app runs the user's login shell (`$SHELL -l -i -c '... env -0 ...'`, from
a utility process) to load their environment, so the test points `$SHELL`
at a probe script that redirects `snap run hello-world` to a file. Without
onexec that redirect fails (`rc=1` under `snap.claude-code.desktop
(complain)` — verified on Ubuntu 26.04 and Debian 13 when the test was
written); with it, it succeeds. Signed-in paths (Code tab sessions, which
run a `claude` binary the app downloads itself into
`~/.config/Claude/claude-code/<version>/` rather than the snap's; Cowork's
VM) can't be exercised headlessly and are untested.

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
  `claude-desktop.wrapper`, `claude-onexec.sh`, the `clipboard`,
  `apparmor-onexec` and `desktop` smoke tests
- **Alex Murray only** (written for this project): `snap/snapcraft.yaml`,
  `claude.completion`, the `claude-code` smoke test

`renovate.json` has no SPDX header (JSON has no comment syntax) despite
being structurally derived from the same two repos — noted here instead.

`snap/gui/icon.png` is Claude Code's own mascot, not an Apache-2.0 asset —
used to identify the packaged product (nominative use), not under this
repo's license, not implying endorsement.

Claude Code and Claude Desktop are proprietary software — all rights
reserved by Anthropic PBC (the component carries the `.deb`'s own
`copyright` file); see https://code.claude.com/docs/en/overview. This project is
unofficial and not affiliated with or endorsed by Anthropic.
