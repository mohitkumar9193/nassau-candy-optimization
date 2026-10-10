"""Reproduce current-performance EDA: python analysis/explore_performance.py.

Install analysis/requirements-eda.txt first. Uses primary cleaned data, including
flagged but potentially valid large orders. Outputs CSV summaries, charts and reports.
"""

import base64
import html
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "eda"
FIG = OUT / "figures"
TABLES = OUT / "tables"
BLUE, TEAL, ORANGE = "#2355a4", "#148677", "#d67b26"


def summarize(data, keys):
    records = []
    overall_units = data["Units"].sum()
    overall_sales = data["Sales"].sum()
    for group, rows in data.groupby(keys, sort=True, dropna=False):
        if not isinstance(group, tuple):
            group = (group,)
        mapped = rows[rows["Great Circle Distance Km"].notna()]
        valid = rows[rows["Lead Time Quality"].eq("passes_interval_screen") & ~rows["Ship Date After Snapshot"]]
        sales, profit, units = rows["Sales"].sum(), rows["Gross Profit"].sum(), rows["Units"].sum()
        intervals = rows["Order To Shipment Lead Time Days"]
        weighted_distance = np.average(mapped["Great Circle Distance Km"], weights=mapped["Units"]) if len(mapped) else np.nan
        records.append({**dict(zip(keys, group)), "Records": len(rows),
                        "Distinct Source Order IDs": rows["Order ID"].nunique(),
                        "Units": units, "Demand Share Pct": 100 * units / overall_units,
                        "Sales": sales, "Sales Share Pct": 100 * sales / overall_sales,
                        "Manufacturing Cost": rows["Cost"].sum(), "Gross Profit": profit,
                        "Gross Margin Pct": 100 * profit / sales if sales else np.nan,
                        "Gross Profit Per Unit": profit / units if units else np.nan,
                        "Mapped Records": len(mapped), "Mapped Record Coverage Pct": 100 * len(mapped) / len(rows),
                        "Mapped Units": mapped["Units"].sum(), "Mapped Unit Coverage Pct": 100 * mapped["Units"].sum() / units,
                        "Mean Great Circle Km": mapped["Great Circle Distance Km"].mean(),
                        "Median Great Circle Km": mapped["Great Circle Distance Km"].median(),
                        "P90 Great Circle Km": mapped["Great Circle Distance Km"].quantile(.90),
                        "Unit Weighted Great Circle Km": weighted_distance,
                        "Distance Exposure Unit Km": (mapped["Great Circle Distance Km"] * mapped["Units"]).sum() if len(mapped) else np.nan,
                        "Diagnostic Mean Date Interval Days": intervals.mean(),
                        "Diagnostic Median Date Interval Days": intervals.median(),
                        "Diagnostic P90 Date Interval Days": intervals.quantile(.90),
                        "Suspect Date Interval Records": (~rows["Lead Time Quality"].eq("passes_interval_screen")).sum(),
                        "Valid Historical Lead Time Records": len(valid),
                        "Verified Mean Lead Time Days": valid["Order To Shipment Lead Time Days"].mean(),
                        "Flagged Extreme Outlier Records": rows["Extreme Outlier"].sum(),
                        "Group Sample Support": "fewer than 20 records" if len(rows) < 20 else "20 or more records"})
    result = pd.DataFrame(records)
    if len(result):
        result = result.sort_values("Sales", ascending=False).reset_index(drop=True)
    return result


