# claude-code snap

This repository contains unofficial snap packaging for [Claude Code](https://code.claude.com/docs/en/overview), Anthropic's agentic coding CLI.

The snap packaging is maintained separately from Anthropic. It is not affiliated with or endorsed by Anthropic.

The snap is named **`claude-code`** with two apps:
- `claude-code` — default app (runs as `claude-code`)
- `claude` — alias target (runs as `claude-code.claude`; an alias from `claude` can be requested on the Snap Store forum)

After the alias is granted, users can run just `claude`.

An optional **`desktop` component** adds [Claude Desktop](https://code.claude.com/docs/en/desktop-linux) (beta), Anthropic's desktop app:

```bash
sudo snap install claude-code+desktop
```

Then launch **Claude** from your application launcher, or run `claude-code.desktop`. It's a separate component (~200 MB download) so CLI-only installs don't pay for it.

## What is Claude Code?

Claude Code lives in your terminal, understands your codebase, and helps you code faster through natural language commands — editing files, running tests, and handling git workflows while you stay in control. It requires an Anthropic account (a Claude subscription, or API billing).

- Docs: [code.claude.com/docs](https://code.claude.com/docs/en/overview)
- Issues: [github.com/anthropics/claude-code](https://github.com/anthropics/claude-code/issues)
- Upstream repo (no source, but real releases/tags): [github.com/anthropics/claude-code](https://github.com/anthropics/claude-code)

## Approach

The snap is a **classic snap** with **`base: core26`** (Ubuntu 26.04 LTS), since Claude Code needs unrestricted filesystem access to edit code and run shell commands as an agent.

### Why the snap ships a prebuilt binary

Claude Code is **closed source** — there is no public implementation repository to clone and build from. Anthropic's [`anthropics/claude-code`](https://github.com/anthropics/claude-code) repo holds no source, but does publish real tagged GitHub releases with per-platform binary assets attached (`claude-linux-x64.tar.gz`, `claude-linux-arm64.tar.gz`, plus a PGP-signed `SHASUMS256.txt`). This snap fetches those directly — they *are* the upstream release artifact, not something to compile.

The binary itself is a Bun-compiled standalone executable, dynamically linked against the host's glibc (not statically bundled), so under classic confinement it runs exactly as it would installed via the official installer on the host — no patching needed for the binary itself. Only the bundled `wl-clipboard` tools need ELF patching: classic snaps aren't patched by default, so without it `wl-copy`/`wl-paste` would load the host's libraries instead of the bundled `libwayland-client` and core26's libraries (see AGENTS.md for why this uses snapcraft's `enable-patchelf` build-attribute rather than a hand-written `patchelf` command).

### Build strategy

Inside the LXD build container:

1. **Fetch** the per-arch native binary directly from `anthropics/claude-code`'s GitHub release assets (`plugin: dump` against a pinned per-arch `.tar.gz` URL)
2. **Verify** the fetched binary's sha256 against a pinned known-good value — taken from that release's own PGP-signed `SHASUMS256.txt`, not just computed from the tarball ourselves
3. **Stage** the binary at `$SNAP/bin/claude`
4. **Install `wl-clipboard`** from Ubuntu package via `stage-packages`, ELF-patched for classic confinement via snapcraft's `enable-patchelf` build-attribute (not a hand-written `patchelf` command — see AGENTS.md)
5. **Install** wrapper script, AppArmor onexec helper, bash completion, and a static LICENSE notice for the bundled binary
6. **Fetch** Claude Desktop's `.deb` from Anthropic's apt repository (its only distribution channel), verify its checksum against the repository's `Packages` index, and unpack the app into the `desktop` component

### Parts in snapcraft.yaml

| Part | Plugin | What it does |
|---|---|---|
| `claude-code-binary` | `dump` | Fetch the per-arch native binary from `anthropics/claude-code`'s GitHub releases (URL built from the top-level `version:` field via `$CRAFT_PROJECT_VERSION`); verify its checksum |
| `claude-desktop` | `nil` | Fetch Claude Desktop's `.deb` from Anthropic's apt repository; verify its checksum; unpack the app into the `desktop` component and set the component's version from the `.deb` |
| `gdbus` | `nil` | Stage-package `gdbus` (from `libglib2.0-bin`), privately under `usr/libexec/claude-code/`, for the desktop wrapper's Cowork notification |
| `wl-clipboard` | `nil` | Stage-package from Ubuntu for Wayland clipboard, patched for classic confinement |
| `claude-code-configuration` | `nil` | Install wrapper script, AppArmor onexec helper (`claude-onexec.sh`), bash completion files, and the bundled binary's LICENSE notice |

### Clipboard strategy

Claude Code shells out to a clipboard tool resolved via `PATH`:

| Session | Tool | Source |
|---|---|---|
| **Wayland** | `wl-copy` / `wl-paste` | Bundled (Ubuntu `wl-clipboard` package via `stage-packages`) |
| **X11** | `xclip` / `xsel` | Host-provided (not bundled; most desktops already have one) |

### AppArmor onexec workaround

Classic snaps run under a complain-mode AppArmor profile whose label is inherited by every child process. If Claude Code spawns a child that is itself a snap (e.g. `juju debug-log > file` run via its Bash tool), snap-confine rejects file descriptors opened under Claude Code's label and redirection fails with "bad file descriptor" (`canonical/pi-coding-agent-snap#26`, LP: #1849753). `claude.wrapper` arms AppArmor's onexec transition before exec'ing `claude` so it, and everything it spawns, runs fully unconfined — the same fix used by pi-coding-agent-snap.

### Claude Desktop component

The `desktop` component packages the official Claude Desktop `.deb` payload as-is (its maintainer scripts aren't run), launched through `claude-desktop.wrapper`:

- Like the CLI, the app runs **unconfined** via the same AppArmor onexec workaround.
- Chromium's sandbox is kept wherever the host allows unprivileged user namespaces. On Ubuntu 23.10+ (which restricts them, and where the `.deb`'s own AppArmor profile doesn't cover snap paths) the wrapper falls back to `--no-sandbox`.
- Runtime libraries (GTK, NSS, ...) come from the host, matching upstream's Debian-based-distro support. Cowork needs the host's QEMU/KVM as [documented upstream](https://code.claude.com/docs/en/desktop-linux#cowork-requirements); if anything's missing, the wrapper sends a desktop notification (via a bundled `gdbus`, so the host needs no `notify-send`) saying exactly what to install or change.
- Not provided: the GNOME Shell search provider and `.mcpb`/`.skill` MIME registrations, which the `.deb` sets up system-wide.
- Building it requires network access to `downloads.claude.ai`, which enforces Anthropic's regional availability allowlist.

## Version management

Version updates are handled by **Renovate** with custom regex managers — no cron jobs needed:

- The Claude Code version in `snap/snapcraft.yaml`'s top-level `version:` field → tracked via Renovate's `github-releases` datasource against `anthropics/claude-code`
- The expected version string in `tests/smoke/claude-code/task.yaml`
- The Claude Desktop version in the `claude-desktop` part's `.deb` URL → tracked via Renovate's `deb` datasource against Anthropic's apt repository (independent of the CLI version; becomes the `desktop` component's version)

When a new upstream Claude Code version is released, Renovate auto-creates a PR updating both locations.

`version:` is the only place the version lives — both GitHub release asset URLs interpolate it via `$CRAFT_PROJECT_VERSION`. Renovate's datasources don't know binary content hashes, though, so `.github/workflows/update-checksums.yml` runs `scripts/update-checksums.py` on any PR touching `snap/snapcraft.yaml` to keep `EXPECTED_SHA256` and `EXPECTED_DEB_SHA256` in sync (see AGENTS.md for the details).

## Project structure

```
claude-snap/
├── snap/
│   ├── gui/
│   │   └── icon.png             # Claude Code's own launch-screen mascot — see AGENTS.md
│   ├── local/
│   │   ├── claude.wrapper       # Wrapper script (unsets SNAP_* env vars, AppArmor onexec, PATH)
│   │   ├── claude-desktop.wrapper # Claude Desktop wrapper (component check, onexec, sandbox fallback)
│   │   ├── claude-desktop-cowork-check.sh # Cowork prerequisite check, sourced by the wrapper
│   │   ├── claude-onexec.sh     # AppArmor onexec-arming logic, also sourced by the apparmor-onexec test
│   │   └── claude.completion    # Hand-written bash completion
│   └── snapcraft.yaml           # Snap build definition
├── scripts/
│   └── update-checksums.py      # Recomputes pinned checksums; run by update-checksums.yml, safe by hand
├── tests/
│   └── smoke/
│       ├── claude-code/task.yaml       # Install/help/version/license
│       ├── clipboard/task.yaml         # wl-copy/wl-paste on PATH
│       ├── apparmor-onexec/task.yaml   # AppArmor onexec workaround
│       └── desktop/task.yaml           # desktop component + Claude Desktop launch under Xvfb
├── .github/
│   ├── actions/
│   │   └── install-cached-snap/    # Snap caching action
│   └── workflows/
│       ├── build.yml               # CI entry point (push/PR/tag) → tasteful-crafts
│       ├── tasteful-crafts.yml     # Reusable build-test orchestrator
│       ├── snapcraft-pack.yml      # Reusable build workflow (per arch)
│       ├── spread.yml              # Reusable image-garden spread runner
│       ├── update-checksums.yml    # Auto-fixes stale checksums on PRs touching snapcraft.yaml
│       └── release.yml             # Release creation from Renovate PRs
├── renovate.json                    # Dependency update configuration (github-releases datasource)
├── spread.yaml                      # Spread test backend config
├── .image-garden.mk                 # image-garden cloud-init templates (core26)
├── .gitignore                       # Ignore built snaps and local spread/image-garden artifacts
├── AGENTS.md                        # Agent instructions for this repo
├── README.md                        # This file
└── LICENSE                          # Apache-2.0 (packaging only; Claude Code itself is proprietary)
```

## Building

```bash
# Install snapcraft
sudo snap install snapcraft --classic

# Build the snap
snapcraft pack -v

# Install locally (snap, then the desktop component)
sudo snap install --classic --dangerous ./claude-code_*.snap
sudo snap install --dangerous ./claude-code+desktop_*.comp

# Run (default app)
claude-code

# Or via the alias target (until the claude alias is granted)
claude-code.claude
```

## Testing with spread

Tests in this repository use [spread](https://github.com/snapcore/spread), the multi-machine test runner from the snap core team.

The tests install the `claude-code_*.snap` and `claude-code+desktop_*.comp` from the repository root, so build it with `snapcraft pack` first (see [Building](#building)).

```bash
sudo snap install image-garden
image-garden.spread
```

## Publishing

CI (`.github/workflows/build.yml`) only builds the snap and runs the spread integration tests — it does not publish anywhere. Publishing to the Snap Store is handled by [Launchpad's snap recipe integration](https://snapcraft.io/claude-code/builds), which builds directly from this repository.

## Contributing

See [AGENTS.md](AGENTS.md) for project-specific rules. Claude Code itself is closed source — bug reports and feature requests for the product belong at [github.com/anthropics/claude-code](https://github.com/anthropics/claude-code/issues).

## License

Apache-2.0 — see [LICENSE](LICENSE). This covers only the snap packaging files in this repository; individual files carry their own SPDX headers crediting Canonical Ltd. where substantially adapted from pi-coding-agent-snap/opencode-snap, and Alex Murray for files written for this project. Claude Code and Claude Desktop are proprietary software, all rights reserved by Anthropic PBC; see https://code.claude.com/docs/en/overview.

## See also

- [pi-coding-agent-snap](https://github.com/canonical/pi-coding-agent-snap) and [opencode-snap](https://github.com/canonical/opencode-snap) — the templates this packaging is modeled after
- [code.claude.com/docs](https://code.claude.com/docs/en/overview) — Claude Code documentation
