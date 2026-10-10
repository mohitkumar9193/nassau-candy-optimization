"""Clean and validate the included order snapshot without changing source files.

Run: python analysis/clean_validate_data.py
Outputs: cleaned orders, outlier sensitivity subset, valid lead-time training subset,
quarantine, row audit, threshold table, JSON summary and Markdown report.
No third-party dependencies are required.
"""

import csv
import json
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from prepare_dataset import ALIASES, DATA, FIELDS, ROOT, SNAPSHOT_DATE, haversine, read_csv, write_csv, write_json

MISSING_TOKENS = {"", "na", "n/a", "null", "none", "nan"}
NUMERIC = ["Sales", "Units", "Gross Profit", "Cost"]
SHIPPING_MODES = {"Standard Class", "Second Class", "First Class", "Same Day"}
MIN_OUTLIER_GROUP = 20
DATE_SCREEN_DAYS = 60
AUDIT_FIELDS = ["Source Record Number", "Row ID", "Field", "Issue", "Original Value", "Cleaned Value", "Action"]
EXTRA_FIELDS = ["Source Product Name", "Source Division", "Assigned Factory", "Factory Assignment Source",
                "Factory Latitude", "Factory Longitude", "Destination Latitude", "Destination Longitude",
                "Coordinate Status", "Great Circle Distance Km", "Order To Shipment Lead Time Days",
                "Lead Time Quality", "Ship Date After Snapshot", "Extreme Outlier", "Outlier Fields",
                "Product Outlier Assessment", "Eligible For Lead Time Training", "Is Simulated"]


