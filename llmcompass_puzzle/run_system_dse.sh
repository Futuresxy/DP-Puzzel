#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "Usage: bash llmcompass_puzzle/run_system_dse.sh NEW_OUTPUT_DIRECTORY [CONFIG_JSON]" >&2
    exit 2
fi
exec llmcompass_puzzle/.venv/bin/python -m llmcompass_puzzle.system_search \
    --output "$1" --config "${2:-llmcompass_puzzle/configs/moe_system_study.json}"
