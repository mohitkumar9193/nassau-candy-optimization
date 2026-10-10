# Streamlit dashboard validation

Validated on 2026-10-10 using Python 3.12, Streamlit 1.65.0, pandas 3.0.1,
NumPy 2.5.3, and PyArrow 25.0.1 in an isolated workspace dependency directory.

- All 24 project tests passed, including four dashboard integration tests.
- Streamlit AppTest rendered all five tabs without application exceptions.
- Product selection, region selection, 100% speed priority and strict profit policy
  reran successfully. The no-reassignment result displays an explanation and N/A
  stability/readiness metrics.
- Filtered calculations reserve full-product sample demand for capacity.
- ZIP exports were opened and inspected for CSVs, active filters, priority and
  operational-status metadata.
- A cohort with no destination coordinates is rejected with an explicit unavailable
  message instead of a zero-distance or invented performance estimate.
- The local server started on port 8501; HTTP health and app-shell checks passed.

AppTest verifies rendered elements and reruns, not browser pixel layout. No live
account deployment or production shipping validation was performed. Every operational
estimate remains assumption-based, and evidence readiness remains zero.

For a normal development environment, install `requirements.txt` and
`analysis/requirements-models.txt`, then run:

```sh
python -m unittest discover -s analysis/tests -v
```