def quantile(values, fraction):
    """Linear interpolation between sorted observations (equivalent to type-7 quantiles)."""
    values = sorted(values)
    position = (len(values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def record(audit, number, row_id, field, issue, original, cleaned, action):
    audit.append(dict(zip(AUDIT_FIELDS, [number, row_id, field, issue, original, cleaned, action])))


def run():
    header, source = read_csv(DATA / "raw" / "Candy_Sales.csv")
    if header != FIELDS:
        raise ValueError("Source schema does not match the 18 required fields")
    _, product_rows = read_csv(DATA / "reference" / "products.csv")
    _, factory_rows = read_csv(DATA / "reference" / "factories.csv")
    _, destination_rows = read_csv(DATA / "reference" / "destinations.csv")
    products = {r["Product ID"]: r for r in product_rows}
    factories = {r["Factory"]: r for r in factory_rows}
    destinations = {(r["Country/Region"], r["Postal Code"]): r for r in destination_rows}
    if len(products) != len(product_rows) or len(factories) != len(factory_rows) or len(destinations) != len(destination_rows):
        raise ValueError("Reference keys must be unique")

    id_versions = defaultdict(set)
    for original in source:
        id_versions[original["Row ID"].strip()].add(tuple(original[f] for f in FIELDS))
    conflicting_ids = {key for key, values in id_versions.items() if len(values) > 1}
    seen = set()
    cleaned, audit, quarantine = [], [], []
    missing = Counter({f: 0 for f in FIELDS})
    counters = Counter()
    for number, original in enumerate(source, 1):
        if set(original) != set(FIELDS) or any(v is None for v in original.values()):
            raise ValueError(f"Malformed CSV at source record {number}")
        row = {k: v.strip() for k, v in original.items()}
        row_id = row["Row ID"]
        errors = []
        for field in FIELDS:
            if original[field] != row[field]:
                record(audit, number, row_id, field, "Outer whitespace removed", original[field], row[field], "Normalized")
                counters["whitespace_cells_normalized"] += 1
            if row[field].lower() in MISSING_TOKENS:
                missing[field] += 1
                errors.append(f"Missing {field}")
        if row_id in conflicting_ids:
            errors.append("Conflicting records share Row ID")
        fingerprint = tuple(row[f] for f in FIELDS)
        if fingerprint in seen and row_id not in conflicting_ids:
            counters["exact_duplicate_rows_removed"] += 1
            record(audit, number, row_id, "Row", "Exact duplicate", "", "", "Duplicate occurrence excluded; first retained")
            continue
        seen.add(fingerprint)
        dates = {}
        for field in ["Order Date", "Ship Date"]:
            try:
                dates[field] = date.fromisoformat(row[field])
            except ValueError:
                errors.append(f"Invalid ISO date: {field}")
                counters["invalid_date_cells"] += 1
        values = {}
        for field in NUMERIC:
            try:
                value = Decimal(row[field])
                if not value.is_finite():
                    raise InvalidOperation
                values[field] = value
                if field == "Units" and (value != value.to_integral_value() or value <= 0):
                    errors.append("Units must be a positive integer")
                if field in {"Sales", "Cost"} and value < 0:
                    errors.append(f"Negative {field} requires review")
            except InvalidOperation:
                errors.append(f"Invalid numeric value: {field}")
                counters["invalid_numeric_cells"] += 1
        if set(values) == set(NUMERIC):
            if abs(values["Sales"] - values["Cost"] - values["Gross Profit"]) > Decimal("0.01"):
                errors.append("Gross Profit does not reconcile to Sales minus Cost")
                counters["profit_reconciliation_failures"] += 1
        if row["Ship Mode"] not in SHIPPING_MODES:
            errors.append("Unrecognized ship mode")
        product = products.get(row["Product ID"])
        if product is None:
            errors.append("Unrecognized Product ID")
        elif ALIASES.get(row["Product Name"], row["Product Name"]) != product["Product Name"]:
            errors.append("Product ID/name conflict")
        if errors:
            quarantine.append({**original, "Source Record Number": number, "Quarantine Reasons": "; ".join(errors)})
            for error in errors:
                record(audit, number, row_id, "Row", error, "", "", "Quarantined; source preserved")
            continue

        row["Source Product Name"] = original["Product Name"]
        row["Source Division"] = original["Division"]
        for field in ["Product Name", "Division"]:
            if row[field] != product[field]:
                record(audit, number, row_id, field, "Aligned with product reference", row[field], product[field], "Corrected in cleaned copy")
                counters["product_names_standardized" if field == "Product Name" else "division_labels_corrected"] += 1
                row[field] = product[field]
        # Decimal formatting is deterministic; identifiers and postal codes remain strings.
        for field in NUMERIC:
            row[field] = str(int(values[field])) if field == "Units" else format(values[field], "f")
        factory = factories[product["Factory"]]
        geo = destinations.get((row["Country/Region"], row["Postal Code"]))
        lat = geo["Destination Latitude"] if geo else ""
        lon = geo["Destination Longitude"] if geo else ""
        distance = ""
        if lat and lon:
            distance = f"{haversine(float(factory['Latitude']), float(factory['Longitude']), float(lat), float(lon)):.3f}"
        lead = (dates["Ship Date"] - dates["Order Date"]).days
        suspect = lead < 0 or lead > DATE_SCREEN_DAYS
        future = dates["Ship Date"] > date.fromisoformat(SNAPSHOT_DATE)
        quality = "negative_interval" if lead < 0 else "suspect_long_interval" if suspect else "passes_interval_screen"
        if suspect:
            record(audit, number, row_id, "Ship Date", "Suspect order-to-shipment interval", row["Ship Date"], row["Ship Date"], "Date retained; excluded from historical lead-time training")
        row.update({"Assigned Factory": factory["Factory"],
                    "Factory Assignment Source": "Static product reference; not an observed shipment origin",
                    "Factory Latitude": factory["Latitude"], "Factory Longitude": factory["Longitude"],
                    "Destination Latitude": lat, "Destination Longitude": lon,
                    "Coordinate Status": "matched_us_zip_centroid" if distance else "unavailable",
                    "Great Circle Distance Km": distance,
                    "Order To Shipment Lead Time Days": str(lead), "Lead Time Quality": quality,
                    "Ship Date After Snapshot": str(future).lower(), "Is Simulated": "false"})
        cleaned.append(row)

    # Contextual screening prevents expensive products being flagged merely for their prices.
    specs = [(f, "Product ID") for f in NUMERIC] + [
        ("Order To Shipment Lead Time Days", "Ship Mode"), ("Great Circle Distance Km", "Country/Region")]
    thresholds, flags = [], defaultdict(list)
    for field, group_field in specs:
        groups = defaultdict(list)
        for index, row in enumerate(cleaned):
            if row[field] != "":
                groups[row[group_field]].append((index, float(row[field])))
        for group, observations in sorted(groups.items()):
            sufficient = len(observations) >= MIN_OUTLIER_GROUP
            if sufficient:
                values = [value for _, value in observations]
                q1, q3 = quantile(values, 0.25), quantile(values, 0.75)
                iqr = q3 - q1
                lower, upper = q1 - 3 * iqr, q3 + 3 * iqr
                # A constant middle distribution supplies no useful IQR scale.
                assessable = iqr > 0
            else:
                q1 = q3 = iqr = lower = upper = None
                assessable = False
            count = 0
            if assessable:
                for index, value in observations:
                    if value < lower or value > upper:
                        flags[index].append(field)
                        count += 1
                        record(audit, "", cleaned[index]["Row ID"], field, "Outside 3-IQR outer fences", cleaned[index][field], cleaned[index][field], "Retained in primary data; excluded from outlier sensitivity subset")
            thresholds.append({"Field": field, "Group Field": group_field, "Group": group, "Sample Size": len(observations),
                               "Assessment Status": "assessed" if assessable else "insufficient_sample" if not sufficient else "zero_iqr",
                               "Q1": q1 if q1 is not None else "", "Q3": q3 if q3 is not None else "",
                               "IQR": iqr if iqr is not None else "", "Lower Fence": lower if lower is not None else "",
                               "Upper Fence": upper if upper is not None else "", "Outlier Rows": count})
    product_counts = Counter(r["Product ID"] for r in cleaned)
    for index, row in enumerate(cleaned):
        row["Extreme Outlier"] = str(bool(flags[index])).lower()
        row["Outlier Fields"] = "; ".join(flags[index])
        row["Product Outlier Assessment"] = "assessed" if product_counts[row["Product ID"]] >= MIN_OUTLIER_GROUP else "insufficient_sample"
        row["Eligible For Lead Time Training"] = str(
            row["Lead Time Quality"] == "passes_interval_screen" and row["Ship Date After Snapshot"] == "false" and not flags[index]
        ).lower()
    fields = FIELDS + EXTRA_FIELDS
    sensitivity = [r for r in cleaned if r["Extreme Outlier"] == "false"]
    training = [r for r in cleaned if r["Eligible For Lead Time Training"] == "true"]
    processed = DATA / "processed"
    write_csv(processed / "orders_cleaned.csv", fields, cleaned)
    write_csv(processed / "orders_outlier_filtered.csv", fields, sensitivity)
    write_csv(processed / "orders_lead_time_training.csv", fields, training)
    write_csv(processed / "orders_quarantined.csv", FIELDS + ["Source Record Number", "Quarantine Reasons"], quarantine)
    write_csv(processed / "cleaning_audit.csv", AUDIT_FIELDS, audit)
    write_csv(processed / "outlier_thresholds.csv", list(thresholds[0]) if thresholds else ["Field"], thresholds)
    summary = {
        "snapshot_date": SNAPSHOT_DATE, "source_rows": len(source), "cleaned_rows": len(cleaned),
        "quarantined_rows": len(quarantine), "exact_duplicate_rows_removed": counters["exact_duplicate_rows_removed"],
        "conflicting_row_ids": len(conflicting_ids), "missing_cells_by_required_field": dict(missing),
        "invalid_date_cells": counters["invalid_date_cells"], "invalid_numeric_cells": counters["invalid_numeric_cells"],
        "product_names_standardized": counters["product_names_standardized"],
        "division_labels_corrected": counters["division_labels_corrected"],
        "profit_reconciliation_failures": counters["profit_reconciliation_failures"],
        "negative_lead_time_rows": sum(r["Lead Time Quality"] == "negative_interval" for r in cleaned),
        "suspect_long_lead_time_rows": sum(r["Lead Time Quality"] == "suspect_long_interval" for r in cleaned),
        "future_ship_date_rows": sum(r["Ship Date After Snapshot"] == "true" for r in cleaned),
        "lead_time_days_min": min(int(r["Order To Shipment Lead Time Days"]) for r in cleaned) if cleaned else None,
        "lead_time_days_max": max(int(r["Order To Shipment Lead Time Days"]) for r in cleaned) if cleaned else None,
        "extreme_outlier_rows": len(cleaned) - len(sensitivity), "outlier_filtered_rows": len(sensitivity),
        "extreme_outlier_counts_by_field": dict(Counter(field for fields_ in flags.values() for field in fields_)),
        "product_outlier_insufficient_sample_rows": sum(r["Product Outlier Assessment"] == "insufficient_sample" for r in cleaned),
        "lead_time_training_rows": len(training), "source_dates_changed": 0,
        "original_fields_preserved_in_raw_files": True, "simulated_inputs_created": False,
        "cleaned_sales_total": str(sum(Decimal(r["Sales"]) for r in cleaned)),
        "cleaned_gross_profit_total": str(sum(Decimal(r["Gross Profit"]) for r in cleaned)),
        "cleaned_units_total": sum(int(r["Units"]) for r in cleaned),
        "rules": {"outliers": "Outside Q1-3*IQR or Q3+3*IQR; linear-interpolated quartiles; minimum 20 observations; zero-IQR groups not assessed",
                  "grouping": "Money and units within Product ID; lead-time intervals within Ship Mode; distance within country",
                  "outlier_handling": "Primary cleaned data retains flagged rows; separate filtered dataset is for sensitivity comparisons, not default business totals",
                  "dates": "Actual calendar-day Ship Date minus Order Date; screen intervals below 0 or above 60 days; never subtract an assumed offset",
                  "missing": "Missing required inputs are quarantined without imputation; geography blanks remain unavailable",
                  "duplicates": "Remove exact duplicate occurrences only; quarantine conflicting Row IDs; retain repeated Order IDs"},
    }
    write_json(DATA / "cleaning_validation_summary.json", summary)
    report = f"""# Cleaning and validation report

Snapshot: {SNAPSHOT_DATE}. Reproduce from the project root with `python analysis/clean_validate_data.py`.

## Results

| Check | Result |
|---|---:|
| Original records | {len(source):,} |
| Primary cleaned records | {len(cleaned):,} |
| Missing required cells | {sum(missing.values()):,} |
| Exact duplicate occurrences removed | {counters['exact_duplicate_rows_removed']:,} |
| Conflicting Row IDs | {len(conflicting_ids):,} |
| Quarantined records | {len(quarantine):,} |
| Invalid date cells | {counters['invalid_date_cells']:,} |
| Invalid numeric cells | {counters['invalid_numeric_cells']:,} |
| Product names standardized | {counters['product_names_standardized']:,} |
| Division labels corrected | {counters['division_labels_corrected']:,} |
| Profit reconciliation failures | {counters['profit_reconciliation_failures']:,} |
| Negative lead-time intervals | {summary['negative_lead_time_rows']:,} |
| Suspect long lead-time intervals | {summary['suspect_long_lead_time_rows']:,} |
| Ship dates after snapshot | {summary['future_ship_date_rows']:,} |
| Extreme outlier records, union of fields | {summary['extreme_outlier_rows']:,} |
| Outlier sensitivity subset | {len(sensitivity):,} |
| Records with too little product history for product-based outlier screening | {summary['product_outlier_insufficient_sample_rows']:,} |
| Historical lead-time training records | {len(training):,} |

## Cleaning decisions

Source files remain unchanged. Postal codes and identifiers remain text, including leading-zero ZIPs. Dates are validated as ISO dates. Money is parsed as finite decimals, units as positive integers, and gross profit is checked against sales minus manufacturing cost with tolerance 0.01. Negative gross profit would remain valid when the amounts reconcile. The script strips outer whitespace and recognizes explicit missing-value tokens; missing required values are quarantined instead of imputed.

Product IDs are checked against the supplied reference. Source spelling `Wonka Bar -Scrumdiddlyumptious` becomes `Wonka Bar - Scrumdiddlyumptious` in the cleaned copy. Six Fizzy Lifting Drinks records are changed from division Sugar to Other, consistent with both reference tables. Original product names and divisions remain in separate Source columns. Factory labels follow the documented aliases.

Repeated Order IDs are retained because they do not identify exact duplicate records. Only exact duplicate occurrences are removed; conflicting Row IDs require quarantine and review. Row-level decisions are in `datasets/processed/cleaning_audit.csv`.

## Date interpretation

`Order To Shipment Lead Time Days = Ship Date - Order Date`, using actual calendar-day arithmetic. The observed range is {summary['lead_time_days_min']}–{summary['lead_time_days_max']} days. All {summary['suspect_long_lead_time_rows']:,} intervals exceed the explicit 60-day quality screen. This systematic issue is separate from statistical outlier detection: a dataset-wide shift can pass relative IQR screening.

No 2,000-day subtraction or date correction is applied. The numeric interval is provided for traceability, but it must not be treated as verified operational performance. The training CSV currently contains a header and zero records; this is intentional, pending resolution of the source dates. This measure does not describe delivery or transit time because delivery dates are absent.

## Extreme outliers

The screen uses outer Tukey fences: below Q1 minus 3 times IQR or above Q3 plus 3 times IQR. Money and units are assessed within each product to avoid confusing differing product prices with unusual orders. Intervals are assessed within ship mode, and geographic distance within destination country. Quartiles use linear interpolation. Groups with fewer than 20 observations or zero IQR are marked unassessed; unavailable coordinates are not filled with zero.

Field-level flagged counts (a record may appear in multiple fields): {json.dumps(summary['extreme_outlier_counts_by_field'], sort_keys=True)}.

Thresholds, group sizes, assessment status and counts are recorded in `datasets/processed/outlier_thresholds.csv`. Flagged values are not automatically errors. The primary cleaned dataset retains them so demand and financial totals remain representative. A separate outlier-filtered subset supports sensitivity comparisons; do not use it as the default EDA population. Training eligibility also excludes flagged extremes, but model-specific outlier thresholds must later be fitted on training data only to prevent evaluation leakage.

## Outputs

- `datasets/processed/orders_cleaned.csv`: primary analysis dataset, normalized labels and calculated lead-time fields.
- `datasets/processed/orders_outlier_filtered.csv`: optional sensitivity subset; statistical flags excluded.
- `datasets/processed/orders_lead_time_training.csv`: only records passing date and outlier screens; currently empty.
- `datasets/processed/orders_quarantined.csv`: invalid or conflicting records; currently header-only if no defects require quarantine.
- `datasets/processed/cleaning_audit.csv`: individual issues and changes.
- `datasets/processed/outlier_thresholds.csv`: transparent group-specific screening thresholds.
- `datasets/cleaning_validation_summary.json`: machine-readable validation results.

Public sample origin, attribution, reference joins and additional data limitations are documented in [the dataset guide](../datasets/DATASET_GUIDE.md). Sales, product mix, profit and geographic EDA can proceed; verified shipping-performance modeling requires resolving the date issue.
"""
    (ROOT / "reports" / "data_cleaning_report.md").write_text(report, encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    run()
