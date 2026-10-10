# Data and project attribution

This is an independent educational internship project, not an official Nassau Candy
application or a claim about verified company operations.

- Orders and source product/factory tables: Maven Analytics, **US Candy Distributor**,
  https://mavenanalytics.io/data-playground/us-candy-distributor.
  The publisher labels its sample Public Domain. Source bytes and SHA-256 hashes are
  retained in `datasets/source_manifest.json`.
- US ZIP geography: **SimpleMaps**, https://simplemaps.com/data/us-zips,
  Basic data under **CC BY 4.0**, https://creativecommons.org/licenses/by/4.0/.
  This project uses the historical snapshot included in the Maven archive. Coordinates
  were joined to orders and used to derive great-circle distances; country/postal keys
  were normalized. Preserve attribution when reusing derived data.
- The five factory coordinates and 15 product assignments were provided in the
  internship assignment and reconciled to the source tables with spelling aliases.
- Logistics costs, dispatch allowances and sensitivity ranges are project-created
  hypothetical assumptions, separately labeled in `datasets/simulated/`.

Dataset usage terms do not automatically license this project's original code. No
blanket software license has been selected for the author; sharing the repository
does not grant an additional open-source license. Dependencies retain their own terms.
