#!/usr/bin/env bash
export RUNTIME_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
export RUNTIME_REPO="$RUNTIME_ROOT/repo"
source /opt/ros/jazzy/setup.bash
if [[ -f "$RUNTIME_REPO/ros2_ws/install/setup.bash" ]]; then
  source "$RUNTIME_REPO/ros2_ws/install/setup.bash"
fi
if [[ -d "$RUNTIME_ROOT/config/local/rosdep" ]]; then
  source "$RUNTIME_ROOT/scripts/rosdep-env.sh"
fi
