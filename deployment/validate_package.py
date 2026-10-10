"""Offline provenance and deployment integrity checks; standard library only."""
import csv
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.ids=[]
    def handle_starttag(self,tag,attrs):
        values=dict(attrs)
        if 'id' in values: self.ids.append(values['id'])
        for key in ['href','src']:
            if values.get(key): self.links.append(values[key])


def validate():
    manifest=json.loads((ROOT/'datasets/source_manifest.json').read_text())
    for filename,info in manifest['raw_files'].items():
        path=ROOT/'datasets/raw'/filename
        assert hashlib.sha256(path.read_bytes()).hexdigest()==info['sha256'],f'Source bytes changed: {filename}'
    public=ROOT/'deployment/companion/public'
    snapshot=json.loads((public/'project-data.json').read_text())
    kpis=json.loads((ROOT/'reports/recommendations/kpis.json').read_text())
    assert snapshot['kpis']==kpis,'Companion KPI snapshot is stale'
    assert len(snapshot['products'])==15 and len({row['id'] for row in snapshot['products']})==15
    assert snapshot['is_simulated'] and not snapshot['operationally_approved']
    assert not kpis['operational_recommendations_approved']
    for relative,digest in snapshot['source_sha256'].items():
        assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==digest,f'Stale copied report: {relative}'
    with (ROOT/'reports/recommendations/selected_rows.csv').open(newline='',encoding='utf-8') as stream:
        rows={row['Product ID']:row for row in csv.DictReader(stream)}
    for product in snapshot['products']:
        row=rows[product['id']]
        assert product['selected']==row['Candidate Factory']
        assert product['dispatch_reduction_pct']==float(row['Modeled Dispatch Lead Reduction Pct'])
        assert product['contribution_change']==float(row['Modeled Contribution Change'])
    page=Links(); page.feed((public/'index.html').read_text(encoding='utf-8'))
    assert len(page.ids)==len(set(page.ids)),'Duplicate HTML IDs'
    for link in page.links:
        if link.startswith('#'):
            assert link[1:] in page.ids,f'Missing anchor: {link}'
        elif not urlsplit(link).scheme:
            assert (public/link).is_file(),f'Missing local resource: {link}'
    report=(public/'downloads/analysis-report.html').read_text(encoding='utf-8')
    assert '<style>' not in report and '<script' not in report
    assert 'href="report.css"' in report and (public/'downloads/report.css').is_file()
    required=['dashboard/app.py','deployment/requirements-dashboard-lock.txt',
              'deployment/requirements-analysis-lock.txt','.github/workflows/validate.yml',
              '.streamlit/config.toml','.gitattributes','ATTRIBUTION.md']
    for relative in required: assert (ROOT/relative).is_file(),relative
    for lock in ['requirements-dashboard-lock.txt','requirements-analysis-lock.txt']:
        for line in (ROOT/'deployment'/lock).read_text().splitlines():
            if line and not line.startswith('#'): assert re.fullmatch(r'[a-z0-9-]+==[^\s]+',line),line
    config=json.loads((ROOT/'deployment/companion/vercel.json').read_text())
    assert config['outputDirectory']=='public' and config['framework'] is None
    assert config['buildCommand']=='' and config['installCommand']==''
    print(f'Package integrity passed: {len(manifest["raw_files"])} source hashes, 15 product snapshots, local resources, version locks and deployment configuration')


if __name__=='__main__':
    try: validate()
    except (AssertionError,KeyError,ValueError,FileNotFoundError) as error:
        print(f'Package integrity failed: {error}',file=sys.stderr); sys.exit(1)
