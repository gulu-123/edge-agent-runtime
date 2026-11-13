#!/usr/bin/env bash
runtime_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
export ROSDEP_SOURCE_PATH="$runtime_root/config/local/rosdep"
export ROSDISTRO_INDEX_URL="file://$runtime_root/cache/rosdistro/index-v4.yaml"
