# Factory Reallocation & Shipping Optimization Recommendation System for Nassau Candy Distributor

An internship data analytics project to compare factory assignments, predict order-to-shipment lead times, and recommend product reassignments while considering profitability and uncertainty.

## Current status

Steps 1–4 are complete: the folder structure, public dataset, cleaning workflow, and current-performance EDA are prepared. There are 10,194 records with all 18 required fields, five factory coordinates, and 15 product assignments. Read [the dataset guide](datasets/DATASET_GUIDE.md) for sources, attribution, joins, and validation, [the cleaning report](reports/data_cleaning_report.md) for cleaning decisions, and [the performance report](reports/eda/current_performance_report.md) for findings and charts. A [self-contained HTML report](reports/eda/current_performance_report.html) is also available.

The source shipment dates have a systematic anomaly: every order-to-shipment interval is 2,000–2,011 days. Dates are preserved and flagged; no records qualify for validated historical lead-time training until the issue is resolved. No synthetic order records were created. A diagnostic-only comparison of Linear Regression, Random Forest and Gradient Boosting fits the unchanged unverified date intervals and produces no operational model. Route clustering is exploratory, and the scenario simulator uses separately documented hypothetical logistics assumptions. The Streamlit dashboard and Vercel-compatible companion are implemented. GitHub packaging, version locks, validation workflow and deployment guides are prepared. The research paper and government stakeholder executive summary are complete; account publication and operational verification remain pending.

## Project structure

```text
project-1/
├── datasets/
│   ├── raw/          # Original order data; preserve source files
│   ├── processed/    # Cleaned data and training-ready features
│   └── reference/    # Factory coordinates and product assignments
├── analysis/         # EDA, preprocessing, modeling, and scenario analysis
├── models/           # Saved models, preprocessing pipelines, and evaluation metrics
├── dashboard/        # Required Streamlit dashboard
├── reports/          # Research paper and executive summary
├── deployment/       # Hosting configuration and Vercel companion website
├── .gitignore
└── README.md
```

Empty folders contain `.gitkeep` files so GitHub preserves the structure.

## Planned workflow

1. Obtain historical orders and document their source and usage terms.
2. Add the five supplied factory locations and 15 unique product assignments.
3. Validate and clean records; calculate lead time as Ship Date minus Order Date.
4. Explore demand, shipping performance, sales, and gross profit.
5. Compare Linear Regression, Random Forest, and Gradient Boosting using RMSE, MAE, and R² on held-out data.
6. Cluster routes, simulate alternative assignments, and rank recommendations.
7. Build the dashboard and calculate the four required KPIs.
8. Write reports, validate outputs, and prepare deployment.

## Setup

Open this folder in your editor or terminal. Once the code and dependency file have been added, the intended Python setup is:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

`requirements.txt` will be created during model/dashboard implementation. The environment commands above apply at that stage. The dataset preparation script uses only Python's standard library and can run now without installing packages:

```powershell
python analysis/prepare_dataset.py
python analysis/clean_validate_data.py
```

These commands rebuild the prepared and cleaned tables from the included raw files. See the dataset guide for download and archive options. The supported Python version for the full application will be recorded after dependency validation.

## Usage

Original orders and publisher reference files are included in `datasets/raw/`; documented reference tables are in `datasets/reference/`. Use `datasets/processed/orders_cleaned.csv` as the primary EDA dataset. It retains all 10,194 records and includes canonical labels, original label columns, computed lead-time intervals, and quality flags. The separate `orders_outlier_filtered.csv` excludes five flagged cost outliers for sensitivity comparisons. `orders_lead_time_training.csv` is intentionally empty pending resolution of the date issue. Reproduce these outputs with the commands above. Subsequent analysis will write model artifacts to `models/`.

The planned dashboard entry point is `dashboard/app.py`. After it is implemented and dependencies are installed, launch it from the project root with:

```powershell
python -m streamlit run dashboard/app.py
```

Exact analysis and training commands will be documented when the corresponding scripts are available.

## Explore current performance

Install the EDA dependencies and run the analysis from the project root:

```powershell
python -m pip install -r analysis/requirements-eda.txt
python analysis/explore_performance.py
```

Outputs are in `reports/eda/`: grouped CSV summaries for products, assigned factories, regions, shipping modes, combinations and time trends; six charts; a Markdown report; a self-contained HTML report; and machine-readable metrics. Demand is measured in units. Monetary figures use source units because the source dictionary does not specify currency. Geographic summaries cover mapped US records, with coverage shown explicitly. Source date intervals appear only as quality diagnostics; verified mean lead times are unavailable.

## Prediction models: diagnostic comparison

The [model comparison report](reports/model_comparison/diagnostic/model_comparison_report.md) contains numerical/categorical feature preparation, a chronological train/validation/test split, RMSE, MAE, R², and interpretability comparisons. Initial preprocessing fits only initial training; final preprocessing fits only pretest development. Training-only outlier rules do not remove any validation or test records.

```powershell
python -m pip install -r analysis/requirements-models.txt
python analysis/train_compare_models.py --diagnostic
python -m unittest discover -s analysis/tests -v
```

Without `--diagnostic`, training refuses the current source dates and records the reason in `models/readiness.json`. Diagnostic bundles are in `models/diagnostic/` and explicitly prohibit operational use. Split assignments, held-out predictions, preprocessing statistics, coefficients/importances and the selected model's training matrix are in `reports/model_comparison/diagnostic/`. Linear Regression was selected by validation performance and interpretability. The simple ship-mode mean provides a comparable sanity baseline; these results do not establish actual shipping-speed accuracy or product reallocation effects.

## Route clustering and investigation

