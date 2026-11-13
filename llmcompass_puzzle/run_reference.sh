#!/usr/bin/env bash
set -euo pipefail
if [[ $# == 1 && "$1" == "--help" ]]; then
    echo "Usage: bash llmcompass_puzzle/run_reference.sh NEW_OUTPUT_DIRECTORY"
    exit 0
fi
if [[ $# != 1 ]]; then
    echo "Usage: bash llmcompass_puzzle/run_reference.sh NEW_OUTPUT_DIRECTORY" >&2
    exit 2
fi
study_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
study_output="$(realpath -m "$1")"
cd "$study_root"
if [[ -e "$study_output" ]]; then
    echo "Output already exists: $study_output" >&2
    exit 2
fi
python3.11 llmcompass_puzzle/setup.py --check
mkdir -p "$study_output"
llmcompass_puzzle/.venv/bin/python -m llmcompass_puzzle.characterize --output "$study_output/area"
llmcompass_puzzle/.venv/bin/python -m llmcompass_puzzle.replay --output "$study_output/reference"
