#!/usr/bin/env bash
set -Eeuo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
set +u
source "$script_dir/env.sh"
set -u
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-130}"
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
export RCUTILS_LOGGING_USE_STDOUT=0
exec /usr/bin/python3 "$script_dir/live_workflow.py" "$@"
