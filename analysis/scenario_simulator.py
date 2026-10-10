"""Assumption-based product/factory simulator; no operational regression is used.

Run: python analysis/scenario_simulator.py
Optional: --product CHO-MIL-31000 --region Pacific --ship-mode "Standard Class"
The pure simulate() function can also serve the later dashboard.
"""

import argparse
import hashlib
import itertools
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASSUMPTIONS = ROOT / "datasets" / "simulated" / "logistics_assumptions.json"


def read_inputs():
    data = pd.read_csv(ROOT / "datasets" / "processed" / "orders_cleaned.csv", dtype={"Product ID": str, "Row ID": str, "Postal Code": str})
    products = pd.read_csv(ROOT / "datasets" / "reference" / "products.csv", dtype={"Product ID": str})
    factories = pd.read_csv(ROOT / "datasets" / "reference" / "factories.csv")
    return data, products, factories


def validate_assumptions(assumptions, factories):
    if assumptions.get("is_simulated") is not True:
        raise ValueError("Scenario assumptions must be explicitly labeled simulated")
    nonnegative = ["planning_distance_multiplier", "handling_cost_per_record", "logistics_cost_per_unit",
                   "distance_cost_per_unit_per_1000_km", "dispatch_coordination_days_per_1000_km", "one_time_reassignment_cost_per_product"]
    for field in nonnegative:
        if not np.isfinite(assumptions[field]) or assumptions[field] < 0:
            raise ValueError(f"Invalid assumption: {field}")
    if assumptions["planning_distance_multiplier"] <= 0:
        raise ValueError("Planning distance multiplier must be positive")
    for factory in factories["Factory"]:
        settings = assumptions["factories"][factory]
        for field in ["dispatch_preparation_days", "alternative_manufacturing_cost_multiplier"]:
            if not np.isfinite(settings[field]) or settings[field] < 0:
                raise ValueError(f"Invalid factory assumption: {factory}, {field}")
    for settings in assumptions["ship_modes"].values():
        if any(not np.isfinite(settings[field]) or settings[field] < 0 for field in ["cost_multiplier", "dispatch_preparation_days"]):
            raise ValueError("Invalid ship-mode assumptions")
    for values in assumptions["sensitivity_grid"].values():
        if not values or any(not np.isfinite(value) or value <= 0 for value in values):
            raise ValueError("Sensitivity multipliers must be finite positive values")
        if 1.0 not in values:
            raise ValueError("Each sensitivity grid must include 1.0 to retain the base case")


def distances_to_factory(rows, factory):
    """Great-circle kilometres to the destination ZIP centroids."""
    latitude = np.radians(rows["Destination Latitude"].to_numpy(dtype=float))
    longitude = np.radians(rows["Destination Longitude"].to_numpy(dtype=float))
    origin_lat, origin_lon = np.radians(float(factory["Latitude"])), np.radians(float(factory["Longitude"]))
    h = np.sin((latitude - origin_lat) / 2) ** 2 + np.cos(latitude) * np.cos(origin_lat) * np.sin((longitude - origin_lon) / 2) ** 2
    return 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(h, 0, 1)))


def cost_time_components(rows, factory, assumptions):
    distances = distances_to_factory(rows, factory)
    planned = distances * assumptions["planning_distance_multiplier"]
    units = rows["Units"].to_numpy(dtype=float)
    mode_cost = rows["Ship Mode"].map(lambda name: assumptions["ship_modes"][name]["cost_multiplier"]).to_numpy(dtype=float)
    mode_days = rows["Ship Mode"].map(lambda name: assumptions["ship_modes"][name]["dispatch_preparation_days"]).to_numpy(dtype=float)
    preparation = assumptions["factories"][factory["Factory"]]["dispatch_preparation_days"] + mode_days
    distance_buffer = planned / 1000 * assumptions["dispatch_coordination_days_per_1000_km"]
    return {"distances": distances, "units": units, "preparation": preparation, "distance_buffer": distance_buffer,
            "weighted_distance": float(np.average(distances, weights=units)),
            "fixed_logistics": float(((assumptions["handling_cost_per_record"] + units * assumptions["logistics_cost_per_unit"]) * mode_cost).sum()),
            "distance_logistics": float((units * planned / 1000 * assumptions["distance_cost_per_unit_per_1000_km"] * mode_cost).sum())}


