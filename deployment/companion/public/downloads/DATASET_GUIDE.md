# Dataset guide

Prepared on 10 October 2026 for the Nassau Candy internship assignment.

## Source and attribution

Orders and source reference tables come from Maven Analytics' [US Candy Distributor](https://mavenanalytics.io/data-playground/us-candy-distributor), a public educational sample. The publisher labels the dataset Public Domain. This project does not claim the sample represents verified real Nassau Candy operational records.

The downloaded archive is [US Candy Distributor ZIP](https://maven-datasets.s3.amazonaws.com/US+Candy+Distributor/US+Candy+Distributor.zip). The exact download URL, retrieval date, archive hash, and original-file SHA-256 hashes are recorded in `source_manifest.json`. The archive link was discovered through a public article linking to Maven's bucket; the files were downloaded directly from that bucket. No third-party analysis or application code was copied.

ZIP centroid coordinates are provided by [SimpleMaps](https://simplemaps.com/data/us-zips) through the Maven archive. SimpleMaps lists its Basic dataset under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Preserve this attribution when publishing the data or dashboard. This project uses the packaged historical snapshot, not a current geography download. Derived destination coordinates and distances retain that source attribution.

Factory coordinates and current product assignments in `reference/factories.csv` and `reference/product_factory_assignments.csv` were transcribed from the user's assignment screenshots. All five coordinates and 15 assignments agree with the downloaded source tables after the documented spelling aliases.

## Files

| File | Purpose |
|---|---|
| `raw/Candy_Sales.csv` | Original downloaded bytes: 10,194 records and exactly 18 fields |
| `raw/Candy_Products.csv` | Source product IDs, names, assignments, unit prices and unit costs |
| `raw/Candy_Factories.csv` | Source factory names and coordinates |
| `raw/Candy_Targets.csv` | Supplemental source division targets; not a factory-capacity table |
| `raw/uszips.csv` | Packaged US ZIP geography snapshot |
| `raw/candy_distributor_data_dictionary.csv` | Publisher's original dictionary |
| `processed/orders_18_fields.csv` | CSV with consistent record delimiters; all 18 source values preserved |
| `processed/orders_enriched.csv` | Original fields plus canonical labels, reference joins, distances and quality flags |
| `processed/data_quality_issues.csv` | Row-level issues and handling decisions |
| `reference/factories.csv` | Five supplied factory coordinates, provenance, and simulation flags |
| `reference/product_factory_assignments.csv` | Fifteen unique supplied product assignments |
| `reference/products.csv` | Source product IDs and prices joined to the supplied canonical assignments |
| `reference/name_aliases.csv` | Explicit source-to-assignment spelling mappings |
| `reference/destinations.csv` | Unique country/postal-code keys with matched coordinates or unavailable status |
| `reference/order_data_dictionary.csv` | Dictionary for the 18 required fields |
| `validation_summary.json` | Counts, coverage, reconciliation checks and limitations |
| `missing_operational_inputs.json` | Inputs still unavailable for operational recommendations |

All postal codes and identifiers must be read as text. US ZIPs such as `02908` retain leading zeros. Canadian values are source postal prefixes, not complete address-level coordinates.

## Required fields

Each source row is an order record containing a product. `Row ID` is unique in this snapshot. `Order ID` repeats: there are 8,549 distinct values and 1,645 repeated-ID rows. Do not deduplicate on `Order ID` alone. The assignment's dictionary describes it as unique, but that is not true in the downloaded records; its exact transaction grain needs confirmation.

| Field | Interpretation | Read as |
|---|---|---|
| Row ID | Unique record identifier | Text |
| Order ID | Source order identifier; repeats in this snapshot | Text |
| Order Date | Date order was placed | ISO date |
| Ship Date | Source shipment date; currently suspect | ISO date |
| Ship Mode | Shipping service category | Category |
| Customer ID | Customer identifier | Text |
| Country/Region | Destination country | Category |
| City | Destination city | Text |
| State/Province | Destination state or province | Category |
| Postal Code | Destination ZIP/postal prefix | Text |
| Division | Source product division | Category |
| Region | Source destination region | Category |
| Product ID | Join key to products | Text |
| Product Name | Source product label | Text |
| Sales | Source monetary sales amount for the record | Decimal |
| Units | Units on the record | Integer |
| Gross Profit | Sales minus manufacturing cost | Decimal |
| Cost | Source manufacturing cost | Decimal |

Monetary values are preserved without currency conversion. The source dictionary does not specify currency; report in source monetary units unless a currency assumption is explicitly documented. Gross profit is not profit after shipping expenses.

## Derived fields and joins

The enriched file retains the original 18 columns and adds:

- `Canonical Product Name`, `Canonical Division`, and `Division Reference Mismatch`: reference-based labels and a mismatch flag. Original labels remain intact.
- `Assigned Factory` and `Factory Assignment Source`: static product assignment, not proof of a shipment's actual origin.
- `Factory Latitude` and `Factory Longitude`: supplied coordinates.
- `Destination Latitude`, `Destination Longitude`, and `Coordinate Status`: exact country/postal-code lookup to the US ZIP snapshot. Canadian coordinates remain blank. ZIP centroids approximate destinations, not customer addresses.
- `Great Circle Distance Km`: Haversine distance using mean Earth radius 6,371.0088 km, rounded to three decimals. This is not road distance, transit time, or shipping cost. Unavailable coordinates produce blank distances, not zeros.
- `Observed Date Interval Days`: calendar days between the unchanged source dates.
- `Lead Time Quality`: intervals below 0 or above 60 days are screened as suspect. The 60-day threshold is an explicitly chosen data-quality screen, not an established service target.
- `Ship Date After Snapshot`: shipment date after 10 October 2026.
- `Eligible For Lead Time Training`: false for suspect intervals or future shipment dates.
- `Is Simulated`: false; no synthetic records or assumed operational measurements were created.

Name aliases normalize `Wicked Choccy's` to the screenshot's `Wicked Chocy's` and add a space after the hyphen in `Wonka Bar -Scrumdiddlyumptious`. Product joins use source Product ID, with name agreement validated. Duplicate reference keys cause preparation to fail rather than silently multiplying records.

## Validation and known issues

| Check | Result |
|---|---:|
| Records retained | 10,194 |
| Required fields | 18 |
| Unique products / factories | 15 / 5 |
| Missing required cells | 0 |
| Duplicate Row IDs / exact duplicate rows | 0 / 0 |
| Gross profit reconciliation failures, tolerance 0.01 | 0 |
| Division-reference mismatches | 6 |
| US records with ZIP coordinates | 9,994 |
| Canadian records without coordinates | 200 |
| Suspect date-interval records | 10,194 |
| Historical lead-time training eligible records | 0 |

Order dates span 2021-01-03 to 2024-12-30. Ship dates span 2026-06-30 to 2030-06-28. Every observed date interval is between 2,000 and 2,011 days. A second public copy at [Suhani810/Candy_Sales](https://github.com/Suhani810/Candy_Sales/blob/main/Candy_Sales.csv) was downloaded for comparison and is byte-identical to Maven's sales file. It does not resolve the anomaly.

Subtracting 2,000 days would create plausible-looking values, but there is no verified evidence that this is the intended correction. No dates have been corrected. Do not train or report historical shipping-time performance from these intervals until dates are verified. Any later offset-based demonstration must be separately labeled as an assumed scenario, never presented as corrected historical fact. Order-to-shipment time also does not measure delivery transit time.

Six Fizzy Lifting Drinks records use Division `Sugar`, while both reference tables classify the product as `Other`. The source values are retained; `Canonical Division` uses `Other`, with the mismatch flagged. No records or extreme outliers have been removed at this stage.

Static assignments give each product only one factory. Alternative product-factory effects cannot be established from these records alone. Capacity, manufacturing compatibility, actual freight costs and reassignment costs are missing. Profit sensitivity or risk calculations that later use assumptions must expose those assumptions and their uncertainty.

## Reproduce

Python's standard library is sufficient for this dataset step. From the project root:

```powershell
# Rebuild derived tables from the included original CSV files (offline).
python analysis/prepare_dataset.py

# Download the publisher archive again and rebuild (requires internet).
python analysis/prepare_dataset.py --download

# Or use an existing archive.
python analysis/prepare_dataset.py --archive "path/to/US Candy Distributor.zip"
```

These commands regenerate dataset outputs and validation metadata. A fresh download can change the snapshot; compare hashes and review the validation output. The prepared snapshot date and screening rules are explicit constants in the script. The source manifest is created only when ingesting an archive, so an offline rebuild does not falsely claim a new retrieval.

## Cleaning stage

Run `python analysis/clean_validate_data.py` after dataset preparation. For subsequent EDA, use `processed/orders_cleaned.csv`, which retains the original dates and amounts, standardizes product names, corrects the six documented division mismatches, and adds `Order To Shipment Lead Time Days` plus outlier and date-quality flags. Original product and division labels remain in separate Source columns; the original 18-field export and raw source files remain unchanged.

See [the cleaning report](../reports/data_cleaning_report.md) for the outlier method, validation results, audit files, and optional sensitivity subset. `processed/orders_lead_time_training.csv` is header-only because all source lead-time intervals fail the date-quality screen.
