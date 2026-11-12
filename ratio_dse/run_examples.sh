#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 [new-output-directory]"
}

if [[ ${1:-} == --help || ${1:-} == -h ]]; then
    usage
    exit 0
fi
if [[ $# -gt 1 ]]; then
    usage >&2
    exit 2
fi

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${RATIO_DSE_PYTHON:-python3.11}"
if [[ $# -eq 1 ]]; then
    output="$1"
    if [[ "$output" != /* ]]; then
        output="$PWD/$output"
    fi
    mkdir -p -- "$(dirname -- "$output")"
    mkdir -- "$output"
else
    output="$(mktemp -d "$repo_root/ratio_dse/results/example.XXXXXX")"
fi

cd -- "$repo_root"
area_config="ratio_dse/configs/area"
compute_config="ratio_dse/configs/compute"

for scenario in equal_array equal_input_bandwidth sm_1x16x16 sm_4x16x4 sm_4x32x2; do
    "$python_bin" -m ratio_dse.area_model \
        --evidence "$area_config/dp_n12_20261112.lock.json" \
        --scenario "$area_config/$scenario.json" \
        --output "$output/area/$scenario"
done

"$python_bin" -m ratio_dse.compute_model \
    --scenario "$compute_config/v41_prefill.json" \
    --plan "$compute_config/adapter_plan.json" \
    --plan "$compute_config/grouped_o_down_fp8.json" \
    --area-run "$output/area/equal_array" \
    --array-model "$compute_config/serial_local_array.json" \
    --output "$output/compute/v41"
"$python_bin" -m ratio_dse.compute_model \
    --scenario "$compute_config/v4_prefill.json" \
    --output "$output/compute/v4"
"$python_bin" -m ratio_dse.compute_model \
    --workload "$compute_config/synthetic_gemm.json" \
    --plan "$compute_config/adapter_plan.json" \
    --plan "$compute_config/synthetic_gemm_fp8.json" \
    --area-run "$output/area/equal_array" \
    --array-model "$compute_config/serial_local_array.json" \
    --output "$output/compute/synthetic_gemm"

echo "$output"