Run `python analysis/cluster_routes.py` with the modeling dependencies installed. [The route investigation report](reports/route_analysis/route_investigation_report.md) covers 180 route combinations: 77 sufficiently supported routes form three geographic clusters, while a separate two-cluster diagnostic comparison includes unverified lead-time intervals. Sparse routes and routes without coordinates remain unassigned.

The report identifies seven region–product combinations for geographic investigation, five with persistent long distances across quarters. Route assignments, sample support, variability, cluster selection, seed stability, quarterly histories and investigation queues are in `reports/route_analysis/`. The confirmed-slow table is intentionally empty because source dates cannot establish actual slow shipping or congestion. Geographic exposure is not a freight cost or speed estimate.

## Factory scenario simulator

The [scenario report](reports/scenario_simulator/scenario_simulator_report.md) compares all 15 products across five factories: 75 scenarios and 6,075 sensitivity cases. [Hypothetical assumptions](datasets/simulated/logistics_assumptions.json) are stored separately from original data. Estimates cover mapped sample demand and are not verified lead-time predictions, actual net profit, or feasibility approvals.

```powershell
python analysis/scenario_simulator.py
python analysis/scenario_simulator.py --product CHO-MIL-31000 --region Pacific --ship-mode "Standard Class"
```

Outputs include all factory comparisons, route-level comparisons, sensitivity grids, uncertainty flags and a chart. Alternative factory–product histories, capacity and production compatibility remain unverified. Filtered runs use separate subfolders. Edit a copy of the assumptions and pass `--assumptions path/to/file.json` to explore other parameters; each sensitivity axis must include 1.0. The pure `simulate()` function is available for dashboard integration.

## Ranked recommendations and KPIs

Run `python analysis/rank_recommendations.py --speed-priority 0.5 --top-n 3`. The [recommendation report](reports/recommendations/recommendation_report.md) defines the ranking score and four required KPIs. The default preserves base-case modeled contribution; `--profit-policy strict_all_cases` requires preservation across all tested cases, and explicit `tradeoff` mode permits modeled losses for exploration.

Ranked options, top-N candidates, a capacity-aware provisional portfolio, KPI JSON, joint sensitivity cases and five speed-priority profiles are in `reports/recommendations/`. [Constraint inputs](datasets/reference/operational_constraints.json) accept additional capacity and compatible Product IDs over the sample replay horizon. Unknown inputs stay unknown; zero capacity and empty compatibility lists block options. Portfolio capacity is rechecked jointly and released origin capacity is conservatively not reused. This is greedy provisional selection, not global optimization or deployment approval.

At the default 50/50 priority, five products are proposed for investigation: modeled dispatch reduction 4.06%, profit stability 66.67% of tested joint cases, evidence confidence 0/100, provisional coverage 33.33%, and verified coverage 0%. Assumed dispatch gains and grid-case stability are not observed shipping improvements or probabilities. Confidence measures evidence readiness and remains zero because verified outcomes, constraints and calibrated estimates are missing.

## Dashboard scope

The required [Streamlit dashboard](dashboard/app.py) is implemented. Install the root
dependencies with `python -m pip install -r requirements.txt`, then launch with
`python -m streamlit run dashboard/app.py`. See [setup and hosting instructions](deployment/STREAMLIT.md).
Five tabs cover current performance, factory simulation, ranked recommendations,
risk/impact, and downloads. Filters and the priority slider recalculate the scenarios;
optional constraint JSON is validated and enforced. CSV/JSON/ZIP downloads include
active settings and reproducibility metadata. Estimates remain explicitly hypothetical.

- Factory optimization simulator with product selection and predicted performance across factories.
- What-if analysis comparing current and recommended assignments.
- Ranked recommendations and expected efficiency gains.
- Risk and profit impact alerts.
- Product, region, and ship mode controls plus a speed-versus-profit priority slider.

## Data and interpretation

- Ship Date minus Order Date measures time until shipment, not delivery transit time.
- Any simulated logistics costs, capacities, or production compatibility inputs must be clearly labeled and documented.
- Alternative factory assignments without supporting historical observations require uncertainty flags; predictions alone do not establish operational feasibility.
- KPI formulas and assumptions will be documented alongside the analysis.
- Do not commit credentials, personal customer information, or data whose sharing terms prohibit publication.

## Deliverables and deployment

The submission includes the [research paper](reports/submission/research_paper.pdf), the implemented Streamlit analytics dashboard, and the [executive summary for government stakeholders](reports/submission/executive_summary.pdf). The paper is 11 pages and the summary is two pages. Editable Markdown sources and a document builder are in [the submission directory](reports/submission/README.md). Both PDFs distinguish observed sample findings, diagnostic model fits and hypothetical scenario estimates. They were rendered and visually inspected on every page. The companion website provides both documents as downloads.

Follow the [GitHub and deployment guide](deployment/README.md) to install exact tested dependencies, reproduce the analysis from bundled raw data, upload the project to GitHub, host `dashboard/app.py` on Streamlit Community Cloud, and host the [static companion](deployment/companion/public/index.html) on Vercel. The Vercel root is `deployment/companion`, output directory `public`, with no build/install command. Add actual public GitHub and Streamlit URLs to `deployment/companion/public/config.js` after deployment. Preserve [data attribution](ATTRIBUTION.md).

`python analysis/reproduce.py --diagnostic-models` rebuilds the full diagnostic workflow;
`python deployment/build_companion.py` refreshes presentation exports;
`python deployment/validate_package.py` checks integrity; and
`python deployment/package_project.py` creates a clean source ZIP and SHA-256 inventory.
The included GitHub Actions workflow runs validation without publishing. No remote
repository or account deployment has been created during preparation.

See [final verification results](reports/final_verification_report.md). Independent
saved-result arithmetic checks run with `python deployment/verify_analysis.py`.