def evaluate_pair(rows, current_components, candidate_components, candidate_factory, is_current, assumptions,
                  distance_rate=1., manufacture=1., setup=1., dispatch_buffer=1.):
    """Paired comparison on the exact same mapped cohort and common rate assumptions."""
    sales, actual_cost = float(rows["Sales"].sum()), float(rows["Cost"].sum())
    current_shipping = current_components["fixed_logistics"] + current_components["distance_logistics"] * distance_rate
    candidate_shipping = candidate_components["fixed_logistics"] + candidate_components["distance_logistics"] * distance_rate
    multiplier = 1. if is_current else assumptions["factories"][candidate_factory]["alternative_manufacturing_cost_multiplier"] * manufacture
    candidate_manufacturing = actual_cost * multiplier
    reassignment = 0. if is_current else assumptions["one_time_reassignment_cost_per_product"] * setup
    current_contribution = sales - actual_cost - current_shipping
    candidate_contribution = sales - candidate_manufacturing - candidate_shipping - reassignment
    current_lead = current_components["preparation"] + current_components["distance_buffer"] * dispatch_buffer
    candidate_lead = candidate_components["preparation"] + candidate_components["distance_buffer"] * dispatch_buffer
    baseline_lead = float(np.average(current_lead, weights=current_components["units"]))
    alternative_lead = float(np.average(candidate_lead, weights=candidate_components["units"]))
    profit_delta = candidate_contribution - current_contribution
    return {"Current Modeled Dispatch Lead Days": baseline_lead, "Candidate Modeled Dispatch Lead Days": alternative_lead,
            "Modeled Dispatch Lead Reduction Days": baseline_lead - alternative_lead,
            "Modeled Dispatch Lead Reduction Pct": 100 * (baseline_lead - alternative_lead) / baseline_lead if baseline_lead > 0 else np.nan,
            "Candidate Modeled Dispatch Lead P90 Days": float(np.quantile(candidate_lead, .9)),
            "Current Assumed Logistics Cost": current_shipping, "Candidate Assumed Logistics Cost": candidate_shipping,
            "Assumed Logistics Savings": current_shipping - candidate_shipping,
            "Current Manufacturing Cost": actual_cost, "Candidate Assumed Manufacturing Cost": candidate_manufacturing,
            "Assumed Reassignment Cost": reassignment, "Current Modeled Contribution": current_contribution,
            "Candidate Modeled Contribution": candidate_contribution, "Modeled Contribution Change": profit_delta,
            "Modeled Contribution Change Pct": 100 * profit_delta / current_contribution if current_contribution > 0 else np.nan}


