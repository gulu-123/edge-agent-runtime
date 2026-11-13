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
e2e_script="$runtime_repo/scripts/run_industrial_e2e.sh"
if [[ -n "${RUNTIME_E2E_ORCHESTRATOR_CANCEL_MS:-}" ]]; then
  cancel_budget="$RUNTIME_E2E_ORCHESTRATOR_CANCEL_MS"
  [[ "$cancel_budget" =~ ^[1-9][0-9]{0,4}$ ]] && ((cancel_budget >= 1000 && cancel_budget <= 10000)) || {
    echo 'RUNTIME_E2E_ORCHESTRATOR_CANCEL_MS must be 1000..10000' >&2
    exit 2
  }
  python3 - "$e2e_script" "$run_dir/e2e-profile.sh" "$cancel_budget" <<'PY'
from pathlib import Path
import sys
source, destination, budget = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
text = source.read_text()
needle = 'start_direct orchestrator "$EVIDENCE/orchestrator.log" "$ORCHESTRATOR"\n'
if text.count(needle) != 1:
    raise SystemExit('Pinned E2E launch changed; refuse to guess a replacement')
replacement = needle.rstrip('\n') + f' --ros-args -p cancel_timeout_ms:={budget}\n'
destination.write_text(text.replace(needle, replacement, 1))
PY
  e2e_script="$run_dir/e2e-profile.sh"
  printf 'E2E profile: outer cancellation confirmation budget %s ms\n' "$cancel_budget"
fi
set +e
WORKSPACE="$runtime_repo/ros2_ws" SETUP_VCAN=0 ROS_DISTRO=jazzy \
  bash "$e2e_script" 2>&1 | tee "$run_dir/e2e.log"
run_status=${PIPESTATUS[0]}
set -e
if [[ -d /tmp/runtime-industrial-evidence ]]; then
  cp -a /tmp/runtime-industrial-evidence "$run_dir/evidence"
fi
if ((run_status != 0)); then
  for logfile in "$run_dir/evidence/bridge.log" "$run_dir/evidence/executor.log" \
                 "$run_dir/evidence/orchestrator.log" "$run_dir/evidence/gateway.log" \
                 "$run_dir/evidence/bridge-after-ack-timeout.log" \
                 "$run_dir/evidence/executor-after-ack-timeout.log"; do
    if [[ -f "$logfile" ]]; then
      printf '\nFailure context: %s\n' "${logfile##*/}"
      tail -n 25 "$logfile"
    fi
  done
fi
printf '\nEvidence saved to: %s\n' "$run_dir"
exit "$run_status"
