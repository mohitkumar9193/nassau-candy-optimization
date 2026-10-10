"""Exploratory route clustering and investigation queues.

Run: python analysis/cluster_routes.py (dependencies: requirements-models.txt).
Reliable geography/demand clustering is separate from diagnostic-only clustering
that includes suspect source lead-time intervals. No offset or simulated data is used.
"""

import hashlib
import json
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "route_analysis"
MODEL_OUT = ROOT / "models" / "route_clusters"
KEYS = ["Product ID", "Assigned Factory", "Country/Region", "Region", "Ship Mode"]
GEOGRAPHIC_FEATURES = ["Unit Weighted Distance Km", "Distance Std Km", "Log Demand Units"]
DIAGNOSTIC_FEATURES = ["Unit Weighted Distance Km", "Diagnostic Mean Interval Days", "Diagnostic Interval Std Days", "Log Demand Units"]
MIN_RECORDS, MIN_COVERAGE = 20, .90


def identifier(values, prefix):
    return prefix + hashlib.sha256(json.dumps(list(values)).encode()).hexdigest()[:12]


def weighted_distance(rows):
    mapped = rows[rows["Great Circle Distance Km"].notna()]
    return np.average(mapped["Great Circle Distance Km"], weights=mapped["Units"]) if len(mapped) else np.nan


def summarize(rows):
    mapped = rows[rows["Great Circle Distance Km"].notna()]
    valid = rows[rows["Valid Historical Interval"]]
    return {"Records": len(rows), "Units": int(rows["Units"].sum()), "Sales": float(rows["Sales"].sum()),
            "Gross Profit": float(rows["Gross Profit"].sum()), "Mapped Records": len(mapped),
            "Mapped Units": int(mapped["Units"].sum()), "Coordinate Coverage Pct": 100 * len(mapped) / len(rows),
            "Unit Weighted Distance Km": float(weighted_distance(rows)),
            "Distance Std Km": float(mapped["Great Circle Distance Km"].std(ddof=1)),
            "P90 Distance Km": float(mapped["Great Circle Distance Km"].quantile(.90)),
            "Distance Exposure Unit Km": float((mapped["Great Circle Distance Km"] * mapped["Units"]).sum()) if len(mapped) else np.nan,
            "Diagnostic Mean Interval Days": float(rows["Order To Shipment Lead Time Days"].mean()),
            "Diagnostic Interval Std Days": float(rows["Order To Shipment Lead Time Days"].std(ddof=1)),
            "Diagnostic P90 Interval Days": float(rows["Order To Shipment Lead Time Days"].quantile(.90)),
            "Valid Historical Interval Records": len(valid),
            "Valid Mean Lead Time Days": float(valid["Order To Shipment Lead Time Days"].mean()),
            "Valid Lead Time Std Days": float(valid["Order To Shipment Lead Time Days"].std(ddof=1)),
            "Suspect Interval Records": int((~rows["Valid Historical Interval"]).sum())}


def fit_clusters(routes, features, prefix, diagnostic):
    """Scale each route equally; choose k by silhouette with at least 3 routes/cluster."""
    candidates, fits = [], {}
    for k in range(2, min(6, len(routes) - 1) + 1):
        model = Pipeline([("scale", StandardScaler()), ("cluster", KMeans(n_clusters=k, random_state=42, n_init=20))])
        labels = model.fit_predict(routes[features])
        smallest = int(pd.Series(labels).value_counts().min())
        silhouette = float(silhouette_score(model.named_steps["scale"].transform(routes[features]), labels))
        candidates.append({"Cluster Set": prefix, "K": k, "Silhouette": silhouette,
                           "Smallest Cluster Routes": smallest, "Eligible": smallest >= 3})
        fits[k] = (model, labels)
    usable = [r for r in candidates if r["Eligible"]]
    if not usable:
        raise ValueError("Insufficient support for meaningful route clusters")
    selected = max(usable, key=lambda r: (r["Silhouette"], -r["K"]))
    model, labels = fits[selected["K"]]
    order = pd.DataFrame({"Label": labels, "Distance": routes["Unit Weighted Distance Km"].to_numpy()}).groupby("Label")["Distance"].mean().sort_values().index
    mapping = {int(label): f"{prefix}{i + 1}" for i, label in enumerate(order)}
    canonical = pd.Series([mapping[int(label)] for label in labels], index=routes.index)
    stability = []
    for seed in [7, 101, 2026]:
        other = KMeans(n_clusters=selected["K"], random_state=seed, n_init=20).fit_predict(model.named_steps["scale"].transform(routes[features]))
        stability.append({"Cluster Set": prefix, "Seed": seed, "Adjusted Rand Index": float(adjusted_rand_score(labels, other))})
    joblib.dump({"pipeline": model, "features": features, "cluster_labels": mapping,
                 "exploratory_only": True, "diagnostic_only": diagnostic, "operational_slow_route_detection_allowed": False},
                MODEL_OUT / ("diagnostic_clusters.joblib" if diagnostic else "geographic_clusters.joblib"), compress=3)
    return canonical, candidates, stability, selected


