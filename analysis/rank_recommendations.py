"""Provisional speed/profit rankings, constraints and explicitly defined KPIs.

Run: python analysis/rank_recommendations.py --speed-priority 0.5 --top-n 3
Policies: nonnegative_base (default), strict_all_cases, tradeoff.
Pure build_rankings() and portfolio_kpis() functions support dashboard integration.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "recommendations"
DEFAULT_CONSTRAINTS = ROOT / "datasets" / "reference" / "operational_constraints.json"
POLICY_PATH = ROOT / "datasets" / "reference" / "recommendation_policy.json"


def truth(value):
    return str(value).lower() == "true"


def number(value):
    return None if pd.isna(value) else float(value)


def validate_constraints(constraints, scenarios):
    if constraints.get("scope") != "sample_replay_2021_2024":
        raise ValueError("Constraint capacity horizon must match sample_replay_2021_2024")
    factory_names = set(scenarios["Candidate Factory"])
    product_ids = set(scenarios["Product ID"])
    for name in factory_names:
        if name not in constraints["factories"]:
            raise ValueError(f"Missing factory constraint record: {name}")
        record = constraints["factories"][name]
        capacity = record["additional_capacity_units"]
        if capacity is not None and (not np.isfinite(capacity) or capacity < 0 or int(capacity) != capacity):
            raise ValueError("Additional capacity must be a nonnegative integer or null")
        compatible = record["compatible_product_ids"]
        if compatible is not None and (not isinstance(compatible, list) or not all(isinstance(value, str) for value in compatible)):
            raise ValueError("Compatibility must be a list of Product IDs or null")
        for flag, value in [("capacity_verified", capacity), ("compatibility_verified", compatible)]:
            if not isinstance(record[flag], bool):
                raise ValueError(f"{flag} must be Boolean")
            if record[flag] and (value is None or not record.get("source_reference")):
                raise ValueError("Verified constraints require a value and a documented source_reference")


def build_rankings(scenarios, sensitivity, constraints, policy, speed_priority=.5, top_n=3, profit_policy="nonnegative_base"):
    if not 0 <= speed_priority <= 1 or not np.isfinite(speed_priority):
        raise ValueError("Speed priority must be between 0 and 1")
    if top_n < 1 or int(top_n) != top_n:
        raise ValueError("top_n must be a positive integer")
    if profit_policy not in {"nonnegative_base", "strict_all_cases", "tradeoff"}:
        raise ValueError("Unknown profit policy")
    validate_constraints(constraints, scenarios)
    scored = scenarios.copy()
    if not scored["Scenario ID"].is_unique:
        raise ValueError("Scenario IDs must be unique")
    if not sensitivity.empty and sensitivity.duplicated(["Scenario ID", "Case"]).any():
        raise ValueError("Duplicate scenario/case sensitivity observations")
    stability = sensitivity.groupby("Scenario ID")["Modeled Contribution Change"].agg(
        lambda values: 100 * (values >= -1e-9).mean()) if not sensitivity.empty else pd.Series(dtype=float)
    scored["Profit Impact Stability Pct"] = scored["Scenario ID"].map(stability)
    scored["Speed Utility"] = (scored["Modeled Dispatch Lead Reduction Pct"] / policy["speed_reference_reduction_pct"]).clip(-1, 1)
    scored["Profit Utility Scale"] = np.maximum(scored["Current Modeled Contribution"].abs() * policy["profit_reference_change_pct"] / 100,
                                               policy["profit_scale_floor_source_units"])
    scored["Profit Utility"] = (scored["Modeled Contribution Change"] / scored["Profit Utility Scale"]).clip(-1, 1)
    scored["Risk Penalty"] = policy["stability_penalty_weight"] * (1 - scored["Profit Impact Stability Pct"] / 100)
    scored["Ranking Score"] = speed_priority * scored["Speed Utility"] + (1 - speed_priority) * scored["Profit Utility"] - scored["Risk Penalty"]
    scored["Speed Priority"] = speed_priority
    scored["Profit Priority"] = 1 - speed_priority
    scored["Profit Policy"] = profit_policy
    constraints_met, compatible_flags, capacity_flags, confidence = [], [], [], []
    reasons = []
    for row in scored.to_dict(orient="records"):
        record = constraints["factories"][row["Candidate Factory"]]
        is_current = truth(row["Is Current Assignment"])
        required = 0 if is_current else row["Source Units"]
        capacity = record["additional_capacity_units"]
        capacity_met = capacity is None or required <= capacity
        allowed = record["compatible_product_ids"]
        compatible = allowed is None or row["Product ID"] in allowed
        capacity_flags.append("unknown" if capacity is None else "verified_met" if capacity_met and record["capacity_verified"] else "supplied_unverified_met" if capacity_met else "blocked_insufficient_capacity")
        compatible_flags.append("unknown" if allowed is None else "verified_compatible" if compatible and record["compatibility_verified"] else "supplied_unverified_compatible" if compatible else "blocked_incompatible_product")
        constraints_met.append(capacity_met and compatible)
        issues = []
        if not capacity_met:
            issues.append("known additional capacity insufficient for whole-product demand")
        if not compatible:
            issues.append("product excluded by supplied compatibility list")
        reasons.append("; ".join(issues))
        mapped_records = max(float(row["Mapped Records"]), 1.)
        source_records = max(float(row["Source Records"]), 1.)
        components = [min(1., float(row["Verified Lead Time Records"]) / mapped_records),
                      min(1., float(row["Observed Factory Origin Records"]) / source_records),
                      float(truth(row["Historical Alternative Outcome Evidence"])),
                      float(capacity is not None and record["capacity_verified"]),
                      float(allowed is not None and record["compatibility_verified"]),
                      float(truth(row.get("Calibrated Estimate Available", False)) and not truth(row["Is Simulated Estimate"]))]
        confidence.append(100 * min(components))
    scored["Capacity Constraint Status"] = capacity_flags
    scored["Compatibility Constraint Status"] = compatible_flags
    scored["Known Constraints Satisfied"] = constraints_met
    scored["Constraint Block Reasons"] = reasons
    scored["Scenario Confidence Score"] = confidence
    scored["Confidence Is A Probability"] = False
    scored["Profit Policy Satisfied"] = True
    if profit_policy == "nonnegative_base":
        scored["Profit Policy Satisfied"] = scored["Modeled Contribution Change"] >= -1e-9
    elif profit_policy == "strict_all_cases":
        scored["Profit Policy Satisfied"] = scored["Sensitivity Min Contribution Change"] >= -1e-9
    scored["Investigation Eligible"] = scored["Known Constraints Satisfied"] & scored["Profit Policy Satisfied"] & scored["Estimate Status"].eq("assumption_based") & scored["Ranking Score"].notna()
    scored["Operationally Supported"] = scored["Investigation Eligible"] & scored["Scenario Confidence Score"].ge(100)
    scored = scored.sort_values(["Product ID", "Investigation Eligible", "Ranking Score", "Is Current Assignment", "Modeled Contribution Change", "Candidate Factory"],
                                ascending=[True, False, False, False, False, True]).reset_index(drop=True)
    scored["Rank Within Product"] = np.nan
    mask = scored["Investigation Eligible"]
    scored.loc[mask, "Rank Within Product"] = scored.loc[mask].groupby("Product ID").cumcount() + 1
    candidates = scored[scored["Investigation Eligible"] & ~scored["Is Current Assignment"].map(truth) & scored["Ranking Score"].gt(1e-12)].copy()
    candidates["Reassignment Rank Within Product"] = candidates.groupby("Product ID").cumcount() + 1
    top = candidates[candidates["Reassignment Rank Within Product"] <= top_n].copy()
    top["Recommendation Status"] = np.where(top["Operationally Supported"], "evidence_supported_candidate", "provisional_investigation_only")

    # Conservative capacity-aware selection: never count alternatives as independent free choices.
    remaining = {factory: record["additional_capacity_units"] for factory, record in constraints["factories"].items()}
    incoming = {factory: 0 for factory in remaining}
    released = {factory: 0 for factory in remaining}
    ordering = scored[scored["Investigation Eligible"]].groupby("Product ID")["Ranking Score"].max().to_dict()
    product_order = sorted(scored["Product ID"].unique(), key=lambda product: (-ordering.get(product, -np.inf), product))
    selected, portfolio_rows = [], []
    for product_id in product_order:
        options = scored[scored["Product ID"].eq(product_id) & scored["Investigation Eligible"]]
        chosen = None
        for index, row in options.iterrows():
            candidate = row["Candidate Factory"]
            is_current = truth(row["Is Current Assignment"])
            required = 0 if is_current else int(row["Source Units"])
            if remaining[candidate] is not None and required > remaining[candidate]:
                continue
            # A move must beat the existing assignment; current score is exactly zero.
            if not is_current and row["Ranking Score"] <= 1e-12:
                continue
            chosen = row
            if not is_current:
                incoming[candidate] += required
                released[row["Current Factory"]] += required
                if remaining[candidate] is not None:
                    remaining[candidate] -= required
            selected.append(row.to_dict())
            break
        base = scored[scored["Product ID"].eq(product_id)].iloc[0]
        portfolio_rows.append({"Product ID": product_id, "Product Name": base["Product Name"],
                               "Selected Scenario ID": chosen["Scenario ID"] if chosen is not None else None,
                               "Current Factory": base["Current Factory"], "Selected Factory": chosen["Candidate Factory"] if chosen is not None else None,
                               "Decision": "No eligible option" if chosen is None else "Keep current assignment" if truth(chosen["Is Current Assignment"]) else "Investigate provisional reassignment",
                               "Operationally Supported": bool(chosen["Operationally Supported"]) if chosen is not None else False,
                               "Ranking Score": number(chosen["Ranking Score"]) if chosen is not None else None,
                               "Capacity Rechecked Jointly": True})
    selected_rows = pd.DataFrame(selected, columns=scored.columns)
    ledger = pd.DataFrame([{"Factory": factory, "Additional Capacity Before": constraints["factories"][factory]["additional_capacity_units"],
                           "Proposed Incoming Units": incoming[factory], "Reported Released Units Not Reused": released[factory],
                           "Additional Capacity Remaining": remaining[factory],
                           "Capacity Verified": constraints["factories"][factory]["capacity_verified"],
                           "Capacity Status": "unknown" if remaining[factory] is None else "within_supplied_limit"}
                          for factory in remaining])
    return {"ranked_options": scored, "top_reassignment_candidates": top, "selected_rows": selected_rows,
            "portfolio": pd.DataFrame(portfolio_rows), "capacity_ledger": ledger,
            "settings": {"speed_priority": speed_priority, "profit_priority": 1 - speed_priority, "top_n": top_n, "profit_policy": profit_policy}}


def portfolio_kpis(result, sensitivity):
    chosen, portfolio = result["selected_rows"], result["portfolio"]
    total_products = len(portfolio)
    moves = chosen[~chosen["Is Current Assignment"].map(truth)].copy()
    if len(chosen):
        denominator = (chosen["Mapped Units"] * chosen["Current Modeled Dispatch Lead Days"]).sum()
        numerator = (chosen["Mapped Units"] * chosen["Modeled Dispatch Lead Reduction Days"]).sum()
        lead_reduction = 100 * numerator / denominator if denominator > 0 else None
    else:
        lead_reduction = None
    joint = pd.DataFrame(columns=["Case", "Portfolio Contribution Change"])
    stability, confidence, worst, best = None, None, None, None
    if len(moves):
        relevant = sensitivity[sensitivity["Scenario ID"].isin(moves["Scenario ID"])]
        counts = relevant.groupby("Scenario ID").size()
        expected = moves.set_index("Scenario ID")["Sensitivity Case Count"]
        if not all(counts.get(scenario_id, 0) == count for scenario_id, count in expected.items()):
            raise ValueError("Selected moves have missing sensitivity cases")
        factor_fields = ["Distance Rate Multiplier", "Alternative Manufacturing Multiplier", "Setup Cost Multiplier", "Dispatch Buffer Multiplier"]
        if set(factor_fields).issubset(relevant.columns) and relevant.groupby("Case")[factor_fields].nunique().gt(1).any().any():
            raise ValueError("Sensitivity case identifiers do not align common assumption shocks")
        complete = relevant.groupby("Case")["Scenario ID"].nunique().eq(len(moves))
        if not complete.all() or relevant["Scenario ID"].nunique() != len(moves):
            raise ValueError("All selected moves need complete aligned sensitivity cases")
        joint = relevant.groupby("Case", as_index=False)["Modeled Contribution Change"].sum().rename(columns={"Modeled Contribution Change": "Portfolio Contribution Change"})
        stability = float(100 * joint["Portfolio Contribution Change"].ge(-1e-9).mean())
        worst, best = float(joint["Portfolio Contribution Change"].min()), float(joint["Portfolio Contribution Change"].max())
        confidence = float(np.average(moves["Scenario Confidence Score"], weights=moves["Mapped Units"]))
    kpis = {"modeled_lead_time_reduction_pct": float(lead_reduction) if lead_reduction is not None else None,
            "profit_impact_stability_pct": stability, "scenario_confidence_score": confidence,
            "recommendation_coverage_pct": 100 * len(moves) / total_products if total_products else None,
            "verified_recommendation_coverage_pct": 100 * moves["Operationally Supported"].sum() / total_products if total_products else None,
            "evaluated_product_coverage_pct": 100 * len(chosen) / total_products if total_products else None,
            "total_products": total_products, "proposed_reassignments": len(moves), "keep_current_products": int(chosen["Is Current Assignment"].map(truth).sum()),
            "products_without_eligible_option": total_products - len(chosen),
            "base_modeled_contribution_change": float(moves["Modeled Contribution Change"].sum()) if len(moves) else 0.,
            "sensitivity_min_portfolio_contribution_change": worst, "sensitivity_max_portfolio_contribution_change": best,
            "joint_sensitivity_cases": len(joint), "unverified_dispatch_dates": True,
            "profit_stability_is_probability": False, "confidence_is_probability": False,
            "operational_recommendations_approved": False, "settings": result["settings"]}
    return kpis, joint


def markdown_table(frame):
    view = frame.copy()
    for field in view.columns:
        if pd.api.types.is_float_dtype(view[field]):
            view[field] = view[field].map(lambda value: "unavailable" if pd.isna(value) else f"{value:,.3f}")
    return "\n".join(["| " + " | ".join(view.columns) + " |", "| " + " | ".join(["---"] * len(view.columns)) + " |"] +
                     ["| " + " | ".join(map(str, row)) + " |" for row in view.itertuples(index=False, name=None)])


def format_kpi(value, unavailable="not applicable"):
    return unavailable if value is None else f"{value:,.2f}"


def preview_payload(result, sensitivity, constraints, policy):
    records = []
    for row in result["ranked_options"].to_dict(orient="records"):
        cases = sensitivity[sensitivity["Scenario ID"].eq(row["Scenario ID"])].sort_values("Case")
        records.append({"id": row["Scenario ID"], "pid": row["Product ID"], "name": row["Product Name"],
                        "factory": row["Candidate Factory"], "current": row["Current Factory"], "baseline": truth(row["Is Current Assignment"]),
                        "speed": number(row["Speed Utility"]), "profit": number(row["Profit Utility"]), "penalty": number(row["Risk Penalty"]),
                        "eligible": bool(row["Investigation Eligible"]), "confidence": number(row["Scenario Confidence Score"]),
                        "stability": number(row["Profit Impact Stability Pct"]), "mappedUnits": number(row["Mapped Units"]),
                        "units": number(row["Source Units"]), "currentLead": number(row["Current Modeled Dispatch Lead Days"]),
                        "gainDays": number(row["Modeled Dispatch Lead Reduction Days"]), "profitChange": number(row["Modeled Contribution Change"]),
                        "capacityStatus": row["Capacity Constraint Status"], "compatibilityStatus": row["Compatibility Constraint Status"],
                        "caseChanges": [round(float(value), 10) for value in cases["Modeled Contribution Change"]]})
    return {"scenarios": records, "capacities": {name: record["additional_capacity_units"] for name, record in constraints["factories"].items()},
            "defaultPriority": result["settings"]["speed_priority"], "profitPolicy": result["settings"]["profit_policy"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speed-priority", type=float, default=.5)
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--profit-policy", choices=["nonnegative_base", "strict_all_cases", "tradeoff"], default="nonnegative_base")
    parser.add_argument("--constraints", type=Path, default=DEFAULT_CONSTRAINTS)
    args = parser.parse_args()
    source = ROOT / "reports" / "scenario_simulator"
    scenarios, sensitivity = pd.read_csv(source / "scenarios.csv"), pd.read_csv(source / "sensitivity.csv")
    constraints = json.loads(args.constraints.read_text())
    policy = json.loads(POLICY_PATH.read_text())
    result = build_rankings(scenarios, sensitivity, constraints, policy, args.speed_priority, args.top_n, args.profit_policy)
    kpis, joint = portfolio_kpis(result, sensitivity)
    folder = OUT if args.speed_priority == .5 and args.profit_policy == "nonnegative_base" and args.constraints == DEFAULT_CONSTRAINTS else OUT / f"priority_{args.speed_priority:g}_{args.profit_policy}"
    folder.mkdir(parents=True, exist_ok=True)
    for name in ["ranked_options", "top_reassignment_candidates", "portfolio", "selected_rows", "capacity_ledger"]:
        result[name].to_csv(folder / f"{name}.csv", index=False, na_rep="", float_format="%.8f")
    joint.to_csv(folder / "joint_portfolio_sensitivity.csv", index=False, float_format="%.8f")
    (folder / "kpis.json").write_text(json.dumps(kpis, indent=2, allow_nan=False) + "\n")
    (folder / "constraints_used.json").write_text(json.dumps(constraints, indent=2) + "\n")
    (folder / "ranking_policy_used.json").write_text(json.dumps(policy, indent=2) + "\n")
    (folder / "ranking_preview_data.json").write_text(json.dumps(preview_payload(result, sensitivity, constraints, policy), separators=(",", ":"), allow_nan=False))
    sweep, sweep_portfolios = [], []
    for priority in [0., .25, .5, .75, 1.]:
        profile = build_rankings(scenarios, sensitivity, constraints, policy, priority, args.top_n, args.profit_policy)
        profile_kpis, _ = portfolio_kpis(profile, sensitivity)
        sweep.append({key: value for key, value in profile_kpis.items() if key != "settings"} | {"Speed Priority": priority})
        sweep_portfolios.append(profile["portfolio"].assign(**{"Speed Priority": priority}))
    pd.DataFrame(sweep).to_csv(folder / "priority_sweep_kpis.csv", index=False, na_rep="", float_format="%.8f")
    pd.concat(sweep_portfolios).to_csv(folder / "priority_sweep_portfolios.csv", index=False, float_format="%.8f")
    decisions = result["portfolio"].merge(result["selected_rows"][["Scenario ID", "Modeled Dispatch Lead Reduction Pct", "Modeled Contribution Change", "Profit Impact Stability Pct", "Scenario Confidence Score"]],
                                          left_on="Selected Scenario ID", right_on="Scenario ID", how="left")
    report = f"""# Ranked recommendations and KPIs

