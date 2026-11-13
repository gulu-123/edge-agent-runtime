#!/usr/bin/env bash
set -Eeuo pipefail
runtime_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
runtime_repo="${RUNTIME_REPO:-$runtime_root/repo}"
[[ -f "$runtime_repo/ros2_ws/install/setup.bash" ]] || {
  echo "Build the ROS workspace first: $runtime_repo/ros2_ws" >&2
  exit 2
}
if ! ip link show vcan0 >/dev/null 2>&1; then
  bash "$runtime_repo/scripts/setup_vcan.sh" vcan0
fi
run_dir="$runtime_root/runs/$(date +%Y%m%d-%H%M%S)-e2e"
mkdir -p "$run_dir"
set +e
WORKSPACE="$runtime_repo/ros2_ws" SETUP_VCAN=0 ROS_DISTRO=jazzy \
  bash "$runtime_repo/scripts/run_industrial_e2e.sh" 2>&1 | tee "$run_dir/e2e.log"
run_status=${PIPESTATUS[0]}
set -e
if [[ -d /tmp/runtime-industrial-evidence ]]; then
  cp -a /tmp/runtime-industrial-evidence "$run_dir/evidence"
fi
printf '\nEvidence saved to: %s\n' "$run_dir"
exit "$run_status"
