---
name: goal-skill
description: Run goal-tracked DP-Puzzel design-space research that pairs measured DP profiles with model GEMM workloads, controlled precision changes, and explicit validation.
---

Set a completion goal with the required number of quantified findings and the evidence or figures that will substantiate them. Use the active goal when one already exists. Read [the DSE procedure](../../ratio_dse/dse/README.md) and reuse its executable inputs before introducing a new model or sweep.

- Run paired comparisons. For chip selection, hold the workload and precision plan fixed. For model adaptation, hold the workload and deployment fixed. For a mapping ablation, preserve useful work and state what changed in the schedule.
- Compare matched scopes and inspect per-operator work, local bytes, and native-K requests before interpreting a ranking. Record exact candidate IDs and the operating range for each finding.
- Track power feasibility and energy as separate outputs. Identify the activity source, power window, and memory boundary. Mark quality and hardware calibration independently.
- For a broader search, start with a structured grid, refine intervals where rank or feasibility changes, and report regret over the same paired cases. Preserve validation cases outside the exploration set.
- Finish with runnable commands, figures backed by the output hashes, checked invariants, and an explicit measured-hardware validation plan for any claims that remain analytical.
