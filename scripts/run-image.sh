#!/usr/bin/env bash
set -Eeuo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
set +u
source "$script_dir/env.sh"
set -u
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-129}"
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
exec /usr/bin/python3 "$script_dir/image_workflow.py" "$@"
