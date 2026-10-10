# Submission documents

- `research_paper.pdf`: 11-page applied research paper covering provenance, cleaning,
  EDA, chronological diagnostic model comparison, route clustering, scenario formulas,
  ranking/KPI definitions, sensitivity, recommendations, limitations and references.
- `executive_summary.pdf`: 2-page decision summary for government stakeholders.
- Matching `.md` files are editable text versions. Keep their `figures/` folder with
  the research paper source for image links.
- `build_documents.py` is the reproducible authoring source. It reads the completed
  CSV/JSON exports for tables and figures and checks key snapshot invariants before
  building. Substantive findings are authored for the current analysis snapshot;
  review and update narrative claims if source data or assumptions change.

The conclusions distinguish sample financial and geographic observations from
diagnostic fits to anomalous date intervals and explicitly hypothetical dispatch/
logistics scenarios. Reassignment proposals remain investigation options with zero
evidence readiness. No official company endorsement or government policy evaluation
is claimed.

Rebuild from the repository root using Python 3.12:

```sh
python -m pip install -r deployment/requirements-documents.txt
python reports/submission/build_documents.py
python deployment/build_companion.py
python deployment/validate_package.py
python deployment/package_project.py
```

Windows fonts are embedded when available; other platforms use ReportLab's standard
Times and Helvetica fonts. Typography may differ, so inspect regenerated PDFs before
submission. The final PDFs were rendered and all pages visually inspected. QA page
images are excluded from the source package.
