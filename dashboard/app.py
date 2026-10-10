"""Run from project root: streamlit run dashboard/app.py."""
import json
from pathlib import Path
import sys

import pandas as pd
import streamlit as st

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from service import ROOT, calculate, download_bundle
from scenario_simulator import read_inputs

st.set_page_config(page_title='Nassau Candy · Factory Decisions', page_icon='🍬', layout='wide')


@st.cache_data
def load_inputs():
    data, products, factories = read_inputs()
    def read(relative):
        return json.loads((ROOT / relative).read_text(encoding='utf-8'))
    return (data, products, factories,
            read('datasets/simulated/logistics_assumptions.json'),
            read('datasets/reference/operational_constraints.json'),
            read('datasets/reference/recommendation_policy.json'))


@st.cache_data(max_entries=32, show_spinner='Comparing factories and sensitivity cases…')
def run_comparison(product, region, mode, priority, top_n, profit_policy, constraints_json):
    data, products, factories, assumptions, _, policy = load_inputs()
    return calculate(data, products, factories, assumptions, json.loads(constraints_json), policy,
                     product, region, mode, priority, top_n, profit_policy)


def csv_button(label, frame, filename):
    st.download_button(label, frame.to_csv(index=False).encode('utf-8'), filename, 'text/csv')


def metric_text(value, suffix=''):
    return 'N/A' if value is None else f'{value:,.2f}{suffix}'


