#!/usr/bin/env bash
set -Eeuo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
readarray -t upstream < <(python3 - "$root/config/upstream.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
print(data['repository'])
print(data['commit'])
PY
)
if [[ ! -d "$root/repo" ]]; then
  git clone --no-checkout "${upstream[0]}" "$root/repo"
  git -C "$root/repo" checkout --detach "${upstream[1]}"
fi
[[ -d "$root/repo/.git" ]] || { echo 'repo/ is not a Git checkout' >&2; exit 2; }
[[ "$(git -C "$root/repo" rev-parse HEAD)" == "${upstream[1]}" ]] || {
  echo 'repo/ differs from config/upstream.json; preserve local work and resolve manually.' >&2
  exit 2
}
printf 'Pinned upstream ready: %s\n' "${upstream[1]}"
