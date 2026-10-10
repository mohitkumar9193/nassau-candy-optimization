# Cleaning and validation report

Snapshot: 2026-10-10. Reproduce from the project root with `python analysis/clean_validate_data.py`.

## Results

| Check | Result |
|---|---:|
| Original records | 10,194 |
| Primary cleaned records | 10,194 |
| Missing required cells | 0 |
| Exact duplicate occurrences removed | 0 |
| Conflicting Row IDs | 0 |
| Quarantined records | 0 |
| Invalid date cells | 0 |
| Invalid numeric cells | 0 |
| Product names standardized | 2,064 |
| Division labels corrected | 6 |
| Profit reconciliation failures | 0 |
| Negative lead-time intervals | 0 |
| Suspect long lead-time intervals | 10,194 |
| Ship dates after snapshot | 9,824 |
| Extreme outlier records, union of fields | 5 |
| Outlier sensitivity subset | 10,189 |
| Records with too little product history for product-based outlier screening | 40 |
| Historical lead-time training records | 0 |

## Cleaning decisions

Source files remain unchanged. Postal codes and identifiers remain text, including leading-zero ZIPs. Dates are validated as ISO dates. Money is parsed as finite decimals, units as positive integers, and gross profit is checked against sales minus manufacturing cost with tolerance 0.01. Negative gross profit would remain valid when the amounts reconcile. The script strips outer whitespace and recognizes explicit missing-value tokens; missing required values are quarantined instead of imputed.

Product IDs are checked against the supplied reference. Source spelling `Wonka Bar -Scrumdiddlyumptious` becomes `Wonka Bar - Scrumdiddlyumptious` in the cleaned copy. Six Fizzy Lifting Drinks records are changed from division Sugar to Other, consistent with both reference tables. Original product names and divisions remain in separate Source columns. Factory labels follow the documented aliases.

Repeated Order IDs are retained because they do not identify exact duplicate records. Only exact duplicate occurrences are removed; conflicting Row IDs require quarantine and review. Row-level decisions are in `datasets/processed/cleaning_audit.csv`.

## Date interpretation

`Order To Shipment Lead Time Days = Ship Date - Order Date`, using actual calendar-day arithmetic. The observed range is 2000–2011 days. All 10,194 intervals exceed the explicit 60-day quality screen. This systematic issue is separate from statistical outlier detection: a dataset-wide shift can pass relative IQR screening.

No 2,000-day subtraction or date correction is applied. The numeric interval is provided for traceability, but it must not be treated as verified operational performance. The training CSV currently contains a header and zero records; this is intentional, pending resolution of the source dates. This measure does not describe delivery or transit time because delivery dates are absent.

## Extreme outliers

The screen uses outer Tukey fences: below Q1 minus 3 times IQR or above Q3 plus 3 times IQR. Money and units are assessed within each product to avoid confusing differing product prices with unusual orders. Intervals are assessed within ship mode, and geographic distance within destination country. Quartiles use linear interpolation. Groups with fewer than 20 observations or zero IQR are marked unassessed; unavailable coordinates are not filled with zero.

Field-level flagged counts (a record may appear in multiple fields): {"Cost": 5}.

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
