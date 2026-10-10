"""Reusable dashboard calculations; no Streamlit or file mutations."""
import io
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'analysis'))
from scenario_simulator import simulate
from rank_recommendations import build_rankings, portfolio_kpis


def calculate(data, products, factories, assumptions, constraints, policy,
              product=None, region=None, ship_mode=None, priority=.5,
              top_n=3, profit_policy='nonnegative_base'):
    cohort = data.copy()
    for field, value in [('Product ID', product), ('Region', region), ('Ship Mode', ship_mode)]:
        if value is not None:
            cohort = cohort[cohort[field].eq(value)]
    if cohort.empty:
        raise ValueError('No orders match the selected filters')
    if not (cohort['Destination Latitude'].notna() & cohort['Destination Longitude'].notna()).any():
        raise ValueError('Selected orders have no destination coordinates; geographic scenario estimates are unavailable')
    simulation = simulate(data, products, factories, assumptions, product, region, ship_mode)
    # A filtered geographic comparison still proposes a whole-product reassignment.
    # Reserve full sample demand, including unmapped/filtered-out orders, for capacity.
    full_units = data.groupby('Product ID')['Units'].sum()
    simulation['scenarios']['Source Units'] = simulation['scenarios']['Product ID'].map(full_units)
    ranking = build_rankings(simulation['scenarios'], simulation['sensitivity'],
                             constraints, policy, priority, top_n, profit_policy)
    kpis, joint = portfolio_kpis(ranking, simulation['sensitivity'])
    metadata = {'filters': simulation['filters'], 'settings': ranking['settings'],
                'is_simulated': True, 'operationally_approved': False,
                'profit_scope': 'Selected mapped cohort replay; not annual savings or a demand forecast',
                'capacity_scope': 'Whole-product demand over full 2021–2024 sample, including excluded orders',
                'constraints': constraints, 'assumptions': assumptions, 'ranking_policy': policy,
                'kpis': kpis}
    return {'simulation': simulation, 'ranking': ranking, 'kpis': kpis,
            'joint': joint, 'cohort': cohort, 'metadata': metadata}


def download_bundle(result):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in ['ranked_options', 'top_reassignment_candidates', 'portfolio', 'capacity_ledger']:
            archive.writestr(name + '.csv', result['ranking'][name].to_csv(index=False))
        for name in ['scenarios', 'sensitivity', 'route_comparisons']:
            archive.writestr(name + '.csv', result['simulation'][name].to_csv(index=False))
        archive.writestr('joint_portfolio_sensitivity.csv', result['joint'].to_csv(index=False))
        archive.writestr('metadata.json', json.dumps(result['metadata'], indent=2, allow_nan=False))
        archive.writestr('README.txt', 'All dispatch and contribution estimates are hypothetical.\n'
                          'Source dates are unverified; delivery time is unavailable.\n'
                          'Ranked alternatives are provisional investigation options.\n'
                          'Consult metadata.json for filters, assumptions, constraints and KPI definitions.\n')
    return buffer.getvalue()