**These are provisional, assumption-based investigation options. Verified recommendation coverage is {kpis['verified_recommendation_coverage_pct']:.1f}%. No operational assignment is approved. The source shipment-date anomaly remains unresolved.**

## Ranking controls

Speed priority is {args.speed_priority:.0%}; profit priority is {1-args.speed_priority:.0%}. Top N is {args.top_n} per product. Current profit policy: `{args.profit_policy}`.

Speed utility = modeled dispatch reduction (%) / 10, clipped to [-1,1]. Profit utility = modeled contribution change / max(5% of absolute current modeled contribution, 100 source monetary units), clipped to [-1,1]. Score = speed priority × speed utility + profit priority × profit utility − 0.1 × (1 − profit stability / 100). The reference scales and penalty are explicit project heuristics, editable in `datasets/reference/recommendation_policy.json`; they are not learned coefficients.

Default profit protection blocks alternatives with negative base-case modeled contribution changes. `strict_all_cases` requires nonnegative changes in every tested case, and `tradeoff` explicitly permits base-case losses for exploration. Supplied capacity and compatibility restrictions are applied before ranking. Unknown constraints permit investigation only and do not confer feasibility. Baseline scores are zero. A move must have positive utility relative to keeping the current assignment.

Ranking is per product. Top-N alternatives are independent comparison options, not a simultaneously feasible allocation. The provisional portfolio considers products in descending best score, rechecks remaining receiving capacity, and selects one eligible option each. It conservatively does not reuse released origin capacity. This greedy procedure is not a global optimization algorithm.