def simulate(data, products, factories, assumptions, product_id=None, region=None, ship_mode=None):
    """Return scenario tables without writing files. All estimates are explicitly assumed."""
    validate_assumptions(assumptions, factories)
    selected = data.copy()
    for column, value in [("Product ID", product_id), ("Region", region), ("Ship Mode", ship_mode)]:
        if value is not None:
            if value not in set(data[column]):
                raise ValueError(f"Unknown {column}: {value}")
            selected = selected[selected[column].eq(value)]
    if selected.empty:
        raise ValueError("The selected product/region/ship-mode combination has no records")
    for name in selected["Ship Mode"].unique():
        if name not in assumptions["ship_modes"]:
            raise ValueError(f"No assumptions for ship mode {name}")
    source_support = data.groupby(["Product ID", "Assigned Factory"]).size()
    factory_lookup = factories.set_index("Factory", drop=False)
    scenarios, sensitivity_rows, comparison_rows = [], [], []
    grid = assumptions["sensitivity_grid"]
    cases = list(itertools.product(grid["distance_rate_multipliers"], grid["alternative_manufacturing_multipliers"],
                                   grid["setup_cost_multipliers"], grid["dispatch_buffer_multipliers"]))
    for product in products.to_dict(orient="records"):
        cohort = selected[selected["Product ID"].eq(product["Product ID"])]
        if cohort.empty:
            continue
        current = product["Factory"]
        if not cohort["Assigned Factory"].eq(current).all():
            raise ValueError("Source cohort disagrees with static product assignment")
        mapped = cohort[cohort["Destination Latitude"].notna() & cohort["Destination Longitude"].notna()].copy()
        current_components = cost_time_components(mapped, factory_lookup.loc[current], assumptions) if len(mapped) else None
        valid = cohort["Lead Time Quality"].eq("passes_interval_screen") & cohort["Ship Date After Snapshot"].astype(str).str.lower().eq("false")
        for candidate in factories["Factory"]:
            is_current = candidate == current
            scenario_id = product["Product ID"] + "-" + hashlib.sha256(candidate.encode()).hexdigest()[:8]
            support = int(source_support.get((product["Product ID"], candidate), 0))
            base = {"Scenario ID": scenario_id, "Product ID": product["Product ID"], "Product Name": product["Product Name"],
                    "Current Factory": current, "Candidate Factory": candidate, "Is Current Assignment": is_current,
                    "Source Records": len(cohort), "Source Units": int(cohort["Units"].sum()), "Mapped Records": len(mapped),
                    "Mapped Units": int(mapped["Units"].sum()), "Mapped Record Coverage Pct": 100 * len(mapped) / len(cohort),
                    "Mapped Unit Coverage Pct": 100 * mapped["Units"].sum() / cohort["Units"].sum(),
                    "Static Assignment Record Support": support, "Observed Factory Origin Records": 0,
                    "Verified Lead Time Records": int(valid.sum()), "Historical Alternative Outcome Evidence": False,
                    "Factory Product Combination Uncertain": True,
                    "Static Factory Product Assignment Supported": is_current,
                    "Capacity Verification": "unverified", "Production Compatibility": "unverified",
                    "Operational Feasibility": "not_established", "Estimate Status": "assumption_based" if len(mapped) else "unavailable_no_coordinates",
                    "Is Simulated Estimate": True, "Profit Scope": "Mapped cohort replay; full one-time assumed setup charged to this subset",
                    "Uncertainty Reasons": "; ".join((["no alternative factory-product outcome history"] if not is_current else ["current origin inferred from static assignment only"]) +
                        ["unverified source lead-time dates", "hypothetical dispatch and logistics rates", "unverified capacity and compatibility"] +
                        (["unmapped orders excluded"] if len(mapped) < len(cohort) else []) +
                        (["fewer than 20 mapped records"] if len(mapped) < 20 else []))}
            if not len(mapped):
                base.update({"Current Weighted Great Circle Km": np.nan, "Candidate Weighted Great Circle Km": np.nan,
                             "Distance Reduction Km": np.nan, "Modeled Dispatch Lead Reduction Days": np.nan,
                             "Modeled Contribution Change": np.nan, "Sensitivity Min Contribution Change": np.nan,
                             "Sensitivity Max Contribution Change": np.nan, "Sensitivity Case Count": 0,
                             "Sensitivity Min Dispatch Reduction Days": np.nan, "Sensitivity Max Dispatch Reduction Days": np.nan,
                             "Contribution Nonnegative In All Tested Cases": None,
                             "Sensitivity Bounds Are Confidence Intervals": False})
                scenarios.append(base)
                continue
            candidate_components = cost_time_components(mapped, factory_lookup.loc[candidate], assumptions)
            base.update({"Current Weighted Great Circle Km": current_components["weighted_distance"],
                         "Candidate Weighted Great Circle Km": candidate_components["weighted_distance"],
                         "Distance Reduction Km": current_components["weighted_distance"] - candidate_components["weighted_distance"],
                         "Mapped Sales": float(mapped["Sales"].sum()), "Mapped Source Gross Profit": float(mapped["Gross Profit"].sum())})
            base.update(evaluate_pair(mapped, current_components, candidate_components, candidate, is_current, assumptions))
            case_results = []
            for case_number, (distance_rate, manufacture, setup, dispatch) in enumerate(cases, 1):
                values = evaluate_pair(mapped, current_components, candidate_components, candidate, is_current, assumptions,
                                       distance_rate, manufacture, setup, dispatch)
                case_results.append(values)
                sensitivity_rows.append({"Scenario ID": scenario_id, "Case": case_number,
                                         "Distance Rate Multiplier": distance_rate, "Alternative Manufacturing Multiplier": manufacture,
                                         "Setup Cost Multiplier": setup, "Dispatch Buffer Multiplier": dispatch, **values,
                                         "Is Simulated Estimate": True})
            changes = [result["Modeled Contribution Change"] for result in case_results]
            leads = [result["Modeled Dispatch Lead Reduction Days"] for result in case_results]
            base.update({"Sensitivity Min Contribution Change": min(changes), "Sensitivity Max Contribution Change": max(changes),
                         "Sensitivity Min Dispatch Reduction Days": min(leads), "Sensitivity Max Dispatch Reduction Days": max(leads),
                         "Contribution Nonnegative In All Tested Cases": min(changes) >= -1e-9,
                         "Sensitivity Case Count": len(case_results), "Sensitivity Bounds Are Confidence Intervals": False})
            scenarios.append(base)
            # All current/candidate route comparisons use identical destination records and weights.
            enriched = mapped.assign(**{"Current Great Circle Km": current_components["distances"],
                                        "Candidate Great Circle Km": candidate_components["distances"],
                                        "Current Modeled Dispatch Lead Days": current_components["preparation"] + current_components["distance_buffer"],
                                        "Candidate Modeled Dispatch Lead Days": candidate_components["preparation"] + candidate_components["distance_buffer"]})
            for (route_region, mode), group in enriched.groupby(["Region", "Ship Mode"]):
                comparison_rows.append({"Scenario ID": scenario_id, "Product ID": product["Product ID"], "Current Factory": current,
                                        "Candidate Factory": candidate, "Region": route_region, "Ship Mode": mode,
                                        "Mapped Records": len(group), "Mapped Units": int(group["Units"].sum()),
                                        "Current Weighted Great Circle Km": float(np.average(group["Current Great Circle Km"], weights=group["Units"])),
                                        "Candidate Weighted Great Circle Km": float(np.average(group["Candidate Great Circle Km"], weights=group["Units"])),
                                        "Current Modeled Dispatch Lead Days": float(np.average(group["Current Modeled Dispatch Lead Days"], weights=group["Units"])),
                                        "Candidate Modeled Dispatch Lead Days": float(np.average(group["Candidate Modeled Dispatch Lead Days"], weights=group["Units"])),
                                        "Is Simulated Estimate": True})
    empty_sensitivity_columns = ["Scenario ID", "Case", "Distance Rate Multiplier", "Alternative Manufacturing Multiplier",
                                 "Setup Cost Multiplier", "Dispatch Buffer Multiplier", "Modeled Contribution Change",
                                 "Modeled Dispatch Lead Reduction Days", "Is Simulated Estimate"]
    empty_route_columns = ["Scenario ID", "Product ID", "Current Factory", "Candidate Factory", "Region", "Ship Mode",
                           "Mapped Records", "Mapped Units", "Is Simulated Estimate"]
    return {"scenarios": pd.DataFrame(scenarios),
            "sensitivity": pd.DataFrame(sensitivity_rows) if sensitivity_rows else pd.DataFrame(columns=empty_sensitivity_columns),
            "route_comparisons": pd.DataFrame(comparison_rows) if comparison_rows else pd.DataFrame(columns=empty_route_columns), "selected_records": len(selected),
            "filters": {"product": product_id, "region": region, "ship_mode": ship_mode}}


