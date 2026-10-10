# Ranked recommendations and KPIs

**These are provisional, assumption-based investigation options. Verified recommendation coverage is 0.0%. No operational assignment is approved. The source shipment-date anomaly remains unresolved.**

## Ranking controls

Speed priority is 50%; profit priority is 50%. Top N is 3 per product. Current profit policy: `nonnegative_base`.

Speed utility = modeled dispatch reduction (%) / 10, clipped to [-1,1]. Profit utility = modeled contribution change / max(5% of absolute current modeled contribution, 100 source monetary units), clipped to [-1,1]. Score = speed priority × speed utility + profit priority × profit utility − 0.1 × (1 − profit stability / 100). The reference scales and penalty are explicit project heuristics, editable in `datasets/reference/recommendation_policy.json`; they are not learned coefficients.

Default profit protection blocks alternatives with negative base-case modeled contribution changes. `strict_all_cases` requires nonnegative changes in every tested case, and `tradeoff` explicitly permits base-case losses for exploration. Supplied capacity and compatibility restrictions are applied before ranking. Unknown constraints permit investigation only and do not confer feasibility. Baseline scores are zero. A move must have positive utility relative to keeping the current assignment.

Ranking is per product. Top-N alternatives are independent comparison options, not a simultaneously feasible allocation. The provisional portfolio considers products in descending best score, rechecks remaining receiving capacity, and selects one eligible option each. It conservatively does not reuse released origin capacity. This greedy procedure is not a global optimization algorithm.

## KPI definitions and results

| KPI | Definition | Current result |
|---|---|---:|
| Modeled lead time reduction (%) | 100 × sum(mapped units × modeled dispatch days saved) / sum(mapped units × current modeled dispatch days), across selected product decisions including keep-current | 4.06 |
| Profit impact stability (%) | Share of aligned joint sensitivity cases where the sum of selected reassignment contribution changes is nonnegative | 66.67 |
| Scenario confidence score (0–100) | Mapped-unit-weighted evidence readiness of proposed moves; each scenario uses the minimum of verified-date coverage, observed-origin coverage, alternative-outcome support, verified capacity, verified compatibility and calibrated nonsimulated estimate availability | 0.00 |
| Recommendation coverage (%) | Products with a selected provisional reassignment / all assessed products × 100 | 33.33 |
| Verified recommendation coverage (%) | Products with evidence-supported selected reassignment / all assessed products × 100 | 0.00 |

The lead-time KPI is a hypothetical dispatch allowance, not measured shipping performance or delivery time. Profit stability is a fraction of deliberately chosen grid cases, not a real-world probability. Common sensitivity shocks are summed jointly across moves; product stability percentages are not averaged. Confidence is an evidence-readiness gate, not a probabilistic prediction. It is zero because required evidence and calibrated operational estimates are absent. No-move portfolios report stability and confidence as not applicable, rather than presenting unchanged baselines as reliable reassignment gains.

Coverage reports actual proposed moves; products kept at their current factory do not inflate it. All 15 products are assessed; 5 are proposed for investigation and 10 retain their current assignment. Products without an eligible option: 0. Geographic estimates cover mapped demand only, while capacity screens use whole-product Source Units including unmapped demand.

Base modeled portfolio contribution change: 977.68 source monetary units over the sample replay. Worst/best joint tested changes: -4,090.69 / 4,066.00. These are not annual savings or statistical confidence bounds.

Under the default neutral factory cost assumptions and base-case profit protection, the same five chocolate-product moves remain selected at all five exported priority profiles. The slider still changes scores and ordering of comparison options; it does not manufacture different assignments when the same options dominate. Other cost assumptions, constraints or explicitly chosen tradeoff policies can change selections.

## Provisional portfolio