def save_chart(fig, name):
    fig.savefig(FIG / name, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return name


def money(value):
    return f"{value:,.2f}"


def markdown_table(frame, columns):
    view = frame[columns].copy()
    for column in columns:
        if pd.api.types.is_numeric_dtype(view[column]):
            view[column] = view[column].map(lambda x: "unavailable" if pd.isna(x) else f"{x:,.2f}" if isinstance(x, float) else f"{x:,}")
    rows = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    rows += ["| " + " | ".join(str(x).replace("|", "\\|") for x in row) + " |" for row in view.itertuples(index=False, name=None)]
    return "\n".join(rows)


def main():
    for folder in [OUT, FIG, TABLES]:
        folder.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(ROOT / "datasets" / "processed" / "orders_cleaned.csv",
                       dtype={"Row ID": str, "Order ID": str, "Customer ID": str, "Postal Code": str, "Product ID": str})
    for field in ["Sales", "Units", "Gross Profit", "Cost", "Great Circle Distance Km", "Order To Shipment Lead Time Days"]:
        data[field] = pd.to_numeric(data[field], errors="raise")
    for field in ["Extreme Outlier", "Ship Date After Snapshot"]:
        if not pd.api.types.is_bool_dtype(data[field]):
            data[field] = data[field].astype(str).str.lower().map({"true": True, "false": False})
        if data[field].isna().any():
            raise ValueError(f"Unrecognized Boolean: {field}")
    data["Order Date"] = pd.to_datetime(data["Order Date"], errors="raise")
    data["Year"] = data["Order Date"].dt.year
    data["Month"] = data["Order Date"].dt.strftime("%Y-%m")
    groupings = {
        "product": ["Product ID", "Product Name", "Division", "Assigned Factory"],
        "factory": ["Assigned Factory"], "region": ["Region"], "ship_mode": ["Ship Mode"],
        "division": ["Division"], "country": ["Country/Region"],
        "factory_region": ["Assigned Factory", "Region"], "product_region": ["Product ID", "Product Name", "Region"],
        "region_ship_mode": ["Region", "Ship Mode"], "factory_ship_mode": ["Assigned Factory", "Ship Mode"],
        "product_ship_mode": ["Product ID", "Product Name", "Ship Mode"],
        "year": ["Year"], "month": ["Month"],
    }
    summaries = {name: summarize(data, keys) for name, keys in groupings.items()}
    routes = summarize(data, ["Product ID", "Product Name", "Assigned Factory", "Region", "Ship Mode"])
    routes = routes.sort_values("Distance Exposure Unit Km", ascending=False, na_position="last").reset_index(drop=True)
    summaries["route_performance"] = routes
    summaries["geographic_review_priorities"] = routes[routes["Mapped Records"] >= 30].head(20).copy()
    for name, frame in summaries.items():
        frame.to_csv(TABLES / f"{name}_summary.csv", index=False, float_format="%.6f", na_rep="")
    mapped = data[data["Great Circle Distance Km"].notna()]
    chocolate = data[data["Division"].eq("Chocolate")]
    totals = {
        "records": len(data), "distinct_source_order_id_values": data["Order ID"].nunique(),
        "units": int(data["Units"].sum()), "sales": round(float(data["Sales"].sum()), 2),
        "manufacturing_cost": round(float(data["Cost"].sum()), 2), "gross_profit": round(float(data["Gross Profit"].sum()), 2),
        "gross_margin_pct": float(100 * data["Gross Profit"].sum() / data["Sales"].sum()),
        "chocolate_units_share_pct": float(100 * chocolate["Units"].sum() / data["Units"].sum()),
        "chocolate_sales_share_pct": float(100 * chocolate["Sales"].sum() / data["Sales"].sum()),
        "mapped_records": len(mapped), "unmapped_records": len(data) - len(mapped),
        "mapped_record_coverage_pct": 100 * len(mapped) / len(data),
        "mapped_unit_coverage_pct": float(100 * mapped["Units"].sum() / data["Units"].sum()),
        "mean_great_circle_km": float(mapped["Great Circle Distance Km"].mean()),
        "unit_weighted_great_circle_km": float(np.average(mapped["Great Circle Distance Km"], weights=mapped["Units"])),
        "p90_great_circle_km": float(mapped["Great Circle Distance Km"].quantile(.90)),
        "suspect_lead_time_records": int((~data["Lead Time Quality"].eq("passes_interval_screen")).sum()),
        "valid_historical_lead_time_records": int((data["Lead Time Quality"].eq("passes_interval_screen") & ~data["Ship Date After Snapshot"]).sum()),
        "verified_mean_lead_time_days": None,
        "currency": "source monetary units; currency unspecified in source dictionary",
        "analysis_population": "primary cleaned data, including five flagged cost outliers",
        "factory_basis": "static product assignments, not observed shipment origins",
        "distance_basis": "great-circle distance to US ZIP centroid; not road distance",
        "python_libraries": {"pandas": pd.__version__, "numpy": np.__version__, "matplotlib": matplotlib.__version__},
    }
    sensitivity = data[~data["Extreme Outlier"]]
    comparisons = []
    for metric in ["Sales", "Gross Profit", "Cost", "Units"]:
        full, filtered = data[metric].sum(), sensitivity[metric].sum()
        comparisons.append({"Metric": metric, "Primary Total": full, "Outlier Filtered Total": filtered,
                            "Difference": filtered - full, "Change Pct": 100 * (filtered - full) / full})
    comparisons = pd.DataFrame(comparisons)
    comparisons.to_csv(TABLES / "outlier_sensitivity.csv", index=False, float_format="%.6f")
    (OUT / "performance_metrics.json").write_text(json.dumps(totals, indent=2) + "\n", encoding="utf-8")

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.titleweight": "bold", "axes.titlesize": 12})
    charts = []
    fig, axes = plt.subplots(2, 2, figsize=(13, 8.5))
    factory = summaries["factory"].sort_values("Units")
    axes[0, 0].barh(factory["Assigned Factory"], factory["Units"], color=BLUE)
    axes[0, 0].set(title="Demand by assigned factory", xlabel="Units")
    region = summaries["region"].sort_values("Sales")
    axes[0, 1].barh(region["Region"], region["Sales"], color=TEAL)
    axes[0, 1].set(title="Sales by destination region", xlabel="Source monetary units")
    mode = summaries["ship_mode"].sort_values("Records")
    axes[1, 0].barh(mode["Ship Mode"], mode["Records"], color=BLUE)
    axes[1, 0].set(title="Shipping mode mix", xlabel="Records (not distinct orders)")
    axes[1, 1].barh(factory["Assigned Factory"], factory["Unit Weighted Great Circle Km"], color=ORANGE)
    axes[1, 1].set(title="Demand-weighted geographic distance", xlabel="Great-circle km; mapped US records only")
    fig.suptitle("Nassau Candy project | current sample performance", fontsize=17, fontweight="bold")
    fig.text(.5, .01, "2021–2024 orders • Static factory assignments • Gross profit excludes freight • Lead times unresolved", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .04, 1, .95))
    charts.append(save_chart(fig, "performance_overview.png"))

    product = summaries["product"].sort_values("Sales")
    labels = product["Product Name"].str.replace("Wonka Bar - ", "", regex=False)
    fig, axes = plt.subplots(1, 2, figsize=(13, 8))
    y = np.arange(len(product))
    axes[0].barh(y + .18, product["Sales"], height=.35, label="Sales", color=BLUE)
    axes[0].barh(y - .18, product["Gross Profit"], height=.35, label="Gross profit", color=TEAL)
    axes[0].set_yticks(y, labels)
    axes[0].set(title="Product sales and gross profit", xlabel="Source monetary units")
    axes[0].legend(loc="lower right")
    axes[1].barh(y, product["Gross Margin Pct"], color=TEAL)
    axes[1].set_yticks(y, labels)
    axes[1].set(title="Gross margin by product", xlabel="Gross profit / sales (%)", xlim=(0, 100))
    fig.suptitle("Product mix and profitability | all 15 products", fontsize=16, fontweight="bold")
    fig.tight_layout()
    charts.append(save_chart(fig, "product_profitability.png"))

    fr = summaries["factory_region"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for ax, metric, title, cmap in [(axes[0], "Units", "Demand (units)", "Blues"),
                                    (axes[1], "Unit Weighted Great Circle Km", "Demand-weighted great-circle km", "YlOrBr")]:
        pivot = fr.pivot(index="Assigned Factory", columns="Region", values=metric).sort_index()
        image = ax.imshow(pivot.to_numpy(), cmap=cmap, aspect="auto")
        ax.set_xticks(range(len(pivot.columns)), pivot.columns)
        ax.set_yticks(range(len(pivot.index)), pivot.index)
        ax.set_title(title)
        for i in range(len(pivot.index)):
            for j in range(len(pivot.columns)):
                v = pivot.iloc[i, j]
                ax.text(j, i, "n.a." if pd.isna(v) else f"{v:,.0f}", ha="center", va="center", fontsize=9,
                        color="white" if pd.notna(v) and v > np.nanmax(pivot.to_numpy()) * .65 else "#18243a")
        fig.colorbar(image, ax=ax, shrink=.7)
    fig.suptitle("Assigned factory × region | distance covers mapped US demand", fontsize=15, fontweight="bold")
    fig.tight_layout()
    charts.append(save_chart(fig, "factory_region_comparison.png"))

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    axes[0].hist(mapped["Great Circle Distance Km"], bins=30, color=BLUE, edgecolor="white")
    axes[0].set(title="Record-level distance distribution", xlabel="Great-circle km", ylabel="Mapped US records")
    sample = [mapped.loc[mapped["Assigned Factory"].eq(name), "Great Circle Distance Km"].to_numpy() for name in factory["Assigned Factory"]]
    axes[1].boxplot(sample, orientation="horizontal", tick_labels=factory["Assigned Factory"], showfliers=False)
    axes[1].set(title="Distance spread by assigned factory", xlabel="Great-circle km; box plots omit displayed fliers")
    fig.tight_layout()
    charts.append(save_chart(fig, "geographic_distances.png"))

    monthly = summaries["month"].sort_values("Month")
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
    axes[0].plot(monthly["Month"], monthly["Sales"], color=BLUE, label="Sales", linewidth=2)
    axes[0].plot(monthly["Month"], monthly["Gross Profit"], color=TEAL, label="Gross profit", linewidth=2)
    axes[0].set(title="Monthly sales and gross profit by order date", ylabel="Source monetary units")
    axes[0].legend()
    axes[1].bar(monthly["Month"], monthly["Units"], color=BLUE)
    axes[1].set(title="Monthly demand", ylabel="Units", xlabel="Order month")
    axes[1].set_xticks(np.arange(0, len(monthly), 3), monthly["Month"].iloc[::3], rotation=45, ha="right")
    fig.tight_layout()
    charts.append(save_chart(fig, "monthly_performance.png"))

    ordered_modes = ["Same Day", "First Class", "Second Class", "Standard Class"]
    diagnostic = summaries["ship_mode"].set_index("Ship Mode").loc[ordered_modes]
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar(ordered_modes, diagnostic["Diagnostic Mean Date Interval Days"], color="#b45b46")
    ax.set(title="Date-quality diagnostic: source intervals are suspect for every mode", ylabel="Mean Ship Date − Order Date (days)", ylim=(0, 2300))
    for i, v in enumerate(diagnostic["Diagnostic Mean Date Interval Days"]):
        ax.text(i, v + 35, f"{v:,.2f}", ha="center")
    fig.text(.5, .02, "Not verified lead-time performance. No assumed 2,000-day correction was applied.", ha="center", color="#9d3c2b")
    fig.tight_layout(rect=(0, .06, 1, 1))
    charts.append(save_chart(fig, "lead_time_quality_diagnostic.png"))

    leader = summaries["region"].iloc[0]
    factory_leader = summaries["factory"].iloc[0]
    highest_product = summaries["product"].iloc[0]
    focus = summaries["factory_region"].query('`Mapped Records` >= 30').sort_values("Distance Exposure Unit Km", ascending=False).head(5)
    weakest = summaries["product"].sort_values("Gross Margin Pct").iloc[0]
    years = summaries["year"].sort_values("Year")
    first, last = years.iloc[0], years.iloc[-1]
    growth = 100 * (last["Sales"] / first["Sales"] - 1)
    narrative = [
        f"The sample contains {totals['records']:,} records, {totals['units']:,} units, sales of {money(totals['sales'])}, and gross profit of {money(totals['gross_profit'])} in source monetary units. Aggregate gross margin is {totals['gross_margin_pct']:.2f}%. Gross profit excludes shipping and reassignment costs.",
        f"Chocolate contributes {totals['chocolate_units_share_pct']:.2f}% of demand and {totals['chocolate_sales_share_pct']:.2f}% of sales. Prioritizing this division for further geographic analysis covers most of the sample's demand.",
        f"{factory_leader['Assigned Factory']} accounts for {factory_leader['Units']:,.0f} units and {money(factory_leader['Sales'])} sales. These totals reflect the static product assignment table, not observed factory output or capacity utilization.",
        f"{leader['Region']} is the largest sales region: {money(leader['Sales'])}, or {leader['Sales Share Pct']:.2f}% of sample sales. {highest_product['Product Name']} has the highest product sales at {money(highest_product['Sales'])}.",
        f"{weakest['Product Name']} has the lowest observed gross margin ({weakest['Gross Margin Pct']:.2f}%). Any future reassignment scenario needs careful cost sensitivity; no freight expense or feasible reassignment has yet been established.",
        f"US ZIP coordinates cover {totals['mapped_record_coverage_pct']:.2f}% of records and {totals['mapped_unit_coverage_pct']:.2f}% of units. Mean mapped distance is {totals['mean_great_circle_km']:,.1f} km; unit-weighted distance is {totals['unit_weighted_great_circle_km']:,.1f} km. All 200 Canadian records remain in financial and demand totals but are excluded from distance calculations.",
        f"Sample sales increased from {money(first['Sales'])} in {int(first['Year'])} to {money(last['Sales'])} in {int(last['Year'])} ({growth:.2f}% across those calendar-year samples). This is descriptive; it does not establish cause or completeness of source business coverage.",
        f"There are {totals['valid_historical_lead_time_records']:,} valid historical lead-time records. The 2,000–2,011-day source intervals are reported only as date-quality diagnostics. Mode labels and relative intervals do not justify measured shipping-service rankings or speed gains.",
    ]
    lead_text = """Every product, factory, region, and ship-mode summary includes suspect-interval counts, diagnostic interval statistics, and valid historical counts. Verified mean lead time is blank when no valid historical records exist. A blank is unavailable, not zero days. No delivery-time, on-time-rate, congestion or causal factory-speed claim can be calculated from these dates.

Distance exposure equals the sum of units × great-circle distance over mapped records. It is a geographic review proxy, not vehicle kilometres, transport work, cost or emissions. Routes with at least 30 mapped records are listed as geographic review candidates; this threshold is an explicit sample-support screen, not proof of operational feasibility. No alternative factories or savings are recommended at this EDA stage."""
    sections = [
        ("Product performance", summaries["product"], ["Product Name", "Records", "Units", "Sales", "Gross Profit", "Gross Margin Pct"]),
        ("Assigned factory performance", summaries["factory"], ["Assigned Factory", "Records", "Units", "Sales", "Gross Profit", "Unit Weighted Great Circle Km"]),
        ("Regional performance", summaries["region"], ["Region", "Units", "Sales", "Gross Profit", "Gross Margin Pct", "Unit Weighted Great Circle Km"]),
        ("Shipping modes", summaries["ship_mode"], ["Ship Mode", "Records", "Units", "Sales", "Gross Profit", "Valid Historical Lead Time Records"]),
        ("Geographic review candidates", focus, ["Assigned Factory", "Region", "Mapped Records", "Mapped Units", "Unit Weighted Great Circle Km", "Distance Exposure Unit Km"]),
        ("Yearly performance", years, ["Year", "Records", "Units", "Sales", "Gross Profit", "Gross Margin Pct"]),
        ("Outlier sensitivity", comparisons, list(comparisons.columns)),
    ]
    report = "# Current performance analysis\n\nOrder-date sample: 2021-01-03 to 2024-12-30. Analysis uses the full cleaned dataset.\n\n## Findings\n\n"
    report += "\n\n".join(narrative) + "\n\n## Lead times and geographic interpretation\n\n" + lead_text + "\n\n"
    for title, frame, columns in sections:
        report += f"## {title}\n\n" + markdown_table(frame, columns) + "\n\n"
    report += "## Charts\n\n" + "\n\n".join(f"![{name.replace('_', ' ').replace('.png', '')}](figures/{name})" for name in charts)
    report += "\n\n## Method and reproducibility\n\nDemand is measured in units; Records counts rows, while Distinct Source Order IDs counts unique IDs within each group. Do not sum group-specific distinct-ID counts to recover the overall count. Shares use the full sample denominator. Margins are ratios of total gross profit to total sales, not averages of record percentages. Distance means and percentiles use available US coordinates only; unit-weighted means weight each mapped record by units. Monetary amounts are source units, with currency unspecified. Sparse product groups are retained and identified, not extrapolated into confident operational recommendations.\n\n"
    report += "The five cost-outlier records remain in primary totals. The optional sensitivity table shows the effect of excluding them; it is not the default business population. Geographic exposure and static factory assignments cannot measure factory congestion or capacity.\n\n"
    report += "Reproduce with `python -m pip install -r analysis/requirements-eda.txt`, then `python analysis/explore_performance.py`. Summary CSVs are in `reports/eda/tables/`; exact machine-readable metrics and library versions are in `reports/eda/performance_metrics.json`. The preparation and cleaning scripts should be run first if source inputs change. See [the dataset guide](../../datasets/DATASET_GUIDE.md) and [cleaning report](../data_cleaning_report.md) for source attribution and quality rules.\n"
    (OUT / "current_performance_report.md").write_text(report, encoding="utf-8")

    # Self-contained HTML: charts are embedded, so this file can be shared independently.
    pieces = ['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Nassau Candy | Current performance</title><style>body{font:16px/1.6 system-ui,sans-serif;margin:0;background:#f2f5fa;color:#17243a}main{max-width:1200px;margin:auto;padding:36px 24px}h1{font-size:34px;line-height:1.2}h2{margin-top:36px;color:#2355a4}.notice{padding:18px 22px;background:#fff3e8;border-left:5px solid #d67b26;border-radius:8px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px;margin:24px 0}.card{background:white;padding:18px;border-radius:12px}.card strong{display:block;font-size:25px}.table{overflow-x:auto}table{border-collapse:collapse;background:white;width:100%;font-size:13px}td,th{padding:10px;border-bottom:1px solid #e4eaf2;text-align:right}td:first-child,th:first-child{text-align:left}img{display:block;width:100%;height:auto;background:white;border-radius:12px;margin:24px 0}.muted{color:#58667a}@media print{body{background:white}main{padding:0}img{break-inside:avoid}}</style></head><body><main>']
    pieces += ['<h1>Nassau Candy project<br>Current performance analysis</h1><p class="muted">Public educational sample • 2021–2024 order dates • Static factory assignments</p>',
               '<div class="notice"><strong>Lead-time quality issue:</strong> all source intervals are 2,000–2,011 days. Verified shipping lead times are unavailable. Financial and geographic analysis remains usable within the documented sample limits.</div>']
    pieces.append('<div class="cards">' + ''.join(f'<div class="card">{html.escape(label)}<strong>{value}</strong></div>' for label, value in [
        ("Units", f"{totals['units']:,}"), ("Sales · source units", money(totals["sales"])),
        ("Gross profit · source units", money(totals["gross_profit"])), ("Gross margin", f"{totals['gross_margin_pct']:.2f}%"),
        ("Mapped record coverage", f"{totals['mapped_record_coverage_pct']:.2f}%")]) + '</div>')
    pieces.append('<h2>Findings</h2>' + ''.join(f'<p>{html.escape(text)}</p>' for text in narrative))
    for name in charts:
        encoded = base64.b64encode((FIG / name).read_bytes()).decode("ascii")
        pieces.append(f'<img alt="{html.escape(name.replace("_", " "))}" src="data:image/png;base64,{encoded}">')
    pieces.append('<h2>Lead times and geography</h2>' + ''.join(f'<p>{html.escape(text)}</p>' for text in lead_text.split("\n\n")))
    for title, frame, columns in sections:
        pieces.append(f'<h2>{html.escape(title)}</h2><div class="table">' + frame[columns].to_html(index=False, border=0, float_format=lambda x: f"{x:,.2f}", na_rep="unavailable", escape=True) + '</div>')
    pieces.append('<h2>Sources and interpretation</h2><p>Orders: <a href="https://mavenanalytics.io/data-playground/us-candy-distributor">Maven Analytics US Candy Distributor</a> (publisher labels Public Domain). ZIP centroid coordinates: <a href="https://simplemaps.com/data/us-zips">SimpleMaps</a> via the Maven archive, with attribution under CC BY 4.0. This sample is not verified proprietary Nassau Candy operational data. Factory coordinates and assignments also match the supplied internship reference tables.</p><p>Demand uses units. Gross margin uses total gross profit divided by total sales. Distances cover mapped US records only and use ZIP centroids; they are not road distances. Dates remain unchanged. Review the accompanying Markdown report, CSV tables, dataset guide and cleaning audit for reproducibility and limitations.</p></main></body></html>')
    (OUT / "current_performance_report.html").write_text("\n".join(pieces), encoding="utf-8")
    print(json.dumps(totals, indent=2))
    print(f"Created {len(summaries) + 1} CSV tables, {len(charts)} charts, Markdown report and self-contained HTML report.")


if __name__ == "__main__":
    main()
