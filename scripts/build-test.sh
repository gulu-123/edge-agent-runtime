#!/usr/bin/env bash
set -Eeuo pipefail
runtime_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
bash "$runtime_root/scripts/bootstrap.sh"
run_dir="$runtime_root/runs/$(date +%Y%m%d-%H%M%S)-build-test"
mkdir -p "$run_dir/artifacts"
set +u
source /opt/ros/jazzy/setup.bash
set -u
export CMAKE_BUILD_PARALLEL_LEVEL="${CMAKE_BUILD_PARALLEL_LEVEL:-2}"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-128}"
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
cd "$runtime_root/repo/ros2_ws"
colcon build --executor sequential --cmake-args -DBUILD_TESTING=ON \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo 2>&1 | tee "$run_dir/build.log"
set +u
source install/setup.bash
set -u
baseline="$runtime_root/repo/scripts/performance_baseline.json"
if [[ -f "$baseline" ]]; then
  mv "$baseline" "$run_dir/artifacts/performance-baseline.before-tests.json"
fi
set +e
colcon test --executor sequential --return-code-on-test-failure 2>&1 | tee "$run_dir/test.log"
test_status=${PIPESTATUS[0]}
colcon test-result --test-result-base build --verbose 2>&1 | tee "$run_dir/test-results.log"
result_status=${PIPESTATUS[0]}
set -e
if [[ -f "$baseline" ]]; then
  mv "$baseline" "$run_dir/artifacts/performance-baseline.generated-by-tests.json"
fi
if [[ -f "$run_dir/artifacts/performance-baseline.before-tests.json" ]]; then
  cp "$run_dir/artifacts/performance-baseline.before-tests.json" "$baseline"
fi
printf '\nBuild and test records: %s\n' "$run_dir"
((test_status == 0 && result_status == 0))
cd "$runtime_root/adapters_ws"
colcon build --executor sequential --cmake-args -DBUILD_TESTING=OFF \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo 2>&1 | tee "$run_dir/adapter-build.log"
