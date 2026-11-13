#!/usr/bin/env bash
set -Eeuo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
source /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 24.04 ]] || { echo 'Requires Ubuntu 24.04' >&2; exit 2; }
[[ -f /opt/ros/jazzy/setup.bash ]] || { echo 'Install ROS 2 Jazzy first' >&2; exit 2; }
bash "$root/scripts/bootstrap.sh"
sudo apt-get update
sudo apt-get install --no-remove -y --no-install-recommends \
  build-essential cmake git can-utils iproute2 kmod libgrpc++-dev libprotobuf-dev \
  libprotoc-dev protobuf-compiler protobuf-compiler-grpc libsqlite3-dev libopencv-dev \
  pkg-config python3-opencv python3-yaml python3-colcon-common-extensions python3-rosdep \
  ros-jazzy-behaviortree-cpp
bash "$root/scripts/setup-rosdep.sh"
set +u
source /opt/ros/jazzy/setup.bash
source "$root/scripts/rosdep-env.sh"
set -u
rosdep install --from-paths "$root/repo/ros2_ws/src" --ignore-src --rosdistro jazzy \
  --skip-keys 'libgrpc protobuf-dev protobuf-compiler-grpc libopencv-dev libsqlite3-dev' -y
