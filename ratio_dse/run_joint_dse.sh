#!/usr/bin/env bash
set -euo pipefail
if [[ $# -lt 1 || $# -gt 2 || ${1:-} == --help ]]; then
    echo "Usage: $0 new-output-directory [config.json]"
    exit 0
fi
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
output="$1"
config="${2:-$repo_root/ratio_dse/configs/dse/joint_search.json}"
[[ "$output" == /* ]] || output="$PWD/$output"
[[ "$config" == /* ]] || config="$PWD/$config"
cd -- "$repo_root"
"${RATIO_DSE_PYTHON:-python3.11}" -m ratio_dse.dse.joint_search --config "$config" --output "$output"