def md_table(frame):
    formatted = frame.copy()
    for column in formatted.columns:
        if pd.api.types.is_float_dtype(formatted[column]):
            formatted[column] = formatted[column].map(lambda x: "unavailable" if pd.isna(x) else f"{x:,.2f}")
    return "\n".join(["| " + " | ".join(formatted.columns) + " |", "| " + " | ".join(["---"] * len(formatted.columns)) + " |"] +
                     ["| " + " | ".join(str(x).replace("|", "\\|") for x in row) + " |" for row in formatted.itertuples(index=False, name=None)])


def main():
    for path in [OUT, MODEL_OUT]:
        path.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(ROOT / "datasets" / "processed" / "orders_cleaned.csv", dtype={"Product ID": str, "Row ID": str, "Postal Code": str})
    data["Order Date"] = pd.to_datetime(data["Order Date"])
    data["Quarter"] = data["Order Date"].dt.to_period("Q").astype(str)
    data["Valid Historical Interval"] = data["Lead Time Quality"].eq("passes_interval_screen") & data["Ship Date After Snapshot"].astype(str).str.lower().eq("false")
    route_rows, quarterly = [], []
    for group, rows in data.groupby(KEYS, sort=True):
        route_id = identifier(group, "R-")
        route_rows.append({"Route ID": route_id, **dict(zip(KEYS, group)), "Product Name": rows["Product Name"].iloc[0], **summarize(rows)})
        for quarter, period in rows.groupby("Quarter"):
            quarterly.append({"Route ID": route_id, **dict(zip(KEYS, group)), "Quarter": quarter, **summarize(period)})
    routes, quarters = pd.DataFrame(route_rows), pd.DataFrame(quarterly)
    if not routes["Route ID"].is_unique:
        raise ValueError("Route identifiers collide")
    routes["Log Demand Units"] = np.log1p(routes["Units"])
    routes["Cluster Eligibility"] = np.select(
        [routes["Mapped Records"].eq(0), routes["Records"].lt(MIN_RECORDS), routes["Coordinate Coverage Pct"].lt(MIN_COVERAGE * 100)],
        ["unavailable_coordinates", "sparse_route_history", "insufficient_coordinate_coverage"], default="eligible")
    supported = routes[routes["Cluster Eligibility"].eq("eligible")].copy()
    if supported[GEOGRAPHIC_FEATURES + DIAGNOSTIC_FEATURES].isna().any().any():
        raise ValueError("Supported routes must have all clustering inputs")
    geo_labels, geo_candidates, geo_stability, geo_selected = fit_clusters(supported, GEOGRAPHIC_FEATURES, "G", False)
    diag_labels, diag_candidates, diag_stability, diag_selected = fit_clusters(supported, DIAGNOSTIC_FEATURES, "D", True)
    routes["Geographic Cluster"] = geo_labels.reindex(routes.index).fillna("unassigned")
    routes["Diagnostic Cluster"] = diag_labels.reindex(routes.index).fillna("unassigned")
    routes["Slow Route Status"] = "unavailable_unverified_dates"
    routes["Mean Lead Time For Decisions Days"] = np.nan
    routes["Distance Variability CV"] = routes["Distance Std Km"] / routes["Unit Weighted Distance Km"].replace(0, np.nan)

    summaries = []
    for set_name, field in [("Geographic", "Geographic Cluster"), ("Diagnostic only", "Diagnostic Cluster")]:
        for label, group in routes[~routes[field].eq("unassigned")].groupby(field):
            summaries.append({"Cluster Set": set_name, "Cluster": label, "Routes": len(group),
                              "Records": int(group["Records"].sum()), "Units": int(group["Units"].sum()),
                              "Mean Route Distance Km": float(group["Unit Weighted Distance Km"].mean()),
                              "Mean Distance Std Km": float(group["Distance Std Km"].mean()),
                              "Diagnostic Mean Route Interval Days": float(group["Diagnostic Mean Interval Days"].mean()),
                              "Diagnostic Mean Interval Std Days": float(group["Diagnostic Interval Std Days"].mean()),
                              "Median Route Units": float(group["Units"].median()),
                              "Valid Historical Interval Records": int(group["Valid Historical Interval Records"].sum()),
                              "Interpretation": "Geographic similarity; speed unverified" if set_name == "Geographic" else "Unverified interval pattern; not operational performance"})
    cluster_summary = pd.DataFrame(summaries)

    # Keep country in route identity to avoid mixing unavailable Canadian geography with US coordinates.
    # Regional product investigation combines countries, but explicitly reports mapped coverage.
    rp_rows, rp_quarters = [], []
    for group, rows in data.groupby(["Product ID", "Region"]):
        combo = identifier(group, "RP-")
        rp_rows.append({"Combination ID": combo, "Product ID": group[0], "Region": group[1],
                        "Product Name": rows["Product Name"].iloc[0], "Assigned Factory": rows["Assigned Factory"].iloc[0], **summarize(rows)})
        for quarter, period in rows.groupby("Quarter"):
            rp_quarters.append({"Combination ID": combo, "Product ID": group[0], "Region": group[1], "Quarter": quarter, **summarize(period)})
    combinations, combination_quarters = pd.DataFrame(rp_rows), pd.DataFrame(rp_quarters)
    eligible_combinations = combinations[combinations["Mapped Records"].ge(30) & combinations["Coordinate Coverage Pct"].ge(90)]
    distance_cutoff = float(eligible_combinations["Unit Weighted Distance Km"].quantile(.75))
    for index, row in combinations.iterrows():
        periods = combination_quarters[combination_quarters["Combination ID"].eq(row["Combination ID"]) & combination_quarters["Mapped Records"].ge(5)]
        far_periods = periods["Unit Weighted Distance Km"].ge(distance_cutoff)
        count, share = int(far_periods.sum()), float(far_periods.mean()) if len(periods) else np.nan
        persistent = len(periods) >= 3 and share >= .75
        combinations.loc[index, "Supported Geographic Quarters"] = len(periods)
        combinations.loc[index, "Long Distance Quarters"] = count
        combinations.loc[index, "Long Distance Quarter Share Pct"] = 100 * share
        combinations.loc[index, "Persistent Long Distance"] = str(persistent).lower()
    candidates = combinations[combinations["Mapped Records"].ge(30) & combinations["Coordinate Coverage Pct"].ge(90) &
                              combinations["Unit Weighted Distance Km"].ge(distance_cutoff)].sort_values("Distance Exposure Unit Km", ascending=False).copy()
    candidates["Investigation Reason"] = "Upper-quartile geographic distance with at least 30 mapped records; verify freight rates and production feasibility"
    candidates["Confirmed Slow"] = "unavailable_unverified_dates"
    sparse = routes[routes["Cluster Eligibility"].eq("sparse_route_history") | (routes["Records"] < 20)].copy()
    uncovered = routes[routes["Mapped Records"].eq(0)].copy()

    # A future relative consistency screen must use valid dates and repeated supported quarters.
    # Current source has none; do not relabel every 2,000-day interval as a slow route.
    slow_columns = ["Route ID", "Product ID", "Assigned Factory", "Country/Region", "Region", "Ship Mode",
                    "Supported Valid Quarters", "Slow Valid Quarters", "Slow Valid Quarter Share Pct"]
    confirmed_slow = pd.DataFrame(columns=slow_columns)
    valid_periods = quarters[quarters["Valid Historical Interval Records"].ge(20)].copy()
    if len(valid_periods):
        # Peers are routes within the same country, ship mode and quarter; >=3 peers required.
        peer_keys = ["Country/Region", "Ship Mode", "Quarter"]
        valid_periods["Peer Routes"] = valid_periods.groupby(peer_keys)["Route ID"].transform("size")
        valid_periods["Peer P75 Mean Lead Days"] = valid_periods.groupby(peer_keys)["Valid Mean Lead Time Days"].transform(lambda values: values.quantile(.75))
        valid_periods = valid_periods[valid_periods["Peer Routes"].ge(3)]
        found = []
        for route_id, period in valid_periods.groupby("Route ID"):
            period = period.sort_values("Quarter")
            slow = period["Valid Mean Lead Time Days"] > period["Peer P75 Mean Lead Days"]
            if len(period) >= 3 and slow.mean() >= .75 and slow.iloc[-1]:
                info = routes[routes["Route ID"].eq(route_id)].iloc[0]
                found.append({"Route ID": route_id, **{field: info[field] for field in KEYS}, "Supported Valid Quarters": len(period),
                              "Slow Valid Quarters": int(slow.sum()), "Slow Valid Quarter Share Pct": 100 * slow.mean()})
        confirmed_slow = pd.DataFrame(found, columns=slow_columns)
    if len(confirmed_slow):
        routes.loc[routes["Route ID"].isin(confirmed_slow["Route ID"]), "Slow Route Status"] = "relative_consistently_slow_valid_dates"

    exports = {"route_cluster_assignments": routes, "cluster_summary": cluster_summary,
               "cluster_selection": pd.DataFrame(geo_candidates + diag_candidates), "cluster_seed_stability": pd.DataFrame(geo_stability + diag_stability),
               "quarterly_route_performance": quarters, "region_product_summary": combinations,
               "quarterly_region_product_performance": combination_quarters, "region_product_investigation_queue": candidates,
               "sparse_routes": sparse, "unmapped_routes": uncovered, "confirmed_slow_routes": confirmed_slow}
    for name, frame in exports.items():
        frame.to_csv(OUT / f"{name}.csv", index=False, na_rep="", float_format="%.6f")
    summary = {"route_definition": KEYS, "total_routes": len(routes), "clustered_routes": len(supported),
               "records_in_clustered_routes": int(supported["Records"].sum()), "unassigned_routes": len(routes) - len(supported),
               "routes_without_coordinates": len(uncovered), "sparse_routes_under_20_records": len(sparse),
               "geographic_features": GEOGRAPHIC_FEATURES, "diagnostic_features": DIAGNOSTIC_FEATURES,
               "geographic_selected_k": int(geo_selected["K"]), "geographic_silhouette": geo_selected["Silhouette"],
               "diagnostic_selected_k": int(diag_selected["K"]), "diagnostic_silhouette": diag_selected["Silhouette"],
               "minimum_records": MIN_RECORDS, "minimum_coordinate_coverage_pct": MIN_COVERAGE * 100,
               "geographic_review_distance_cutoff_km": distance_cutoff, "region_product_investigation_candidates": len(candidates),
               "persistent_long_distance_candidates": int(candidates["Persistent Long Distance"].eq("true").sum()),
               "valid_historical_lead_time_records": int(data["Valid Historical Interval"].sum()),
               "confirmed_slow_detection_available": bool(len(valid_periods)), "confirmed_slow_routes": len(confirmed_slow),
               "source_date_offset_applied": 0, "simulated_inputs_created": False,
               "cluster_seed_stability": geo_stability + diag_stability,
               "limits": ["No confirmed slow or congested routes can be identified from the current source dates",
                          "Distance measures great-circle proximity, not road mileage, cost or transit speed",
                          "Clusters are exploratory similarity groups, not optimized factory assignments",
                          "Sparse routes and missing coordinates remain unassigned rather than imputed into clusters"]}
    (OUT / "route_analysis_summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    pd.DataFrame({"Route ID": supported["Route ID"], **{f: supported[f] for f in GEOGRAPHIC_FEATURES}}).to_csv(OUT / "geographic_cluster_inputs.csv", index=False)
    pd.DataFrame({"Route ID": supported["Route ID"], **{f: supported[f] for f in DIAGNOSTIC_FEATURES}}).to_csv(OUT / "diagnostic_cluster_inputs.csv", index=False)

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    for label, group in routes[~routes["Geographic Cluster"].eq("unassigned")].groupby("Geographic Cluster"):
        axes[0].scatter(group["Unit Weighted Distance Km"], group["Units"], s=45, alpha=.8, label=label)
    axes[0].set(xlabel="Unit-weighted great-circle distance (km)", ylabel="Route demand (units, log scale)", yscale="log", title="Geography and demand clusters")
    axes[0].legend(title="Exploratory cluster")
    for label, group in routes[~routes["Diagnostic Cluster"].eq("unassigned")].groupby("Diagnostic Cluster"):
        axes[1].scatter(group["Unit Weighted Distance Km"], group["Diagnostic Mean Interval Days"], s=45, alpha=.8, label=label)
    axes[1].set(xlabel="Unit-weighted great-circle distance (km)", ylabel="Unverified mean date interval (days)", title="DIAGNOSTIC ONLY: source-interval clusters")
    axes[1].legend(title="Diagnostic cluster")
    fig.suptitle("Route similarities | source lead times remain unverified", fontsize=15, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, .95))
    fig.savefig(OUT / "route_clusters.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(12, 6))
    top = candidates.head(8).sort_values("Distance Exposure Unit Km")
    labels = top["Product Name"].str.replace("Wonka Bar - ", "", regex=False) + " · " + top["Region"]
    ax.barh(labels, top["Distance Exposure Unit Km"] / 1e6, color="#2355a4")
    ax.set(title="Region–product combinations for geographic investigation", xlabel="Mapped demand × great-circle distance (million unit-km; geographic proxy)")
    fig.text(.5, .015, "Not confirmed slow routes, shipping costs or reassignment savings.", ha="center", color="#9d3c2b")
    fig.tight_layout(rect=(0, .05, 1, 1))
    fig.savefig(OUT / "investigation_priorities.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    for name, values in [("Geographic", geo_candidates), ("Diagnostic only", diag_candidates)]:
        ax.plot([r["K"] for r in values], [r["Silhouette"] for r in values], marker="o", label=name)
    ax.set(xlabel="Number of clusters (k)", ylabel="Silhouette score", title="Exploratory cluster selection")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "cluster_selection.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    report = f"""# Route clustering and investigation priorities

**Current data does not support confirmed slow-route or congestion claims. All source lead-time intervals are suspect. Geographic review candidates are identified below; four-feature lead-time clustering is explicitly diagnostic only.**

## Scope and population

A route is one Product ID × assigned factory × destination country × region × ship mode combination. Factory means the static product assignment, not an observed shipment origin. Country is retained to distinguish unavailable Canadian geography from mapped US ZIP centroids.

There are {len(routes)} routes. {len(supported)} have at least {MIN_RECORDS} records and {MIN_COVERAGE:.0%} coordinate coverage and are clustered, covering {int(supported['Records'].sum()):,} of {len(data):,} records. {len(uncovered)} routes lack coordinates. {len(sparse)} routes have fewer than 20 records; these categories can overlap. Unassigned routes remain in the summaries and investigation exports. No records are dropped from financial or demand totals.

## Features and method

The geographic cluster set uses unit-weighted great-circle distance, within-route distance standard deviation, and log(1 + demand units). The diagnostic set uses unit-weighted distance, mean unchanged Ship Date minus Order Date, standard deviation of that interval, and log(1 + demand units), satisfying the requested four-feature comparison without claiming verified time performance.

StandardScaler fits the selected routes, followed by KMeans with seed 42 and 20 initializations. Routes are weighted equally in clustering; demand enters as a log-transformed feature. Candidate k values 2–6 are compared with silhouette score, rejecting solutions with fewer than three routes in any cluster. These are explicit exploratory support rules, not service targets. Clusters are numbered by increasing mean geographic distance; numbers are not performance ranks.

Geographic selection: k={int(geo_selected['K'])}, silhouette={geo_selected['Silhouette']:.3f}. Diagnostic selection: k={int(diag_selected['K'])}, silhouette={diag_selected['Silhouette']:.3f}. Additional seeds 7, 101 and 2026 are compared with adjusted Rand index; this checks initialization sensitivity, not temporal generalization or proof of business outcomes.

{md_table(cluster_summary[['Cluster Set', 'Cluster', 'Routes', 'Units', 'Mean Route Distance Km', 'Mean Distance Std Km', 'Median Route Units']])}

![Route clusters](route_clusters.png)

## Region–product combinations requiring investigation

Candidates have at least 30 mapped records, at least 90% coordinate coverage, and demand-weighted distance at or above the upper quartile of supported region–product combinations ({distance_cutoff:,.1f} km). They are ranked by mapped units × great-circle distance. This geographic exposure proxy is not a transport-cost or emissions metric.

{len(candidates)} combinations meet the screen. {int(candidates['Persistent Long Distance'].eq('true').sum())} also show persistent long geographic distances: at least three quarters with five mapped records each, with distance at or above the same threshold in at least 75% of those quarters. This describes geography, not consistently slow shipping.

{md_table(candidates.head(10)[['Product Name', 'Assigned Factory', 'Region', 'Mapped Units', 'Unit Weighted Distance Km', 'Supported Geographic Quarters', 'Long Distance Quarter Share Pct']])}

![Investigation priorities](investigation_priorities.png)

Investigate freight rates, actual shipment origins, production compatibility, capacity and order-to-shipment dates for these flows. Clusters do not establish that changing factories is feasible or profitable. Sparse routes require additional observations; all Canadian routes require destination coordinates before geographic comparison.

## Consistently slow routes: unavailable

Valid historical date-interval records: {int(data['Valid Historical Interval'].sum()):,}. The confirmed-slow export is currently header-only. Its zero rows mean detection is unavailable, not that no slow routes exist. Raw means, P90 intervals and standard deviations remain diagnostic columns; no 2,000-day offset was subtracted. Delivery times cannot be measured without delivery dates.

The implemented future consistency screen requires at least 20 valid interval records per route-quarter, at least three comparable routes in the same country/ship-mode/quarter, and at least three supported quarters. A route must exceed the peer upper-quartile mean in at least 75% of those quarters and in its latest supported quarter. This would identify relative slowness, not SLA failure or congestion. It cannot run meaningfully on the current source dates.

## Outputs and reproducibility

Run `python analysis/cluster_routes.py` after preparation and cleaning, using the dependencies in `analysis/requirements-models.txt`. Outputs beside this report include route assignments, cluster summaries, silhouette comparisons, seed stability, input matrices, quarterly histories, region–product summaries and priorities, sparse/unmapped routes, and the empty confirmed-slow table. Cluster pipelines are saved in `models/route_clusters/` with explicit exploratory/diagnostic flags.

![Cluster selection](cluster_selection.png)

Source attribution and coordinate limitations are in [the dataset guide](../../datasets/DATASET_GUIDE.md); cleaning decisions are in [the cleaning report](../data_cleaning_report.md). All monetary values use source units. This is exploratory analysis of a public educational sample, not verified operational performance.
"""
    (OUT / "route_investigation_report.md").write_text(report, encoding="utf-8")
    print(json.dumps(summary, indent=2, allow_nan=False))
    print(candidates.head(8)[["Product Name", "Region", "Unit Weighted Distance Km", "Mapped Units", "Persistent Long Distance"]].to_string(index=False))


if __name__ == "__main__":
    main()