def main():
    st.title('Nassau Candy factory decisions')
    st.caption('Factory Reallocation & Shipping Optimization Recommendation System')
    st.warning('Educational planning scenarios. All dispatch and logistics estimates are hypothetical. '
               'Source shipment dates imply 2,000–2,011 days and remain unverified. '
               'These results do not establish delivery times or operationally approved factory moves.')
    data, products, factories, assumptions, constraints, policy = load_inputs()
    names = products.set_index('Product ID')['Product Name'].to_dict()
    with st.sidebar:
        st.header('Compare scenarios')
        product = st.selectbox('Product', [None] + products['Product ID'].tolist(),
                               format_func=lambda value: 'All products' if value is None else names[value])
        available = data if product is None else data[data['Product ID'].eq(product)]
        region = st.selectbox('Destination region', [None] + sorted(available['Region'].unique()),
                              format_func=lambda value: 'All regions' if value is None else value)
        if region is not None:
            available = available[available['Region'].eq(region)]
        mode = st.selectbox('Ship mode', [None] + sorted(available['Ship Mode'].unique()),
                            format_func=lambda value: 'All ship modes' if value is None else value)
        priority = st.slider('Speed priority (%)', 0, 100, 50, 5)
        st.caption(f'Profit priority: {100-priority}%. Risk penalty remains active.')
        top_n = st.slider('Top alternatives per product', 1, 4, 3)
        policies = {'Base contribution must not decline': 'nonnegative_base',
                    'No loss in any tested sensitivity case': 'strict_all_cases',
                    'Explore speed/profit tradeoffs': 'tradeoff'}
        policy_label = st.selectbox('Profit protection', list(policies))
        upload = st.file_uploader('Optional capacity / compatibility JSON', type=['json'])
        st.caption('Use the downloadable constraint template. Unknown constraints remain unverified.')
        st.download_button('Constraint template', json.dumps(constraints, indent=2),
                           'operational_constraints.json', 'application/json')
    try:
        if upload is not None:
            constraints = json.loads(upload.getvalue().decode('utf-8'))
        result = run_comparison(product, region, mode, priority/100, top_n,
                                policies[policy_label], json.dumps(constraints, sort_keys=True))
    except (ValueError, KeyError, TypeError, AttributeError, UnicodeError) as error:
        st.error(f'Cannot calculate this selection: {error}')
        st.stop()
    ranking, kpis, cohort = result['ranking'], result['kpis'], result['cohort']
    st.caption(f'{len(cohort):,} selected order records · {cohort["Units"].sum():,} units · '
               'Profit comparisons use mapped destinations only; capacity reserves full-product sample demand.')
    columns = st.columns(4)
    for column, label, key, suffix in [
        (columns[0], 'Modeled dispatch reduction', 'modeled_lead_time_reduction_pct', '%'),
        (columns[1], 'Profit stability across tested cases', 'profit_impact_stability_pct', '%'),
        (columns[2], 'Evidence readiness', 'scenario_confidence_score', '/100'),
        (columns[3], 'Provisional recommendation coverage', 'recommendation_coverage_pct', '%')]:
        column.metric(label, metric_text(kpis[key], suffix))
    overview, simulator, recommendations, risks, downloads = st.tabs([
        'Current performance', 'Factory simulator', 'Ranked recommendations', 'Risk & impact', 'Downloads'])
    with overview:
        st.subheader('Selected historical demand and financials')
        columns = st.columns(3)
        columns[0].metric('Sales · source monetary units', f'{cohort["Sales"].sum():,.2f}')
        columns[1].metric('Source gross profit · before assumed freight', f'{cohort["Gross Profit"].sum():,.2f}')
        columns[2].metric('Order units', f'{cohort["Units"].sum():,}')
        dimension = st.selectbox('Group performance by', ['Product Name', 'Assigned Factory', 'Region', 'Ship Mode'])
        summary = cohort.groupby(dimension, as_index=False).agg(
            Records=('Row ID', 'size'), Units=('Units', 'sum'), Sales=('Sales', 'sum'),
            Gross_Profit=('Gross Profit', 'sum'))
        st.dataframe(summary, hide_index=True, width='stretch')
        st.bar_chart(summary.set_index(dimension)[['Sales', 'Gross_Profit']])
        st.caption('Factory groups use static product assignments, not observed shipment origins. '
                   'Historical lead-time reporting is blocked until the date anomaly is resolved.')
    with simulator:
        options = ranking['ranked_options']
        choice = st.selectbox('Inspect product', list(options['Product ID'].unique()), format_func=names.get)
        view = options[options['Product ID'].eq(choice)]
        decision = ranking['portfolio'][ranking['portfolio']['Product ID'].eq(choice)].iloc[0]
        st.write(f'Current: **{decision["Current Factory"]}** → Selected: **{decision["Selected Factory"]}**')
        st.caption(str(decision['Decision']))
        fields = ['Candidate Factory', 'Is Current Assignment', 'Current Modeled Dispatch Lead Days',
                  'Candidate Modeled Dispatch Lead Days', 'Modeled Dispatch Lead Reduction Pct',
                  'Modeled Contribution Change', 'Mapped Unit Coverage Pct', 'Ranking Score']
        st.dataframe(view.reindex(columns=fields), hide_index=True, width='stretch')
        chart = view.set_index('Candidate Factory')[['Current Modeled Dispatch Lead Days',
                                                     'Candidate Modeled Dispatch Lead Days']]
        st.bar_chart(chart, horizontal=True)
        st.caption('Days are assumed pre-shipment dispatch allowances, not delivery durations. '
                   'Contribution changes are source monetary units over the selected mapped replay.')
        comparison = ranking['selected_rows'].reindex(columns=['Product Name', 'Current Factory',
            'Candidate Factory', 'Current Modeled Dispatch Lead Days', 'Candidate Modeled Dispatch Lead Days',
            'Modeled Contribution Change'])
        st.subheader('Current versus selected portfolio')
        st.dataframe(comparison, hide_index=True, width='stretch')
    with recommendations:
        st.subheader('Top alternatives to investigate')
        candidates = ranking['top_reassignment_candidates']
        if candidates.empty:
            st.info('No reassignment passes the selected profit policy, constraints and positive-score requirement.')
        else:
            st.dataframe(candidates, hide_index=True, width='stretch')
        st.subheader('Joint portfolio after capacity checks')
        st.dataframe(ranking['portfolio'], hide_index=True, width='stretch')
        st.caption('Top alternatives are standalone choices. The joint portfolio reserves receiving capacity '
                   'once per whole product, does not reuse released origin capacity, and uses a greedy selection. '
                   'It is not a globally optimal allocation.')
        with st.expander('Ranking and KPI definitions'):
            st.markdown('Speed utility = dispatch reduction (%) / 10; profit utility = contribution change / '
                        'max(5% of absolute current modeled contribution, 100). Both are clipped to [−1, 1]. '
                        'Score = speed weight × speed utility + profit weight × profit utility '
                        '− 0.1 × (1 − stability / 100).')
            st.markdown('Dispatch reduction is weighted by mapped units across the selected portfolio. '
                        'Profit stability is the percentage of aligned joint sensitivity cases with nonnegative '
                        'contribution change. Evidence readiness is the minimum evidence gate, weighted across '
                        'proposed moves; it is not a probability. Coverage is proposed product moves / products '
                        'in the selected cohort. No-move stability and readiness are N/A.')
            st.json(policy)
    with risks:
        st.error('No factory reassignment is operationally verified. Alternative factory-product outcome history '
                 'and calibrated dispatch estimates are absent.')
        st.warning('Capacity and production compatibility are unknown unless documented in the uploaded constraints. '
                   'Unknown does not mean unlimited capacity or confirmed compatibility.')
        if policies[policy_label] == 'tradeoff':
            st.warning('Tradeoff mode permits base-case financial losses when the speed score outweighs them.')
        worst = kpis['sensitivity_min_portfolio_contribution_change']
        if worst is not None and worst < 0:
            st.warning(f'Joint downside in the tested grid: {worst:,.2f} source monetary units. '
                       'Grid cases have no assigned probability.')
        unmapped = cohort['Destination Latitude'].isna() | cohort['Destination Longitude'].isna()
        st.write(f'Excluded from geographic and modeled financial estimates: {unmapped.sum():,} records '
                 f'({cohort.loc[unmapped, "Units"].sum():,} units).')
        st.write(f'Base modeled contribution change: {kpis["base_modeled_contribution_change"]:,.2f} '
                 'source monetary units. Verified recommendation coverage: '
                 f'{kpis["verified_recommendation_coverage_pct"]:.2f}%.')
        st.dataframe(ranking['ranked_options'].reindex(columns=['Product Name', 'Candidate Factory',
            'Investigation Eligible', 'Known Constraints Satisfied', 'Profit Policy Satisfied',
            'Sensitivity Min Contribution Change', 'Scenario Confidence Score', 'Uncertainty Reasons']),
            hide_index=True, width='stretch')
        st.subheader('Capacity ledger · full sample units')
        st.dataframe(ranking['capacity_ledger'], hide_index=True, width='stretch')
        with st.expander('Active assumptions and constraints'):
            st.json(assumptions)
            st.json(constraints)
    with downloads:
        st.download_button('Download complete scenario results (ZIP)', download_bundle(result),
                           'nassau_candy_scenarios.zip', 'application/zip')
        csv_button('Ranked factory options (CSV)', ranking['ranked_options'], 'ranked_options.csv')
        csv_button('Selected portfolio (CSV)', ranking['portfolio'], 'portfolio.csv')
        csv_button('Sensitivity cases (CSV)', result['joint'], 'joint_sensitivity.csv')
        st.download_button('KPIs and reproducibility metadata (JSON)',
                           json.dumps(result['metadata'], indent=2, allow_nan=False),
                           'scenario_metadata.json', 'application/json')
        st.caption('Downloads reflect the active filters, priority, protection policy and uploaded constraints.')


if __name__ == '__main__':
    main()
