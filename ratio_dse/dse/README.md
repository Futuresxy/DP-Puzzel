# DeepSeek chip and workload design-space study

This study combines the measured DP profiles from the [area model](../area_model/README.md) with the GEMM and precision contracts from the [compute model](../compute_model/README.md). The [2026-11-13 findings](../results/summaries/deepseek-dse-20261113/README.md) document the first controlled sweep and its validation boundary.

## Joint hardware × workload search

The current chip-design study treats the four cumulative precision plans as supplied scenarios. PPL and accuracy thresholds are **out of scope**; no quality record is required or used to reject a plan. This does not assert that a quantizer has validated those plans. Useful MACs stay fixed; precision distribution, native-K padding, bytes and completion time change.

The [joint-search results](../results/summaries/deepseek-dse-20261113/joint_search/README.md) contain 6,752 evaluations and show how extra baseline DPs, power allocation and bandwidth-filling policies change the chosen ratio.

```bash
bash ratio_dse/run_joint_dse.sh ratio_dse/results/my-joint-run
# Optional second argument: a replacement joint-search JSON.
python3.11 -m ratio_dse.dse.joint_search \
  --config ratio_dse/configs/dse/joint_search.json \
  --output ratio_dse/results/my-other-joint-run
```

Both commands require a fresh output directory. Python 3.11+ standard library is sufficient. The [configuration](../configs/dse/joint_search.json) combines nine measured DP profiles, 32 analytical shapes, two models, four precision plans, 4/8/16 TB/s per SM, uncapped/150 W DP budgets and same-capacity single/ping-pong buffers. Shape legality is an explicit search assumption, not array RTL validation.

```text
DP evidence + fixed baseline core-pool area
  → fixed array / bandwidth-constrained variable array → installed SMs and DP count
model config + runtime scenario → GEMM shapes → four supplied precision plans
  → native-K output tiles → power-limited active SMs → per-SM port shares
  → capacity-limited contexts → input-bank refill / RAW / compute / write timeline
  → workload-to-hardware ranking + hardware-to-migration ranking + Pareto set
```

**Construction.** `equal_array` keeps the baseline M/N; bandwidth may stall it. `bandwidth_filled` selects shapes whose maximum full-issue demand over the required formats is closest to the fixed budget for each profile; all tied orientations remain. `bandwidth_feasible` additionally allows every smaller feasible shape, to test whether filling the bandwidth is helpful. The latter two use the area model's `equal_input_bandwidth` gate. A fixed-array design can run faster even though it fails that full-rate gate: these are different construction policies, not an optimization over nested spaces. All policies retain one baseline area budget. The `1:2:4` design can grow its DP count when allowed more area per SM, while the total SM count decreases.

**Power.** The default `power_granularity: "core"` allocates complete SMs at the fixed profile clock. For the current precision, `enabled_SM = min(installed_SM, floor((cap - installed_idle_power) / (arrays_per_SM × active_increment_per_array)))`, clamped to zero. All installed DP leakage remains; disabled SMs are idle, not assumed power-gated. A nonempty GEMM with zero eligible SMs is infeasible. Active arrays may be fewer if there are fewer output tiles. The scheduler uses the maximum permitted SM count; it does not search voltage/frequency or optimize smaller runtime allocations. `"array"` retains the historical finer-grained policy. The budget is for the DP pool, not a whole-chip TDP.