## KPI definitions and results

| KPI | Definition | Current result |
|---|---|---:|
| Modeled lead time reduction (%) | 100 × sum(mapped units × modeled dispatch days saved) / sum(mapped units × current modeled dispatch days), across selected product decisions including keep-current | {format_kpi(kpis['modeled_lead_time_reduction_pct'], 'unavailable')} |
| Profit impact stability (%) | Share of aligned joint sensitivity cases where the sum of selected reassignment contribution changes is nonnegative | {format_kpi(kpis['profit_impact_stability_pct'], 'not applicable; no moves')} |
| Scenario confidence score (0–100) | Mapped-unit-weighted evidence readiness of proposed moves; each scenario uses the minimum of verified-date coverage, observed-origin coverage, alternative-outcome support, verified capacity, verified compatibility and calibrated nonsimulated estimate availability | {format_kpi(kpis['scenario_confidence_score'], 'not applicable; no moves')} |
| Recommendation coverage (%) | Products with a selected provisional reassignment / all assessed products × 100 | {format_kpi(kpis['recommendation_coverage_pct'])} |
| Verified recommendation coverage (%) | Products with evidence-supported selected reassignment / all assessed products × 100 | {format_kpi(kpis['verified_recommendation_coverage_pct'])} |

The lead-time KPI is a hypothetical dispatch allowance, not measured shipping performance or delivery time. Profit stability is a fraction of deliberately chosen grid cases, not a real-world probability. Common sensitivity shocks are summed jointly across moves; product stability percentages are not averaged. Confidence is an evidence-readiness gate, not a probabilistic prediction. It is zero because required evidence and calibrated operational estimates are absent. No-move portfolios report stability and confidence as not applicable, rather than presenting unchanged baselines as reliable reassignment gains.

