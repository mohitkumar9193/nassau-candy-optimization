# GitHub and deployment readiness

Prepared and verified on 2026-10-10.

## Ready to upload

- Clean source ZIP, per-file SHA-256 inventory and archive checksum.
- Python 3.12 hint, exact tested dashboard/analysis dependency versions, and a
  one-command offline reproduction workflow using the bundled original source files.
- Six original raw-file hash checks and data/attribution documentation.
- Git attributes preserve file bytes across Windows/Linux clones.
- GitHub Actions workflow runs the analytics/dashboard suite and package integrity
  validation. Its remote Linux execution is pending the first GitHub push.
- Required Streamlit dashboard with root configuration and deployment instructions.
- Static Vercel companion with exported scenario snapshot, 15 product comparisons,
  methodology, working-report downloads and source attribution.

## Verification completed

The source ZIP was extracted into an independent workspace directory. The entire
workflow was rebuilt from raw data, including explicitly requested diagnostic models,
route clustering, scenarios, rankings and companion resources. It completed successfully.
The regenerated KPI JSON matches every saved KPI and setting. All 24 project tests
passed in the extracted directory, and its package integrity validation passed.

Companion JavaScript syntax and interactions were checked against its actual exported
data: all 15 product comparisons, KPI formatting, public-link configuration and the
unavailable-data state passed. The local server returned HTTP 200 for the page, JSON,
CSS, JavaScript and analysis-report resources. A browser engine was unavailable for
pixel/layout QA; phone-width and keyboard checks remain part of the post-deployment
verification guide. No browser engine was installed solely for this preparation.

The version locks describe the actual tested dependency closure and contain no
unsatisfied active requirements in the local environment. They are version pins,
not wheel hashes. A completely new Linux dependency installation has not been run
locally; GitHub Actions and the hosting build will validate that platform.

## Account-specific next steps

1. Upload the inner `project-1/` contents to the author's GitHub repository.
2. Deploy `dashboard/app.py` to Streamlit Community Cloud using Python 3.12.
3. Set the actual public dashboard and GitHub URLs in the companion `config.js`.
4. Deploy Vercel with root `deployment/companion`, output `public`, and skipped
   build/install commands.
5. Follow the post-deployment checks in `deployment/README.md`.

This preparation did not create a remote repository or publish to either account.
The research paper and government-stakeholder executive summary are completed in
`reports/submission/` and included in the companion downloads. Current shipping
estimates remain hypothetical; the zero evidence-readiness
score and date-quality limitations are preserved in both applications.
