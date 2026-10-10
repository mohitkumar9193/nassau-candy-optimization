# GitHub and deployment guide

The repository root is the **contents of `project-1/`**, not its parent output folder.
The required Python dashboard and the static presentation site are separate deployments
from the same repository. This preparation has not created a remote repository or
published either application.

## Reproduce locally

Use Python **3.12**, matching the tested environment. From the project root:

```sh
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r deployment/requirements-analysis-lock.txt
python -m unittest discover -s analysis/tests -v
python deployment/validate_package.py
python analysis/reproduce.py --diagnostic-models
python -m streamlit run dashboard/app.py
```

The reproduction command uses bundled raw source files without downloading them.
It regenerates dataset joins, cleaning, EDA, diagnostic model comparisons, route
clustering, scenarios, rankings and the static companion snapshot. Random seeds and
chronological model splits are fixed in the analysis scripts. Model numbers can vary
slightly across platforms; no model is approved for operational use. Omit
`--diagnostic-models` to skip recreating the diagnostic artifacts.

Root `requirements.txt` installs the exact dashboard lock. The analysis lock adds
the exact tested modeling dependencies. These are version pins, not a hash-locked
wheel distribution; installations still resolve platform-specific wheels from PyPI.
The package inventory hashes project files and the original data manifest hashes
source bytes. Local dependency directories and environments are excluded from the ZIP.
`.gitattributes` preserves file bytes across clones so Git line-ending conversion
does not invalidate the provenance checks.

## Put the project on GitHub

Extract `project-1-github-ready.zip` and open its inner `project-1` directory. Create
an empty GitHub repository in your account, then run from that directory:

```sh
git init
git add .
git commit -m "Prepare Nassau Candy analytics project and deployment"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
git push -u origin main
```

Replace both placeholders with your actual repository identity. The included
GitHub Actions workflow installs dependencies and runs the 24 analytics/dashboard
tests plus package validation. It does not publish apps or regenerate/commit outputs.
Raw data is public educational sample data; preserve `ATTRIBUTION.md` and the dataset
guide. No software license has been selected on the author's behalf.

## Deploy the required Streamlit dashboard

Use **Streamlit Community Cloud** for the persistent Streamlit application.
Connect the GitHub repository and choose:

| Setting | Value |
|---|---|
| Branch | `main` |
| Main file path | `dashboard/app.py` |
| Python version in Advanced settings | `3.12` |
| Dependencies | Root `requirements.txt` → dashboard version lock |
| Configuration | Root `.streamlit/config.toml` |
| Secrets | None required |

Keep processed orders and reference/simulated JSON files in the repository. All file
paths resolve from the source tree. The dashboard regenerates scenarios in memory,
so visitors do not need write access to the repository.

Official references: [deploying and selecting Python](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy),
[dependency discovery](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies),
[repository layout](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization).

## Deploy the static companion on Vercel

Before publishing, edit `deployment/companion/public/config.js`:

```js
window.PROJECT_LINKS = {
  dashboard: "https://YOUR-APP.streamlit.app",
  github: "https://github.com/YOUR-USERNAME/YOUR-REPOSITORY"
};
```

Use the actual public URLs, commit and push the change. Null keeps a link hidden;
the presentation does not send public visitors to a loopback development server.
The values are public navigation links, not credentials or environment variables.

In Vercel, import the same GitHub repository with these settings:

| Setting | Value |
|---|---|
| Root Directory | `deployment/companion` |
| Framework Preset | Other |
| Build Command | Empty / skipped |
| Install Command | Empty / skipped |
| Output Directory | `public` |
| Environment variables | None |

`vercel.json` supplies the static settings and response headers. No Node dependency
installation is needed. The tracked `public/` folder already contains the generated
snapshot and report downloads. After new analysis, run `python deployment/build_companion.py`
from the repository root and commit the updated static files. Vercel serves the
presentation; the dashboard link opens the separately hosted Streamlit application.

Official references: [static build settings and root directories](https://vercel.com/docs/builds/configure-a-build),
[vercel.json configuration](https://vercel.com/docs/project-configuration/vercel-json),
[Git repository deployments](https://vercel.com/docs/git).

To preview the companion locally from the repository root:

```sh
python -m http.server 8502 --bind 127.0.0.1 --directory deployment/companion/public
```

Open `http://127.0.0.1:8502/`. Serve it over HTTP; opening the HTML directly as a
`file://` URL may block loading its JSON snapshot in browsers.

## Verify after deploying

Open both actual deployment URLs. On Streamlit, change product/region/mode and speed
priority; verify strict protection can produce no recommendations and downloads carry
the active settings. On the companion, change the product selector, open every resource,
and confirm the live-dashboard and GitHub links point to your deployments.
Check phone-width layout and keyboard navigation in a browser before submission.
Hosting build success alone does not verify real-world shipping performance.

The completed research paper and stakeholder executive summary are in
`reports/submission/`, with editable Markdown sources and a reproducible builder.
They are also included in the companion's downloads. To rebuild them, install
`deployment/requirements-documents.txt`, run `python reports/submission/build_documents.py`,
then refresh the companion. Review narrative findings if data or assumptions change;
the builder protects key snapshot facts with explicit checks.

## Refresh the source package

```sh
python deployment/build_companion.py
python deployment/validate_package.py
python deployment/verify_analysis.py
python deployment/package_project.py
```

The ZIP and its `.sha256` file are created beside `project-1/`, outside the repository.
The inventory is `deployment/package_manifest.json`; repackage after any source change.
