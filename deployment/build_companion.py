"""Refresh the tracked static presentation snapshot from completed reports."""
import csv
import hashlib
import json
import re
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT/'deployment/companion/public'


def build():
    PUBLIC.mkdir(parents=True, exist_ok=True)
    downloads=PUBLIC/'downloads'
    downloads.mkdir(exist_ok=True)
    source=ROOT/'reports/recommendations'
    kpis=json.loads((source/'kpis.json').read_text())
    with (source/'portfolio.csv').open(newline='',encoding='utf-8') as stream:
        portfolio=list(csv.DictReader(stream))
    with (source/'selected_rows.csv').open(newline='',encoding='utf-8') as stream:
        selected={row['Scenario ID']:row for row in csv.DictReader(stream)}
    products=[]
    for row in portfolio:
        scenario=selected[row['Selected Scenario ID']]
        products.append({'id':row['Product ID'],'name':row['Product Name'],
            'current':row['Current Factory'],'selected':row['Selected Factory'],'decision':row['Decision'],
            'dispatch_reduction_pct':float(scenario['Modeled Dispatch Lead Reduction Pct']),
            'contribution_change':float(scenario['Modeled Contribution Change'])})
    assets={'reports/eda/current_performance_report.html':'analysis-report.html',
        'reports/recommendations/recommendation_report.md':'recommendation_report.md',
        'reports/recommendations/portfolio.csv':'portfolio.csv',
        'datasets/DATASET_GUIDE.md':'DATASET_GUIDE.md'}
    for filename in ['research_paper.pdf','executive_summary.pdf']:
        relative='reports/submission/'+filename
        if (ROOT/relative).is_file():
            assets[relative]=filename
    manifest={}
    for relative,filename in assets.items():
        path=ROOT/relative
        shutil.copyfile(path,downloads/filename)
        manifest[relative]=hashlib.sha256(path.read_bytes()).hexdigest()
    # Keep the copied HTML report compatible with the companion's strict CSP.
    report=downloads/'analysis-report.html'
    html=report.read_text(encoding='utf-8')
    css=re.search(r'<style>(.*?)</style>',html,re.S).group(1)
    (downloads/'report.css').write_text(css,encoding='utf-8')
    report.write_text(re.sub(r'<style>.*?</style>', '<link rel="stylesheet" href="report.css">',html,flags=re.S),encoding='utf-8')
    # Companion copies only aggregate reports and product-level choices; no order rows.
    snapshot={'is_simulated':True,'operationally_approved':False,
        'snapshot_scope':'Full mapped 2021–2024 replay; default 50/50 priority',
        'kpis':kpis,'products':products,'source_sha256':manifest}
    (PUBLIC/'project-data.json').write_text(json.dumps(snapshot,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(f'Companion refreshed: {len(products)} product comparisons, {len(assets)} resources')


if __name__=='__main__':
    build()
