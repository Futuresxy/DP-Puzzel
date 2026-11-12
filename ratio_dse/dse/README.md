# DeepSeek chip and workload design-space study

This study combines the measured DP profiles from the [area model](../area_model/README.md) with the GEMM and precision contracts from the [compute model](../compute_model/README.md). The [2026-11-13 findings](../results/summaries/deepseek-dse-20261113/README.md) document the first controlled sweep and its validation boundary.

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

The cross-sweep evaluates all 24 existing precision plans on all nine profiles at the anchor and first topology. Each bandwidth/DP-budget cohort ranks profiles for a fixed plan and records the runner-up margin and minimum-energy profile. The [combined figure and interpretation](../results/summaries/deepseek-dse-20261113/migration_selection/README.md) show the useful MAC mix and six representative plans under the uncapped and 150 W cases.

```bash
python3.11 -m ratio_dse.dse.migration_selection --output ratio_dse/results/deepseek-migration-selection
python3.11 -m ratio_dse.dse.migration_figure \
  --run ratio_dse/results/deepseek-migration-selection \
  --pdf paper/figures/dse_precision_selection.pdf \
  --evidence ratio_dse/results/summaries/deepseek-dse-20261113/migration_selection
```

## Paired comparisons

| View | Fixed | Varied |
|---|---|---|
| `chip_selection` | Workload, precision plan and the scenario's area/frequency/bandwidth conditions | Nine DP profiles and three 256-DP SM organizations |
| `model_adaptation` | Workload, deployment, bandwidth and modeled power policy | Whitelisted operator-group precision choices |
| `power_cap` | Workload, plan and local bandwidth | DP-envelope allocation and candidate profile |
| Ablations | Useful work and the paired configuration | Local traffic, one vs eight feedback contexts, per-weight launch barriers, hot-expert routing, ideal within-array B broadcast, idle and activity parameters |

The native-K geometry comes from the compute model. Independent output tiles are striped across arrays with every K chain pinned to its array. Within a core, active arrays reserve equal portions of the local read and write ports. For each array the model serializes compute service and padded local ingress/egress service, then takes the longest array time. The compute phase uses output-stationary context waves and explicit RAW waits. Both data transfers and context storage have named resource assumptions. The shared-B ablation assumes ideal sharing across row groups within one TensorCore and uses the same incremental area.

The W4A8 case expands expert weights into MXFP8 before the local boundary. The W4A4 alternative assumes native MXFP4 inputs. Generic FP8/FP4 tags are explicit format proxies. Precision comparisons use preformatted local inputs and report how much serial conversion time could be added before erasing their latency benefit. All plans in this run have unknown quality.

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