Coverage reports actual proposed moves; products kept at their current factory do not inflate it. All {kpis['total_products']} products are assessed; {kpis['proposed_reassignments']} are proposed for investigation and {kpis['keep_current_products']} retain their current assignment. Products without an eligible option: {kpis['products_without_eligible_option']}. Geographic estimates cover mapped demand only, while capacity screens use whole-product Source Units including unmapped demand.

Base modeled portfolio contribution change: {kpis['base_modeled_contribution_change']:,.2f} source monetary units over the sample replay. Worst/best joint tested changes: {format_kpi(kpis['sensitivity_min_portfolio_contribution_change'])} / {format_kpi(kpis['sensitivity_max_portfolio_contribution_change'])}. These are not annual savings or statistical confidence bounds.

Under the default neutral factory cost assumptions and base-case profit protection, the same five chocolate-product moves remain selected at all five exported priority profiles. The slider still changes scores and ordering of comparison options; it does not manufacture different assignments when the same options dominate. Other cost assumptions, constraints or explicitly chosen tradeoff policies can change selections.

## Provisional portfolio

{markdown_table(decisions[['Product Name', 'Current Factory', 'Selected Factory', 'Decision', 'Modeled Dispatch Lead Reduction Pct', 'Modeled Contribution Change', 'Scenario Confidence Score']])}

