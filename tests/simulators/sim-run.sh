#!/usr/bin/env bash
# Boot one x86Sim device (X86SIM_ROOT: an x86sim checkout), install and launch an app, take a
# screenshot, stop the device. UNINSTALL=1 removes the app before stopping.
# Exits 0 only when the install and the launch succeeded and the screenshot was written.
#
# usage: sim-run.sh DEVICE_DIR APP BUNDLE_ID OUT.png [DIVISOR]
#   DEVICE_DIR: relative to X86SIM_ROOT (var/device-a64-watch) or absolute
set -uo pipefail
dev=$1 app=$2 bid=$3 out=$4 div=${5:-2}
cd "${X86SIM_ROOT:?set X86SIM_ROOT to an x86sim checkout}" || exit 1
case $dev in /*) ;; *) dev=$PWD/$dev ;; esac
export X86SIM_DEVICE=$dev
name=$(basename "$dev")
log=${TMPDIR:-/tmp}/sim-$name
rm -f "$out"
ok=1

A64_DEVICE=$dev A64_KEEP=1 timeout 1200 cli/libexec/arm64/boot-a64.sh > "$log-boot.log" 2>&1 &
boot=$!
stop() {
  [ -n "${UNINSTALL:-}" ] && timeout 120 cli/x86sim uninstall "$bid" > /dev/null 2>&1
  A64_DEVICE=$dev A64_STOP_ONLY=1 timeout 300 cli/libexec/arm64/boot-a64.sh > /dev/null 2>&1
  kill "$boot" 2>/dev/null
  wait "$boot" 2>/dev/null
  echo "$name: stopped"
}
trap stop EXIT

# The home-screen detector does not know every runtime's home screen (tvOS, visionOS):
# go on and let the install and launch retries below decide.
timeout 900 cli/x86sim wait home 900 > "$log-wait.log" 2>&1 || echo "$name: home screen not detected"

# Install, retrying while the device is still starting.
installed=
for _ in 1 2 3 4 5; do
  if timeout 300 cli/x86sim install "$app" > "$log-install.log" 2>&1; then installed=1; break; fi
  grep -q "no answer" "$log-install.log" || break
  sleep 60
done
if [ -z "$installed" ]; then
  echo "$name: install failed"; tail -3 "$log-install.log"; exit 1
fi

# A slow runtime (visionOS) may still be starting: retry for up to 10 minutes.
launched=
for _ in $(seq 1 10); do
  if timeout 120 cli/x86sim launch --terminate-running-process "$bid" > "$log-launch.log" 2>&1; then
    launched=1; break
  fi
  grep -q "unknown to FrontBoard" "$log-launch.log" && break
  sleep 50
done
if [ -z "$launched" ]; then
  echo "$name: launch failed"; tail -3 "$log-launch.log"; ok=
else
  echo "$name: launched $(tail -1 "$log-launch.log")"
  sleep 12
  if timeout 60 cli/x86sim screenshot "$out" "$div" > /dev/null 2>&1 && [ -s "$out" ]; then
    echo "$name: screenshot $out"
  else
    echo "$name: no screenshot"; ok=
  fi
fi
[ -n "$ok" ]
