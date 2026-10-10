# Final verification and upload package

Verified on 10 October 2026 using Python 3.12 and the pinned local dependencies.

## Results

| Check | Result |
|---|---|
| Automated tests | All 24 passed in 20.598 seconds |
| Source calculations | All 10,194 rows reconciled; sales 141,783.63, gross profit 93,442.80 and units 38,654 |
| Chronological evaluation | 6,519 training / 1,632 validation / 2,043 test records; dates and order IDs do not cross partitions |
| Preprocessing | Independently checked fit counts, training medians, scaler means and categorical vocabularies |
| Test metrics | Independently recomputed RMSE, MAE and R² for all three models and the ship-mode sanity baseline |
| Scenario calculations | Independently recomputed geographic distances, dispatch and base contribution for 75 pairs, plus 6,075 financial sensitivity cases |
| Ranking and KPIs | All 75 scores and the selected portfolio's dispatch reduction, coverage, contribution and joint downside/stability reconciled |
| Constraints | Tests cover capacity, production compatibility, full-product demand reservations, strict protection, uncertainty and no-move states |
| Dashboard | AppTest exercised five tabs, product/region/ship-mode filters, speed priority, top-N, grouping and strict protection; export metadata and ZIP tested |
| Companion | Regenerated 15 product comparisons and six resources; JavaScript interactions, unavailable-data state and configured links passed |
| Local static hosting | All 12 public resources returned HTTP 200 with byte-identical contents; temporary server stopped |
| Submission documents | Source totals, model results, scenario KPIs and 11-page paper / two-page summary reconciled; every page previously rendered and visually inspected |
| Deployment package | Raw data hashes, local links, copied resources, snapshot KPIs, dependency pins and hosting configuration passed |

Independent arithmetic checks are reproducible with `python deployment/verify_analysis.py`.
Run `python -m unittest discover -s analysis/tests -v` for behavioral tests and
`python deployment/validate_package.py` for package integrity. GitHub Actions includes
these commands. The SHA-256 inventory and archive checksum are regenerated when packaging.

## Interpretation and remaining hosting checks

The unmodified source dates imply 2,000–2,011 days between order and shipment.
They are not verified operational lead times. No date offset or operational model
was introduced. Diagnostic metrics describe that source interval only. All logistics,
dispatch and reassignment estimates remain explicitly hypothetical.

The default provisional portfolio proposes five investigations, with 4.0619% modeled
dispatch reduction, +977.6832 source monetary units of base contribution, 66.6667%
nonnegative joint sensitivity cases and a -4,090.6936 worst-case contribution change.
Evidence readiness and verified recommendation coverage remain zero. These are
neither demonstrated savings nor approved factory changes.

The companion is static: its Vercel configuration deliberately skips build/install
commands and serves `public/`. Local generation, configuration and HTTP checks passed.
No remote GitHub Actions run, clean Linux installation, Streamlit hosting build or
Vercel account deployment has been executed. Add the actual public URLs after hosting.
Browser pixel layout, phone-width layout and production security-header enforcement
remain post-deployment checks in `deployment/README.md`.

The first dashboard test attempt stalled in Windows asyncio's local socket creation
under network sandboxing. After loopback access was granted, all tests passed; no
application workaround was needed.