**I/O.** `single_buffer` and `pingpong` explicitly schedule whole native-K rounds; they share the same total storage per array. The [round recurrence and capacity rule](../compute_model/README.md#ab-驻留和-ping-pong) retain first fill, last drain, per-context RAW and final writes. Each active array reserves an equal share of its SM's refill/write ports. Buffer-to-DP delivery has an explicitly assumed independent native-width port. Cross-request operand reuse and cross-wave prefetch are absent. Single-buffer refill may overlap feedback waiting, so it differs from historical `serial` compute+transfer totals.

| Input | Meaning |
|---|---|
| `evidence`, `baseline_topology`, `legal_shapes` | Locked DP evidence; common area/topology baseline; discrete M/N search space including baseline shape |
| `workloads`, `anchor_length`, `anchor_batch` | Registered model scenario files and the query-token/batch override; other scenario fields remain in force |
| `local_read_tb_s_per_core`, `bandwidth_scope` | Decimal TB/s at each SM's preformatted input boundary; supported scope is `per_core_local_input` |
| `power_caps_w`, `power_granularity` | `null` means uncapped; W allocated to installed DP pool; `core` or `array` |
| `io_schedules`, `operand_delivery` | `single_buffer`, `pingpong`, optional legacy `serial`; buffered modes require `native_issue_width` |
| `buffer_bytes_per_array`, `contexts` | Total input + accumulator capacity; maximum output contexts, reduced if necessary by capacity |
| `write_read_ratio` | Write-port bandwidth / read-port bandwidth; writebacks do not overlap the next wave's refill |
| `quality_policy` | Required `out_of_scope` in this chip-design entry point |

| Output | Meaning |
|---|---|
| `deployments.json` | All requested shapes, area, SM/DP counts, per-mode peaks and bandwidth-gate failures; invalid shapes are retained for audit |
| `precision_workloads.csv`, `step_moves.csv`, `excluded_work.csv` | Per-format useful work, exact migration transitions, excluded GEMM categories/precisions |
| `candidate_evaluations.csv` | Model × plan × valid deployment × bandwidth × power × buffer schedule; time, overlap, capacity, active-core maximum, area, DP power/energy, peak and effective TFLOP/s |
| `winning_operator_breakdown.csv` | Forward winners by operator family/format; allowed/active SMs and arrays, effective contexts, buffer demand and time components; join through `candidate_id` |
| `workload_to_hardware.csv` | Fixed model/plan/runtime constraints → fastest ratio and shape in each construction view; independent minimum-DP-energy winner |
| `hardware_to_migration.csv` | Fixed physical deployment/runtime constraints → fastest supplied migration plan; no quality penalty |
| `pareto.csv` | Nondominated area, modeled completion time and DP-envelope points per forward cohort; exact ties retained |
| `validation.json`, `manifest.json`, `summary.md` | Invariants, commands, input/source/output fingerprints, scope and assumptions |

`bandwidth_utilization_at_full_issue` is maximum required-mode full-rate demand / budget; it may exceed one for fixed-array designs and is not measured runtime bandwidth utilization. `local_input_port_sum_tb_s` is installed SM count × local bandwidth, not HBM bandwidth. `compute_s/read_s/write_s` are critical-lane service components; `seconds = compute_s + read_s + write_s - overlap_s`. `effective_tflops_s` uses useful modeled GEMM work and includes local waits; `per_mode_peak_tflops_s` lists mutually exclusive single-mode peaks. Peak fields for unmeasured-power modes do not imply they participated in the runtime search.

All timing is `analytical_uncalibrated`. Inputs start after packing/quantization/gather, with zero initial GEMM C and FP32 accumulation. HBM, non-GEMM operations, SRAM/interconnect power, thermal/DVFS behavior and online conversion are outside this completion boundary. Fixed per-SM peripheral area is a scenario assumption; shape-dependent bank/port/broadcast timing and area require characterization. Historical studies below retain their earlier single-array concurrency and serial-transfer assumptions.

## Reproduce

From the repository root with Python 3.11 or later.

```bash
python3.11 -m unittest discover -s ratio_dse/tests -v
python3.11 -m ratio_dse.dse.study \
  --config ratio_dse/configs/dse/deepseek_study.json \
  --output ratio_dse/results/deepseek-study
```

Figure generation uses Matplotlib from [paper/requirements.txt](../../paper/requirements.txt).

```bash
python3.11 -m ratio_dse.dse.figures \
  --run ratio_dse/results/deepseek-study \
  --output ratio_dse/results/deepseek-study-figures
```

The [study config](../configs/dse/deepseek_study.json) names the evidence, topology and workload inputs and specifies the discrete bandwidth, context, batch and DP budget probes. The first topology is used for the full cross-workload, power-cap and migration sweeps. All listed topologies run at the anchor workload. The migration sweep compares the expert target, three Grouped O-down choices, a projection/shared-FFN move and a main-attention move. The supplied figure layouts select the documented 2,048-token, batch-1 anchor and the three named formats.

## Precision migration × chip selection

The main cross-sweep compares four cumulative plans on all nine profiles at the anchor and first topology. Step 1 moves Grouped O-down and routed/shared experts to MXFP4. Step 2 also moves Q-down, Q-up, O-up and window KV projections to MXFP4. Step 3 also moves SWA/CSA QK and PV to MXFP8. Each bandwidth/DP-budget cohort ranks profiles for a fixed plan and records the runner-up margin and minimum-energy profile. The [staged figure and interpretation](../results/summaries/deepseek-dse-20261113/staged_migration/README.md) show the useful MAC mix and fastest ratios under the uncapped and 150 W cases. The [24-plan factorial study](../results/summaries/deepseek-dse-20261113/migration_selection/README.md) remains available through `--plan-set factorial`.

```bash
python3.11 -m ratio_dse.dse.migration_selection --output ratio_dse/results/deepseek-staged-migration
python3.11 -m ratio_dse.dse.migration_figure \
  --run ratio_dse/results/deepseek-staged-migration \
  --pdf paper/figures/dse_staged_precision_selection.pdf \
  --evidence ratio_dse/results/summaries/deepseek-dse-20261113/staged_migration
```

The staged run writes `step_moves.csv` with the exact operator moves and `quality_records.json` with model-specific plan IDs. Pass `--quality` with the [full-plan quality record schema](../compute_model/README.md#inputs) to attach external measurements. `quality_screened_selections.csv` retains rows whose supplied metrics pass. The main figure presents the hardware-only ranking and keeps quality unknown in the absence of records.

The staged CSVs report two latency break-even budgets against the previous step. `fixed_profile_conversion_headroom_s` compares the same hardware and `reselected_conversion_headroom_s` compares each step's fastest hardware. These are budgets for incremental serial online work over the previous plan. The DSE timings start with preformatted operands. Use measured conversion time on the critical path, then re-rank if the overhead depends on the hardware or mapping.

## Paired comparisons

| View | Fixed | Varied |
|---|---|---|
| `chip_selection` | Workload, precision plan and the scenario's area/frequency/bandwidth conditions | Nine DP profiles and three 256-DP SM organizations |
| `model_adaptation` | Workload, deployment, bandwidth and modeled power policy | Whitelisted operator-group precision choices |
| `power_cap` | Workload, plan and local bandwidth | DP-envelope allocation and candidate profile |
| Ablations | Useful work and the paired configuration | Local traffic, one vs eight feedback contexts, per-weight launch barriers, hot-expert routing, ideal within-array B broadcast, idle and activity parameters |

The native-K geometry comes from the compute model. Independent output tiles are striped across arrays with every K chain pinned to its array. Within a core, active arrays reserve equal portions of the local read and write ports. For each array the model serializes compute service and padded local ingress/egress service, then takes the longest array time. The compute phase uses output-stationary context waves and explicit RAW waits. Both data transfers and context storage have named resource assumptions. The shared-B ablation assumes ideal sharing across row groups within one TensorCore and uses the same incremental area.

The W4A8 case expands expert weights into MXFP8 before the local boundary. The W4A4 alternative assumes native MXFP4 inputs. Generic FP8/FP4 tags are explicit format proxies. Precision comparisons use preformatted local inputs and report how much serial conversion time could be added before erasing their latency benefit. The bundled experiments have unknown quality. The [GEMM model](../compute_model/README.md#建模架构与周期) documents the timing boundary and the assumptions for operand reuse and double buffering.

Dynamic energy applies the measured active-mode proxy per issued array interval and a separate idle sensitivity. Leakage applies to installed DP resources across the modeled GEMM window. The DP envelope assumes the maximum number of allocated arrays can issue in the same mode concurrently. A DP cap limits that allocation at 1 GHz. The scope covers local-memory delivery and the DP compute pool. HBM, perimeter/uncore, conversion power, board power, transient peaks and DVFS need additional evidence.

## Outputs

| Artifact | Use |
|---|---|
| `candidate_evaluations.csv` | Candidate IDs, fixed comparison variables, area, useful/issued work, local bytes, time components, DP average power/energy/envelope, quality status |
| `operator_breakdown.csv` | Anchor sums per operator family and format with shape and local intensity metrics |
| `precision_migrations.csv` | Fixed-deployment changes, reassigned MAC, latency and energy ratios, aggregate and per-row conversion break-even |
| `selection_summary.csv` / `pareto.csv` | Separate winners and Pareto sets over area, latency and DP envelope or energy |
| `bandwidth_boundaries.csv` / `robustness.csv` | Refined sampled winner changes and worst/median regret over matched cases |
| `excluded_work.csv` / `validation.json` | Residual work and full-grid invariant checks |
| `manifest.json` | Exact inputs, source hashes and output hashes |

The [project goal skill](../../.skill/goal-skill/SKILL.md) captures the repeatable comparison and evidence procedure. A physical calibration/holdout plan is part of the [findings report](../results/summaries/deepseek-dse-20261113/README.md#expand-and-validate).