def md_table(frame):
    formatted = frame.copy()
    for field in formatted.columns:
        if pd.api.types.is_float_dtype(formatted[field]):
            formatted[field] = formatted[field].map(lambda value: "unavailable" if pd.isna(value) else f"{value:,.3f}")
    return "\n".join(["| " + " | ".join(formatted.columns) + " |", "| " + " | ".join(["---"] * len(formatted.columns)) + " |"] +
                     ["| " + " | ".join(map(str, row)) + " |" for row in formatted.itertuples(index=False, name=None)])


def save_outputs(result, assumptions):
    folder = ROOT / "reports" / "scenario_simulator"
    if any(value is not None for value in result["filters"].values()):
        folder = folder / ("filtered_" + hashlib.sha256(json.dumps(result["filters"], sort_keys=True).encode()).hexdigest()[:10])
    folder.mkdir(parents=True, exist_ok=True)
    for name in ["scenarios", "sensitivity", "route_comparisons"]:
        result[name].to_csv(folder / f"{name}.csv", index=False, na_rep="", float_format="%.8f")
    (folder / "assumptions_used.json").write_text(json.dumps(assumptions, indent=2) + "\n", encoding="utf-8")
    scenarios = result["scenarios"]
    alternatives = scenarios[~scenarios["Is Current Assignment"]]
    usable = alternatives[alternatives["Estimate Status"].eq("assumption_based")]
    # Descriptive comparison, not a feasibility recommendation or selection by speed alone.
    display = usable.sort_values(["Product ID", "Modeled Contribution Change"], ascending=[True, False]).groupby("Product ID", sort=True).head(1)
    display.to_csv(folder / "highest_modeled_contribution_alternative_per_product.csv", index=False, float_format="%.8f")
    summary = {"selected_records": result["selected_records"], "filters": result["filters"],
               "products_compared": int(scenarios["Product ID"].nunique()), "factory_scenarios": len(scenarios),
               "current_assignment_scenarios": int(scenarios["Is Current Assignment"].sum()), "alternative_scenarios": len(alternatives),
               "sensitivity_cases": len(result["sensitivity"]),
               "cases_per_available_scenario": int(np.prod([len(values) for values in assumptions["sensitivity_grid"].values()])),
               "alternative_scenarios_with_uncertain_factory_product_evidence": int(alternatives["Factory Product Combination Uncertain"].sum()),
               "base_case_positive_contribution_alternatives": int(usable["Modeled Contribution Change"].gt(0).sum()),
               "base_case_shorter_dispatch_alternatives": int(usable["Modeled Dispatch Lead Reduction Days"].gt(0).sum()),
               "nonnegative_contribution_in_all_tested_cases_alternatives": int(usable["Contribution Nonnegative In All Tested Cases"].sum()),
               "verified_lead_time_prediction": False, "uses_diagnostic_regression_model": False, "source_date_offset_applied": 0,
               "simulated_inputs_created": True, "source_records_modified": False,
               "profit_definition": "Sales minus source/current or assumed candidate manufacturing cost, assumed logistics and one-time reassignment cost; excludes other overheads",
               "population": "Mapped orders only; Canadian unmapped orders excluded from scenario estimates",
               "operational_feasibility_established": False, "statistical_confidence_estimated": False}
    (folder / "scenario_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if not display.empty:
        plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
        ordered = display.sort_values("Modeled Contribution Change")
        labels = ordered["Product Name"].str.replace("Wonka Bar - ", "", regex=False)
        fig, axes = plt.subplots(1, 2, figsize=(14, 8))
        values = ordered["Modeled Contribution Change"]
        axes[0].barh(labels, values, color=np.where(values >= 0, "#148677", "#b45b46"))
        axes[0].axvline(0, color="#17243a", linewidth=.8)
        axes[0].set(title="Highest modeled-contribution alternative per product", xlabel="Contribution change (source monetary units)")
        low = values - ordered["Sensitivity Min Contribution Change"]
        high = ordered["Sensitivity Max Contribution Change"] - values
        axes[0].errorbar(values, np.arange(len(ordered)), xerr=[np.maximum(low, 0), np.maximum(high, 0)], fmt="none", ecolor="#17243a", capsize=3)
        axes[1].barh(labels, ordered["Modeled Dispatch Lead Reduction Days"], color="#2355a4")
        axes[1].axvline(0, color="#17243a", linewidth=.8)
        axes[1].set(title="Hypothetical dispatch allowance change", xlabel="Modeled dispatch lead reduction (days)")
        fig.suptitle("ASSUMPTION-BASED SCENARIOS | alternatives are unverified", fontsize=16, fontweight="bold")
        fig.text(.5, .015, "Whiskers are sensitivity bounds, not confidence intervals. Estimates replay mapped sample demand; no assignment is approved.", ha="center", fontsize=9)
        fig.tight_layout(rect=(0, .05, 1, .95))
        fig.savefig(folder / "scenario_comparison.png", dpi=170, bbox_inches="tight")
        plt.close(fig)
    chart_markup = "![Scenario comparison](scenario_comparison.png)" if not display.empty else "No coordinate-supported estimates are available for this selection."
    grid_sizes = [len(values) for values in assumptions["sensitivity_grid"].values()]
    report = f"""# Factory scenario simulator

**All lead-time and logistics estimates are hypothetical. All alternative product–factory combinations lack historical outcome evidence. No scenario establishes operational feasibility or actual profit/speed improvement.**

The simulator compares {summary['products_compared']} products across {len(scenarios)} product–factory scenarios: {summary['current_assignment_scenarios']} current assignments and {len(alternatives)} alternatives. It computes {len(result['sensitivity']):,} sensitivity cases. Filters used: `{json.dumps(result['filters'])}`.

## Source and estimate scopes

Historical orders, sales, manufacturing costs, units, product assignments and coordinates remain unchanged. Scenario estimates replay only records with destination coordinates. Source Records/Units and mapped coverage are included for every product. Unmapped Canadian records are not assigned zero distances or assumed financial outcomes. The full hypothetical one-time setup cost is charged to the mapped subset. Values cover the sample replay, not annual savings or a future forecast.

Static Assignment Record Support counts records consistent with the reference product assignment. It does not count observed origin-factory measurements. Observed Factory Origin Records remains zero. Every alternative is explicitly flagged uncertain. Factory capacity, production compatibility and operational feasibility remain unverified.

## Documented assumptions and formulas

All assumptions are in `datasets/simulated/logistics_assumptions.json` and copied into `assumptions_used.json` beside this report. Money uses source monetary units; the source dictionary does not specify currency.

- Planning distance proxy = Haversine great-circle distance × {assumptions['planning_distance_multiplier']}. This is not measured road distance.
- Logistics per record = (handling allowance {assumptions['handling_cost_per_record']} + units × {assumptions['logistics_cost_per_unit']} + units × planning distance / 1,000 × {assumptions['distance_cost_per_unit_per_1000_km']}) × ship-mode cost multiplier. Handling is per source record because repeated Order IDs have ambiguous transaction grain.
- Modeled order-to-dispatch allowance = factory preparation days + ship-mode preparation days + planning distance / 1,000 × {assumptions['dispatch_coordination_days_per_1000_km']} days. The last term is an explicit hypothetical dispatch-coordination buffer before shipment, not vehicle travel or delivery time.
- Current manufacturing cost remains the source cost. Candidate manufacturing cost = source cost × the candidate's alternative manufacturing multiplier; the base default is 1.0 at every factory, a neutral assumption.
- Modeled contribution = sales − manufacturing cost − assumed logistics cost − assumed setup cost. It is not actual net profit; taxes, overheads, inventory effects and other transition costs are absent.
- Setup cost is {assumptions['one_time_reassignment_cost_per_product']} once per alternative product–factory scenario over the cohort replay. Current assignment incurs zero setup cost.

Dispatch averages are weighted by units. Candidate dispatch P90 is record-based. Current and alternative scenarios use identical mapped destination records and the same ship modes/units. Contribution percentage change is unavailable when current modeled contribution is nonpositive.

## Sensitivity

The grid jointly varies distance-rate, alternative-manufacturing, setup-cost and dispatch-buffer multipliers. The axis sizes are {grid_sizes}, giving {summary['cases_per_available_scenario']} cases per available scenario. Each grid includes 1.0 so the base case is within the sensitivity bounds. Baseline and candidate share the distance-rate and dispatch-buffer perturbations; manufacturing perturbations and setup costs apply only to alternatives. The minimum and maximum changes are bounds over the tested assumptions, not probabilities or statistical confidence intervals.

Base-case positive-contribution alternatives: {summary['base_case_positive_contribution_alternatives']}. Alternatives with shorter modeled dispatch allowances: {summary['base_case_shorter_dispatch_alternatives']}. Alternatives with nonnegative contribution change in every tested case: {summary['nonnegative_contribution_in_all_tested_cases_alternatives']}. These counts describe the chosen assumptions, not real business outcomes. Current-factory scenarios have exactly zero changes under all sensitivity cases.

## Comparison by product

The table shows the alternative with the highest base-case modeled contribution for each product, including products whose best alternative is still worse than the current assignment. This is a descriptive comparison, not a recommendation or feasibility approval. All five options, including current factories, are in `scenarios.csv`.

{md_table(display[['Product Name', 'Current Factory', 'Candidate Factory', 'Modeled Dispatch Lead Reduction Days', 'Modeled Contribution Change', 'Sensitivity Min Contribution Change', 'Sensitivity Max Contribution Change']])}

{chart_markup}

## Reliability limits

Source Ship Date minus Order Date remains suspect; no 2,000-day correction is applied. The diagnostic regression models are not used for these estimates. Estimated dispatch changes come solely from the hypothetical formula. Alternative factories have no historical product-specific outcomes, and even current shipment origins are inferred from static assignments. No factory-product capability or capacity is invented.

Before implementing an assignment, replace assumptions with verified dates, observed origin/outcome records, tariffs, factory preparation times, manufacturing/reassignment costs and production constraints. Sensitivity consistency is not a confidence score. The simulator does not claim congestion relief, delivery improvement or actual profit preservation.

## Reproduce and use

```powershell
python analysis/scenario_simulator.py
python analysis/scenario_simulator.py --product CHO-MIL-31000 --region Pacific --ship-mode "Standard Class"
```

Optional `--assumptions path/to/file.json` runs an edited assumption file. Filtered runs use a separate subfolder so the full comparison is retained. The pure `simulate()` function returns scenario, sensitivity and route-comparison DataFrames for future dashboard integration. Dependencies are included in `analysis/requirements-models.txt`. Source provenance and geographic limitations are documented in [the dataset guide](../../datasets/DATASET_GUIDE.md).
"""
    (folder / "scenario_simulator_report.md").write_text(report, encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("Outputs:", folder)
    return folder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product", help="Product ID")
    parser.add_argument("--region")
    parser.add_argument("--ship-mode")
    parser.add_argument("--assumptions", type=Path, default=DEFAULT_ASSUMPTIONS)
    args = parser.parse_args()
    assumptions = json.loads(args.assumptions.read_text(encoding="utf-8"))
    data, products, factories = read_inputs()
    result = simulate(data, products, factories, assumptions, args.product, args.region, args.ship_mode)
    save_outputs(result, assumptions)


if __name__ == "__main__":
    main()
