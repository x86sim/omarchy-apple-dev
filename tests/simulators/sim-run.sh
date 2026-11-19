#!/usr/bin/env bash
# Boot one x86Sim device (X86SIM_ROOT: an x86sim checkout), install and launch an app, take a
# screenshot, stop the device. UNINSTALL=1 removes the app before stopping.
#
# usage: sim-run.sh DEVICE_DIR APP BUNDLE_ID OUT.png [DIVISOR]
set -uo pipefail
dev=$1 app=$2 bid=$3 out=$4 div=${5:-2}
cd "${X86SIM_ROOT:?set X86SIM_ROOT to an x86sim checkout}"
export X86SIM_DEVICE=$PWD/$dev
name=$(basename "$dev")
log=${TMPDIR:-/tmp}/sim-$name

A64_DEVICE=$dev A64_KEEP=1 timeout 1200 cli/libexec/arm64/boot-a64.sh > "$log-boot.log" 2>&1 &
if ! timeout 900 cli/x86sim wait home 900 > "$log-wait.log" 2>&1; then
  echo "$name: no home screen"; tail -3 "$log-boot.log"
fi
# Install, retrying while the device is still starting.
installed=
for _ in 1 2 3 4 5; do
  if timeout 300 cli/x86sim install "$app" > "$log-install.log" 2>&1; then installed=1; break; fi
  grep -q "no answer" "$log-install.log" || break
  sleep 60
done
[ -n "$installed" ] || { echo "$name: install failed"; tail -3 "$log-install.log"; }
# A slow runtime (visionOS) may still be starting: retry for up to 10 minutes.
launched=
for _ in $(seq 1 10); do
  if timeout 120 cli/x86sim launch --terminate-running-process "$bid" > "$log-launch.log" 2>&1; then
    launched=1; break
  fi
  grep -q "unknown to FrontBoard" "$log-launch.log" && break
  sleep 50
done
if [ -n "$launched" ]; then
  echo "$name: launched $(tail -1 "$log-launch.log")"
else
  echo "$name: launch failed"; tail -3 "$log-launch.log"
fi
sleep 12
timeout 60 cli/x86sim screenshot "$out" "$div" > /dev/null 2>&1 && echo "$name: screenshot $out"
[ -n "${UNINSTALL:-}" ] && timeout 120 cli/x86sim uninstall "$bid" > /dev/null 2>&1
A64_DEVICE=$dev A64_STOP_ONLY=1 timeout 300 cli/libexec/arm64/boot-a64.sh > /dev/null 2>&1
echo "$name: stopped"
