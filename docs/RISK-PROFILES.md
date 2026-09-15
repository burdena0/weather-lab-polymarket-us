# Risk controls for the three LLM strategies

Click **Reliable**, **Balanced**, or **Risky** in each model's dashboard row. The selected button saves immediately and applies to the next new run. The row also labels the profile of its last completed run, so changing a selection cannot relabel old results. CLI users set `risk_profile` in their configuration JSON. Balanced is the default.

These are deterministic research presets, not empirically validated reliability ratings. They control how a forecast becomes a paper order, not the model's factual evidence or output probability. Model-reported confidence and uncertainty intervals are uncalibrated until evaluated out of sample.

| Parameter | Reliable | Balanced | Risky |
|---|---:|---:|---:|
| Minimum edge after stress costs | 6 percentage points | 3 points | 1 point |
| Minimum reported confidence | 0.70 | 0.50 | 0.30 |
| Maximum probability interval width | 0.25 | 0.40 | 0.65 |
| Fractional Kelly multiplier | 0.10 | 0.25 | 0.50 |
| Maximum station-day exposure at cost | $2 | $5 | $5 |
| Entry probability | Conservative interval bound | Conservative interval bound | Half bound, half point estimate |

All settings retain the $40 reserve, $5 position limit, 5-share order sizing cap, delayed observed-depth fills, evidence timestamps, fee stress, model abstention and API spending limits. Reliable's $2 station-day limit is rechecked at fill time, including simultaneous pending entries. Exit rules are unchanged. Adaptive model routing and escalation remain separate from this risk choice; a difficult forecast can still receive a stronger model at any risk setting. PolySwarm disagreement and explicit abstention still block entry. Adaptive inference also retains its final interval-width gate of 0.40 after escalation, even under Risky. Changing a button during a background session affects the next session; its running configuration stays frozen.

The selected profile and its resolved parameters are stored in every forecast audit; the run manifest and config hash identify the preset. For paper comparisons, predeclare profiles and compare strategies under the same profile first. A 3-model by 3-profile factorial comparison is a separate nine-cell experiment: account for multiple comparisons and do not select a winner using the held-out test period.
