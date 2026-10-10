"""Acquire and prepare the public sample dataset using only Python's standard library.

Run from the project root: python analysis/prepare_dataset.py --download
Or pass an already downloaded ZIP: python analysis/prepare_dataset.py --archive FILE
Without either option, rebuild derived files from datasets/raw/.
"""

import argparse
import csv
import hashlib
import json
import math
import tempfile
import urllib.request
import zipfile
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "datasets"
DOWNLOAD_URL = "https://maven-datasets.s3.amazonaws.com/US+Candy+Distributor/US+Candy+Distributor.zip"
SOURCE_PAGE = "https://mavenanalytics.io/data-playground/us-candy-distributor"
SNAPSHOT_DATE = "2026-10-10"
RAW_FILES = ["Candy_Sales.csv", "Candy_Products.csv", "Candy_Factories.csv",
             "Candy_Targets.csv", "uszips.csv", "candy_distributor_data_dictionary.csv"]
FIELDS = ["Row ID", "Order ID", "Order Date", "Ship Date", "Ship Mode", "Customer ID",
          "Country/Region", "City", "State/Province", "Postal Code", "Division", "Region",
          "Product ID", "Product Name", "Sales", "Units", "Gross Profit", "Cost"]
ALIASES = {"Wonka Bar -Scrumdiddlyumptious": "Wonka Bar - Scrumdiddlyumptious",
           "Wicked Choccy's": "Wicked Chocy's"}


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def haversine(lat1, lon1, lat2, lon2):
    """Great-circle kilometres, not road distance or a shipping cost estimate."""
    a1, a2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    da = a2 - a1
    a = math.sin(da / 2) ** 2 + math.cos(a1) * math.cos(a2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def ingest_archive(path):
    # Extract only explicit CSV members; preserve original bytes and source filenames.
    with zipfile.ZipFile(path) as archive:
        for filename in RAW_FILES:
            (DATA / "raw" / filename).write_bytes(archive.read(filename))
    write_json(DATA / "source_manifest.json", {
        "retrieved_on": SNAPSHOT_DATE,
        "publisher": "Maven Analytics",
        "dataset_title": "US Candy Distributor",
        "source_page": SOURCE_PAGE,
        "download_url": DOWNLOAD_URL,
        "archive_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "orders_license": "Public Domain, as stated on the publisher's dataset page",
        "geography_attribution": "US ZIP coordinates: SimpleMaps, https://simplemaps.com/data/us-zips",
        "geography_license_note": "SimpleMaps Basic data is CC BY 4.0; preserve attribution. This is the snapshot packaged by Maven, not the current ZIP release.",
        "usage": "Public educational sample; not verified proprietary Nassau Candy operational records",
        "raw_files": {filename: {
            "sha256": hashlib.sha256((DATA / "raw" / filename).read_bytes()).hexdigest(),
            "size_bytes": (DATA / "raw" / filename).stat().st_size,
        } for filename in RAW_FILES},
        "simulated_inputs_created": False,
    })


def prepare():
    header, rows = read_csv(DATA / "raw" / "Candy_Sales.csv")
    if header != FIELDS:
        raise ValueError(f"Expected exactly the 18 assignment fields; found {header}")
    _, factories = read_csv(DATA / "reference" / "factories.csv")
    _, assignments = read_csv(DATA / "reference" / "product_factory_assignments.csv")
    _, source_products = read_csv(DATA / "raw" / "Candy_Products.csv")
    _, source_factories = read_csv(DATA / "raw" / "Candy_Factories.csv")
    if len(factories) != 5 or len(assignments) != 15:
        raise ValueError("Expected five factories and fifteen unique assignments")
    factory_lookup = {r["Factory"]: r for r in factories}
    assignment_lookup = {r["Product Name"]: r for r in assignments}
    if len(factory_lookup) != 5 or len(assignment_lookup) != 15:
        raise ValueError("Reference keys must be unique")
    for factory in source_factories:
        expected = factory_lookup[ALIASES.get(factory["Factory"], factory["Factory"])]
        for coordinate in ["Latitude", "Longitude"]:
            if Decimal(factory[coordinate]) != Decimal(expected[coordinate]):
                raise ValueError("Factory coordinates differ from assignment")
    products = []
    for source in source_products:
        name = ALIASES.get(source["Product Name"], source["Product Name"])
        assignment = assignment_lookup[name]
        if ALIASES.get(source["Factory"], source["Factory"]) != assignment["Factory"]:
            raise ValueError(f"Factory mismatch: {name}")
        if source["Division"] != assignment["Division"]:
            raise ValueError(f"Division mismatch: {name}")
        products.append({"Product ID": source["Product ID"], "Product Name": name,
                         "Division": assignment["Division"], "Factory": assignment["Factory"],
                         "Unit Price": source["Unit Price"], "Unit Cost": source["Unit Cost"],
                         "Source Product Name": source["Product Name"],
                         "Source Factory": source["Factory"], "Is Simulated": "false"})
    product_lookup = {r["Product ID"]: r for r in products}
    if len(product_lookup) != 15:
        raise ValueError("Expected fifteen unique source product IDs")
    write_csv(DATA / "reference" / "products.csv", list(products[0]), products)
    write_csv(DATA / "reference" / "name_aliases.csv", ["Source Name", "Canonical Name", "Reason"],
              [{"Source Name": k, "Canonical Name": v, "Reason": "Align source spelling with supplied assignment"}
               for k, v in ALIASES.items()])

    _, zip_rows = read_csv(DATA / "raw" / "uszips.csv")
    zip_lookup = {r["zip"]: r for r in zip_rows}
    if len(zip_lookup) != len(zip_rows):
        raise ValueError("Ambiguous ZIP lookup")
    # Postal codes remain strings; no Canadian postal code is joined to a US ZIP.
    destination_fields = ["Country/Region", "Postal Code", "Destination Latitude", "Destination Longitude",
                          "Coordinate Status", "Coordinate Source", "Is Simulated"]
    destinations = {}
    enriched, leads, issues = [], [], []
    missing = Counter()
    duplicate_ids = Counter(r["Row ID"] for r in rows)
    monetary_mismatches = 0
    for row in rows:
        missing.update(k for k, v in row.items() if not v.strip())
        product = product_lookup[row["Product ID"]]
        if ALIASES.get(row["Product Name"], row["Product Name"]) != product["Product Name"]:
            raise ValueError(f"Product ID/name mismatch at row {row['Row ID']}")
        division_mismatch = row["Division"] != product["Division"]
        if division_mismatch:
            issues.append({"Row ID": row["Row ID"], "Issue": "Division differs from product reference",
                           "Value": row["Division"], "Action": "Preserved source Division; Canonical Division comes from product reference"})
        factory = factory_lookup[product["Factory"]]
        lead = (date.fromisoformat(row["Ship Date"]) - date.fromisoformat(row["Order Date"])).days
        leads.append(lead)
        suspect = lead < 0 or lead > 60  # Screening rule; never changes dates or removes rows.
        future = row["Ship Date"] > SNAPSHOT_DATE
        if suspect:
            issues.append({"Row ID": row["Row ID"], "Issue": "Suspect order-to-shipment date interval",
                           "Value": str(lead), "Action": "Preserved; exclude from historical lead-time training pending resolution"})
        profit_delta = Decimal(row["Sales"]) - Decimal(row["Cost"]) - Decimal(row["Gross Profit"])
        monetary_mismatches += abs(profit_delta) > Decimal("0.01")
        key = (row["Country/Region"], row["Postal Code"])
        if key not in destinations:
            geo = zip_lookup.get(key[1]) if key[0] == "United States" else None
            mapped = bool(geo and geo["lat"] and geo["lng"])
            destinations[key] = {"Country/Region": key[0], "Postal Code": key[1],
                                 "Destination Latitude": geo["lat"] if mapped else "",
                                 "Destination Longitude": geo["lng"] if mapped else "",
                                 "Coordinate Status": "matched_us_zip_centroid" if mapped else "unavailable",
                                 "Coordinate Source": "SimpleMaps via Maven ZIP snapshot" if mapped else "",
                                 "Is Simulated": "false"}
        destination = destinations[key]
        distance = ""
        if destination["Coordinate Status"] == "matched_us_zip_centroid":
            distance = f"{haversine(float(factory['Latitude']), float(factory['Longitude']), float(destination['Destination Latitude']), float(destination['Destination Longitude'])):.3f}"
        enriched.append({**row, "Canonical Product Name": product["Product Name"],
                         "Canonical Division": product["Division"], "Division Reference Mismatch": str(division_mismatch).lower(),
                         "Assigned Factory": factory["Factory"], "Factory Assignment Source": "Static product reference; not an observed shipment origin",
                         "Factory Latitude": factory["Latitude"], "Factory Longitude": factory["Longitude"],
                         "Destination Latitude": destination["Destination Latitude"],
                         "Destination Longitude": destination["Destination Longitude"],
                         "Coordinate Status": destination["Coordinate Status"],
                         "Great Circle Distance Km": distance, "Observed Date Interval Days": str(lead),
                         "Lead Time Quality": "suspect_date_interval" if suspect else "passes_interval_screen",
                         "Ship Date After Snapshot": str(future).lower(),
                         "Eligible For Lead Time Training": str(not suspect and not future).lower(),
                         "Is Simulated": "false"})

    write_csv(DATA / "processed" / "orders_18_fields.csv", FIELDS, rows)
    write_csv(DATA / "processed" / "orders_enriched.csv", list(enriched[0]), enriched)
    write_csv(DATA / "reference" / "destinations.csv", destination_fields,
              [destinations[k] for k in sorted(destinations)])
    write_csv(DATA / "processed" / "data_quality_issues.csv", ["Row ID", "Issue", "Value", "Action"], issues)
    dictionary_header, dictionary = read_csv(DATA / "raw" / "candy_distributor_data_dictionary.csv")
    write_csv(DATA / "reference" / "order_data_dictionary.csv", dictionary_header,
              [r for r in dictionary if r["Table"] == "Sales"])
    summary = {
        "snapshot_date": SNAPSHOT_DATE, "rows": len(rows), "required_fields": len(header),
        "unique_products": len({r["Product ID"] for r in rows}), "factories": len(factories),
        "unique_order_id_values": len({r["Order ID"] for r in rows}),
        "repeated_order_id_rows": len(rows) - len({r["Order ID"] for r in rows}),
        "duplicate_row_id_rows": sum(n - 1 for n in duplicate_ids.values()),
        "exact_duplicate_rows": len(rows) - len({tuple(r.values()) for r in rows}),
        "missing_required_cells": dict(missing), "gross_profit_reconciliation_failures": monetary_mismatches,
        "division_reference_mismatch_rows": sum(r["Division Reference Mismatch"] == "true" for r in enriched),
        "order_date_range": [min(r["Order Date"] for r in rows), max(r["Order Date"] for r in rows)],
        "ship_date_range": [min(r["Ship Date"] for r in rows), max(r["Ship Date"] for r in rows)],
        "observed_date_interval_days_range": [min(leads), max(leads)],
        "suspect_date_interval_rows": sum(r["Lead Time Quality"] == "suspect_date_interval" for r in enriched),
        "eligible_for_lead_time_training_rows": sum(r["Eligible For Lead Time Training"] == "true" for r in enriched),
        "mapped_destination_rows": sum(bool(r["Great Circle Distance Km"]) for r in enriched),
        "unmapped_destination_rows": sum(not r["Great Circle Distance Km"] for r in enriched),
        "countries": dict(Counter(r["Country/Region"] for r in rows)),
        "sales_total": str(sum(Decimal(r["Sales"]) for r in rows)),
        "gross_profit_total": str(sum(Decimal(r["Gross Profit"]) for r in rows)),
        "units_total": sum(int(r["Units"]) for r in rows),
        "simulated_inputs_created": False, "source_dates_modified": False, "rows_removed": 0,
        "screening_rule": "Intervals below 0 or above 60 days are suspect; future ship dates also excluded from historical training",
        "historical_origin_limit": "Factory is assigned from a static product table; no observed alternative product-factory history",
    }
    write_json(DATA / "validation_summary.json", summary)
    write_json(DATA / "missing_operational_inputs.json", {
        "simulated_inputs_created": False,
        "unavailable": ["Verified order-to-shipment dates", "Delivery dates and transit durations",
                        "Observed shipment-origin factories", "Alternative product-factory outcome history",
                        "Factory capacities", "Production compatibility", "Shipping tariffs and actual logistics costs",
                        "Reassignment costs", "Canadian destination coordinates"],
        "policy": "Unavailable inputs are not zero. Any future demo assumptions must be stored separately, labeled simulated, and excluded from claims about real business performance.",
    })
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--download", action="store_true")
    group.add_argument("--archive", type=Path)
    args = parser.parse_args()
    for folder in ["raw", "processed", "reference"]:
        (DATA / folder).mkdir(parents=True, exist_ok=True)
    if args.download:
        with tempfile.TemporaryDirectory() as temporary:
            archive_path = Path(temporary) / "us-candy-distributor.zip"
            with urllib.request.urlopen(DOWNLOAD_URL, timeout=120) as response:
                archive_path.write_bytes(response.read())
            ingest_archive(archive_path)
    elif args.archive:
        ingest_archive(args.archive)
    prepare()


if __name__ == "__main__":
    main()
