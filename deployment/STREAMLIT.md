# Run and host the required dashboard

From the project root, use Python 3.12 to match the tested dependency lock:

```sh
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run dashboard/app.py
```

Open the local URL printed by Streamlit, usually http://localhost:8501.
For macOS/Linux activate with `source .venv/bin/activate`.

Commit the entire project, including processed orders and reference/simulated JSON files,
to GitHub. In Streamlit Community Cloud, select that repository and set the main file
to `dashboard/app.py`. Dependencies are installed from the root `requirements.txt`.
The application resolves file paths relative to its source, so it can be launched
from another directory. No secrets or credentials are needed.

The required Python dashboard uses suitable Streamlit hosting. The implemented static
Vercel companion links to it once the actual public URL is set in `companion/public/config.js`.
No account deployment is performed by this setup.

Official hosting references: [repository layout](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization),
[dependencies](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies),
and [deployment steps](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy).

## Usage

Select a product, destination region and shipping mode. Adjust speed priority and
profit protection. Inspect the current-performance, factory-simulator, ranked-options,
risk and download tabs. ZIP downloads contain CSVs and metadata with every active
filter, assumption, constraint, policy and KPI.

Optional capacity/compatibility inputs use the downloadable JSON template. Capacity
means **additional units beyond baseline over the full 2021–2024 sample**. Null means
unknown, zero forbids additional capacity, and an empty compatible-product list
forbids all products. Verified flags require documented source references. Invalid
uploads display an error. Even with filters, capacity reserves full sample demand
for each proposed whole-product move; profit gains refer only to the selected mapped
cohort and do not represent the full-product business case.

All estimates are hypothetical. Source shipment dates remain anomalous, inferred
current factory assignments are not observed origins, alternative outcome history
is absent, and evidence readiness remains zero. The simulator uses no diagnostic
regression model for operational decisions.
