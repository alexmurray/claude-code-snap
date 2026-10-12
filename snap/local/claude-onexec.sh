# SPDX-FileCopyrightText: Canonical Ltd.
# SPDX-FileCopyrightText: Alex Murray
# SPDX-License-Identifier: Apache-2.0
#
# Shared by claude.wrapper and tests/smoke/apparmor-onexec/task.yaml, so the
# onexec-arming logic has exactly one copy instead of two kept in sync only
# by a comment. Meant to be sourced (`.`), never executed directly: it only
# sets the onexec attribute on the current shell's own task and doesn't exec
# anything itself, so sourcing it is safe from any calling context.
#
# snapd gives classic snaps a complain-mode (log-only) AppArmor profile whose
# label is inherited by everything claude spawns. If a child is itself a
# snap (e.g. `juju debug-log > file`), snap-confine rejects file descriptors
# that were opened under claude's label, so redirection fails with "bad file
# descriptor" (see canonical/pi-coding-agent-snap#26, LP: #1849753). Arm
# AppArmor's onexec transition so claude, and everything it spawns, runs
# unconfined as it would outside the snap. Only act under our own
# complain-mode label; ignore any failure.
if [ -e /proc/self/attr/apparmor/current ]; then
    ATTR_DIR=/proc/self/attr/apparmor
else
    ATTR_DIR=/proc/self/attr
fi
LABEL=
{ read -r LABEL < "$ATTR_DIR/current"; } 2>/dev/null || :
case "$LABEL" in
    "snap.${SNAP_INSTANCE_NAME:-claude-code}."*" (complain)")
        { printf 'exec unconfined' > "$ATTR_DIR/exec"; } 2>/dev/null || :
        ;;
esac
unset ATTR_DIR LABEL
