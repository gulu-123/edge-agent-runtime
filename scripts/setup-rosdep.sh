#!/usr/bin/env bash
set -Eeuo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
mkdir -p "$root/cache" "$root/config/local/rosdep"
if [[ ! -d "$root/cache/rosdistro/.git" ]]; then
  git clone --depth 1 https://github.com/ros/rosdistro.git "$root/cache/rosdistro"
fi
sed -e "s#https://raw.githubusercontent.com/ros/rosdistro/master/#file://$root/cache/rosdistro/#g" \
    -e '/^gbpdistro /d' \
    "$root/cache/rosdistro/rosdep/sources.list.d/20-default.list" \
    > "$root/config/local/rosdep/20-local.list"
source "$root/scripts/rosdep-env.sh"
rosdep update --rosdistro jazzy
