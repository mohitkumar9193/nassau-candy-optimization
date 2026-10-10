import io
import json
from pathlib import Path
import sys
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'dashboard'))
from service import calculate, download_bundle
from scenario_simulator import read_inputs


class DashboardIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.products, cls.factories = read_inputs()
        cls.assumptions = json.loads((ROOT/'datasets/simulated/logistics_assumptions.json').read_text())
        cls.constraints = json.loads((ROOT/'datasets/reference/operational_constraints.json').read_text())
        cls.policy = json.loads((ROOT/'datasets/reference/recommendation_policy.json').read_text())

    def run_filter(self, **kwargs):
        return calculate(self.data, self.products, self.factories, self.assumptions,
                         self.constraints, self.policy, **kwargs)

    def test_filtered_capacity_reserves_full_product_and_exports_settings(self):
        result = self.run_filter(product='CHO-MIL-31000', region='Pacific', ship_mode='Standard Class', priority=.75)
        full_units = self.data.loc[self.data['Product ID'].eq('CHO-MIL-31000'), 'Units'].sum()
        self.assertTrue(result['simulation']['scenarios']['Source Units'].eq(full_units).all())
        self.assertEqual(len(result['simulation']['scenarios']), 5)
        archive = zipfile.ZipFile(io.BytesIO(download_bundle(result)))
        metadata = json.loads(archive.read('metadata.json'))
        self.assertEqual(metadata['filters']['region'], 'Pacific')
        self.assertEqual(metadata['settings']['speed_priority'], .75)
        self.assertFalse(metadata['operationally_approved'])
        self.assertIn('ranked_options.csv', archive.namelist())
        self.assertIn('sensitivity.csv', archive.namelist())

    def test_strict_policy_no_moves_and_na_risk_metrics(self):
        result = self.run_filter(profit_policy='strict_all_cases')
        self.assertEqual(result['kpis']['proposed_reassignments'], 0)
        self.assertIsNone(result['kpis']['profit_impact_stability_pct'])
        self.assertIsNone(result['kpis']['scenario_confidence_score'])
        download_bundle(result)

    def test_unmapped_cohort_reports_unavailable(self):
        only_unmapped = self.data[self.data['Destination Latitude'].isna()]
        with self.assertRaisesRegex(ValueError, 'no destination coordinates'):
            calculate(only_unmapped, self.products, self.factories, self.assumptions,
                      self.constraints, self.policy)

    def test_app_controls_and_strict_rerun(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_file(str(ROOT/'dashboard/app.py'), default_timeout=90).run()
        self.assertEqual(len(app.exception), 0, str(app.exception))
        self.assertEqual(len(app.tabs), 5)
        self.assertEqual(len(app.metric), 7)
        next(x for x in app.slider if x.label == 'Speed priority (%)').set_value(100)
        next(x for x in app.selectbox if x.label == 'Product').select('CHO-MIL-31000')
        app.run()
        self.assertEqual(len(app.exception), 0, str(app.exception))
        next(x for x in app.selectbox if x.label == 'Destination region').select('Pacific')
        app.run()
        self.assertEqual(len(app.exception), 0, str(app.exception))
        next(x for x in app.selectbox if x.label == 'Profit protection').select('No loss in any tested sensitivity case')
        app.run()
        self.assertEqual(len(app.exception), 0, str(app.exception))
        self.assertTrue(any('No reassignment passes' in str(x.value) for x in app.info))
        self.assertTrue(any(x.value == 'N/A' for x in app.metric))
        next(x for x in app.selectbox if x.label == 'Ship mode').select('Standard Class')
        next(x for x in app.slider if x.label == 'Top alternatives per product').set_value(1)
        next(x for x in app.selectbox if x.label == 'Group performance by').select('Assigned Factory')
        app.run()
        self.assertEqual(len(app.exception), 0, str(app.exception))
        self.assertTrue(any('selected order records' in str(x.value) for x in app.caption))
        self.assertEqual(next(x for x in app.slider if x.label == 'Top alternatives per product').value, 1)


if __name__ == '__main__':
    unittest.main()
