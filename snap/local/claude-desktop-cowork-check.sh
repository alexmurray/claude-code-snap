# SPDX-FileCopyrightText: Alex Murray
# SPDX-License-Identifier: Apache-2.0
#
# Sourced by claude-desktop.wrapper (and tests/smoke/desktop/task.yaml).
# Sets COWORK_HINT to a human-readable description of what the host is
# missing for Claude Desktop's Cowork tab, or to the empty string if
# nothing is.
#
# Claude Desktop runs Cowork in a QEMU/KVM VM using host-provided tools —
# deliberately not bundled, see AGENTS.md. It checks for them once at
# startup, but only reports what's missing inside the Cowork tab itself
# (and logs just "status=unsupported"). This mirrors those checks, as found
# in the app's bundle, so the wrapper can say up front what to fix:
#
#   - qemu-system-<arch> on PATH
#   - UEFI firmware at fixed paths (OVMF on amd64, AAVMF on arm64)
#   - virtiofsd at /usr/libexec/virtiofsd or /usr/bin/virtiofsd, except
#     on Ubuntu 22.04 (no virtiofsd package), where the app uses its own
#   - read/write access to /dev/kvm and /dev/vhost-vsock (the latter is
#     only granted via the kvm group)
#
# Keep in sync with the app's own checks if a release changes them.

COWORK_HINT=
_cowork_pkgs=
if [ "$(uname -m)" = aarch64 ]; then
    command -v qemu-system-aarch64 >/dev/null 2>&1 || _cowork_pkgs="$_cowork_pkgs qemu-system-arm"
    [ -r /usr/share/AAVMF/AAVMF_CODE.fd ] || _cowork_pkgs="$_cowork_pkgs qemu-efi-aarch64"
else
    command -v qemu-system-x86_64 >/dev/null 2>&1 || _cowork_pkgs="$_cowork_pkgs qemu-system-x86"
    [ -r /usr/share/OVMF/OVMF_CODE_4M.fd ] || [ -r /usr/share/OVMF/OVMF_CODE.fd ] ||
        _cowork_pkgs="$_cowork_pkgs ovmf"
fi
_cowork_os=$(. /etc/os-release 2>/dev/null && echo "$ID $VERSION_ID")
case "$_cowork_os" in
    "ubuntu 22."*) ;;
    *)
        [ -r /usr/libexec/virtiofsd ] || [ -r /usr/bin/virtiofsd ] ||
            _cowork_pkgs="$_cowork_pkgs virtiofsd"
        ;;
esac
if [ -n "$_cowork_pkgs" ]; then
    COWORK_HINT="Install the tools it needs: sudo apt install${_cowork_pkgs}"
fi

_cowork_kvm=
if [ ! -e /dev/kvm ]; then
    _cowork_kvm="Turn on hardware virtualization (VT-x/AMD-V) in your firmware settings."
elif [ ! -r /dev/kvm ] || [ ! -w /dev/kvm ] ||
     { [ -e /dev/vhost-vsock ] && { [ ! -r /dev/vhost-vsock ] || [ ! -w /dev/vhost-vsock ]; }; }; then
    _cowork_kvm="Join the kvm group: sudo usermod -aG kvm \$USER, then log out and back in."
elif [ ! -e /dev/vhost-vsock ]; then
    if [ -d "/lib/modules/$(uname -r)" ]; then
        _cowork_kvm="Load the vhost_vsock module: sudo modprobe vhost_vsock"
    else
        _cowork_kvm="This kernel lacks the vhost_vsock support Cowork needs."
    fi
fi
if [ -n "$_cowork_kvm" ]; then
    COWORK_HINT="${COWORK_HINT:+$COWORK_HINT
}$_cowork_kvm"
fi
unset _cowork_pkgs _cowork_os _cowork_kvm