All alternative factory–product combinations remain historically unsupported. Verify real shipment origins, dates, factory preparation times, costs, product compatibility and capacity before implementation. A positive model score or base-case gain does not remove uncertainty.

## Capacity and compatibility

`datasets/reference/operational_constraints.json` stores additional capacity in production units over the entire sample replay and compatible Product IDs. Null means unknown; capacity zero and compatibility [] are binding restrictions. Capacity and compatibility supplied without verification are still applied as provisional limits. Verification flags require a source reference and matching horizon. Current inputs are unknown, so no capacity or capability has been invented.

{markdown_table(result['capacity_ledger'])}

The ledger sums incoming moves at each receiving factory; per-product capacity checks alone are insufficient. Released origin units are reported but not reused in the conservative single pass. Missing or contradicted restrictions can leave a product without any eligible option; this is exposed, not silently replaced with zero gains.

## Reproduce

```powershell
python analysis/rank_recommendations.py --speed-priority 0.5 --top-n 3
python analysis/rank_recommendations.py --speed-priority 1 --profit-policy tradeoff
python analysis/rank_recommendations.py --profit-policy strict_all_cases
```

Optional `--constraints path/to/constraints.json` uses a supplied constraint file. The pure ranking and KPI functions support the dashboard slider. Exports include all ranked options, top-N investigation candidates, selected portfolio, capacity ledger, joint sensitivity cases, KPI JSON, five priority profiles and compact preview data. Source estimates and logistics assumptions are documented in [the scenario report](../scenario_simulator/scenario_simulator_report.md). Dependency setup is in the project README.
"""
    (folder / "recommendation_report.md").write_text(report, encoding="utf-8")
    print(json.dumps(kpis, indent=2, allow_nan=False))
    print("Top-N provisional candidates:", len(result["top_reassignment_candidates"]))
    print("Outputs:", folder)


if __name__ == "__main__":
    main()