| Product Name | Current Factory | Selected Factory | Decision | Modeled Dispatch Lead Reduction Pct | Modeled Contribution Change | Scenario Confidence Score |
| --- | --- | --- | --- | --- | --- | --- |
| Wonka Bar - Nutty Crunch Surprise | Lot's O' Nuts | Secret Factory | Investigate provisional reassignment | 5.264 | 245.794 | 0.000 |
| Wonka Bar - Fudge Mallows | Lot's O' Nuts | Secret Factory | Investigate provisional reassignment | 5.012 | 232.866 | 0.000 |
| Wonka Bar - Scrumdiddlyumptious | Lot's O' Nuts | Secret Factory | Investigate provisional reassignment | 5.058 | 263.664 | 0.000 |
| Wonka Bar - Triple Dazzle Caramel | Wicked Chocy's | Secret Factory | Investigate provisional reassignment | 3.124 | 125.368 | 0.000 |
| Wonka Bar - Milk Chocolate | Wicked Chocy's | Secret Factory | Investigate provisional reassignment | 2.802 | 109.991 | 0.000 |
| Fizzy Lifting Drinks | Sugar Shack | Sugar Shack | Keep current assignment | 0.000 | 0.000 | 0.000 |
| Wonka Gum | Secret Factory | Secret Factory | Keep current assignment | 0.000 | 0.000 | 0.000 |
| Kazookles | The Other Factory | The Other Factory | Keep current assignment | 0.000 | 0.000 | 0.000 |
| Lickable Wallpaper | Secret Factory | Secret Factory | Keep current assignment | 0.000 | 0.000 | 0.000 |
| Everlasting Gobstopper | Secret Factory | Secret Factory | Keep current assignment | 0.000 | 0.000 | 0.000 |
| Fun Dip | Sugar Shack | Sugar Shack | Keep current assignment | 0.000 | 0.000 | 0.000 |
| Hair Toffee | The Other Factory | The Other Factory | Keep current assignment | 0.000 | 0.000 | 0.000 |
| Laffy Taffy | Sugar Shack | Sugar Shack | Keep current assignment | 0.000 | 0.000 | 0.000 |
| Nerds | Sugar Shack | Sugar Shack | Keep current assignment | 0.000 | 0.000 | 0.000 |
| SweeTARTS | Sugar Shack | Sugar Shack | Keep current assignment | 0.000 | 0.000 | 0.000 |

All alternative factory–product combinations remain historically unsupported. Verify real shipment origins, dates, factory preparation times, costs, product compatibility and capacity before implementation. A positive model score or base-case gain does not remove uncertainty.

## Capacity and compatibility

`datasets/reference/operational_constraints.json` stores additional capacity in production units over the entire sample replay and compatible Product IDs. Null means unknown; capacity zero and compatibility [] are binding restrictions. Capacity and compatibility supplied without verification are still applied as provisional limits. Verification flags require a source reference and matching horizon. Current inputs are unknown, so no capacity or capability has been invented.

| Factory | Additional Capacity Before | Proposed Incoming Units | Reported Released Units Not Reused | Additional Capacity Remaining | Capacity Verified | Capacity Status |
| --- | --- | --- | --- | --- | --- | --- |
| Lot's O' Nuts | None | 0 | 21412 | None | False | unknown |
| Wicked Chocy's | None | 0 | 15863 | None | False | unknown |
| Sugar Shack | None | 0 | 0 | None | False | unknown |
| Secret Factory | None | 37275 | 0 | None | False | unknown |
| The Other Factory | None | 0 | 0 | None | False | unknown |

The ledger sums incoming moves at each receiving factory; per-product capacity checks alone are insufficient. Released origin units are reported but not reused in the conservative single pass. Missing or contradicted restrictions can leave a product without any eligible option; this is exposed, not silently replaced with zero gains.

## Reproduce

```powershell
python analysis/rank_recommendations.py --speed-priority 0.5 --top-n 3
python analysis/rank_recommendations.py --speed-priority 1 --profit-policy tradeoff
python analysis/rank_recommendations.py --profit-policy strict_all_cases
```

Optional `--constraints path/to/constraints.json` uses a supplied constraint file. The pure ranking and KPI functions support the dashboard slider. Exports include all ranked options, top-N investigation candidates, selected portfolio, capacity ledger, joint sensitivity cases, KPI JSON, five priority profiles and compact preview data. Source estimates and logistics assumptions are documented in [the scenario report](../scenario_simulator/scenario_simulator_report.md). Dependency setup is in the project README.
