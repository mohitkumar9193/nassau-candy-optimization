"""Ranking/constraint/KPI checks with explicitly synthetic in-memory test cases."""

import copy
import json
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rank_recommendations import DEFAULT_CONSTRAINTS, POLICY_PATH, ROOT, build_rankings, portfolio_kpis


class RecommendationChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = pd.read_csv(ROOT / "reports/scenario_simulator/scenarios.csv")
        cls.policy = json.loads(POLICY_PATH.read_text())
        cls.constraints = json.loads(DEFAULT_CONSTRAINTS.read_text())

    def fixture(self, products=1):
        template = self.source[self.source["Product ID"].eq("CHO-NUT-13000")].set_index("Candidate Factory")
        rows, cases = [], []
        for i in range(products):
            for factory, gain, profit in [("Lot's O' Nuts", 0., 0.), ("Secret Factory", 20., 100.), ("Wicked Chocy's", 5., 400.)]:
                row = template.loc[factory].to_dict()
                row.update({"Candidate Factory": factory, "Product ID": f"TEST-{i}", "Product Name": f"Test product {i}",
                            "Scenario ID": f"TEST-{i}-{factory}", "Source Units": 100, "Mapped Units": 100,
                            "Current Modeled Contribution": 1000., "Modeled Dispatch Lead Reduction Pct": gain,
                            "Current Modeled Dispatch Lead Days": 2., "Modeled Dispatch Lead Reduction Days": 2 * gain / 100,
                            "Modeled Contribution Change": profit, "Sensitivity Min Contribution Change": profit,
                            "Sensitivity Case Count": 2})
                rows.append(row)
                cases.extend({"Scenario ID": row["Scenario ID"], "Case": case, "Modeled Contribution Change": profit} for case in [1, 2])
        return pd.DataFrame(rows), pd.DataFrame(cases)

    def test_slider_changes_the_selected_tradeoff(self):
        rows, cases = self.fixture()
        speed = build_rankings(rows, cases, self.constraints, self.policy, speed_priority=1.)
        profit = build_rankings(rows, cases, self.constraints, self.policy, speed_priority=0.)
        self.assertEqual(speed["portfolio"]["Selected Factory"].iloc[0], "Secret Factory")
        self.assertEqual(profit["portfolio"]["Selected Factory"].iloc[0], "Wicked Chocy's")

    def test_zero_capacity_and_empty_compatibility_are_real_limits(self):
        rows, cases = self.fixture()
        constraints = copy.deepcopy(self.constraints)
        constraints["factories"]["Secret Factory"]["additional_capacity_units"] = 0
        constraints["factories"]["Wicked Chocy's"]["compatible_product_ids"] = []
        result = build_rankings(rows, cases, constraints, self.policy, speed_priority=1.)
        self.assertEqual(result["portfolio"]["Selected Factory"].iloc[0], "Lot's O' Nuts")
        self.assertTrue(result["top_reassignment_candidates"].empty)

    def test_joint_capacity_is_not_double_counted(self):
        rows, cases = self.fixture(products=2)
        constraints = copy.deepcopy(self.constraints)
        constraints["factories"]["Secret Factory"]["additional_capacity_units"] = 150
        constraints["factories"]["Wicked Chocy's"]["compatible_product_ids"] = []
        result = build_rankings(rows, cases, constraints, self.policy, speed_priority=1.)
        self.assertEqual(result["portfolio"]["Selected Factory"].eq("Secret Factory").sum(), 1)
        ledger = result["capacity_ledger"].set_index("Factory")
        self.assertEqual(ledger.loc["Secret Factory", "Additional Capacity Remaining"], 50)
        self.assertEqual(ledger.loc["Secret Factory", "Proposed Incoming Units"], 100)

    def test_verified_constraints_do_not_invent_outcome_confidence(self):
        rows, cases = self.fixture()
        constraints = copy.deepcopy(self.constraints)
        record = constraints["factories"]["Secret Factory"]
        record.update({"additional_capacity_units": 1000, "compatible_product_ids": ["TEST-0"],
                       "capacity_verified": True, "compatibility_verified": True, "source_reference": "Synthetic test fixture"})
        result = build_rankings(rows, cases, constraints, self.policy)
        self.assertTrue(result["ranked_options"]["Scenario Confidence Score"].eq(0).all())
        self.assertFalse(result["ranked_options"]["Operationally Supported"].any())

    def test_profit_stability_sums_common_shocks_instead_of_averaging(self):
        rows, cases = self.fixture(products=2)
        constraints = copy.deepcopy(self.constraints)
        constraints["factories"]["Wicked Chocy's"]["compatible_product_ids"] = []
        for index, deltas in enumerate([[10., -5.], [-5., 10.]]):
            mask = cases["Scenario ID"].eq(f"TEST-{index}-Secret Factory")
            cases.loc[mask, "Modeled Contribution Change"] = deltas
            rows.loc[rows["Scenario ID"].eq(f"TEST-{index}-Secret Factory"), "Sensitivity Min Contribution Change"] = -5.
        result = build_rankings(rows, cases, constraints, self.policy)
        kpis, joint = portfolio_kpis(result, cases)
        self.assertEqual(kpis["profit_impact_stability_pct"], 100.)
        self.assertTrue(joint["Portfolio Contribution Change"].eq(5.).all())
        self.assertEqual(kpis["modeled_lead_time_reduction_pct"], 20.)

    def test_no_move_stability_is_not_falsely_reported_as_100_percent(self):
        rows, cases = self.fixture()
        rows.loc[~rows["Is Current Assignment"], "Sensitivity Min Contribution Change"] = -1.
        result = build_rankings(rows, cases, self.constraints, self.policy, profit_policy="strict_all_cases")
        kpis, joint = portfolio_kpis(result, cases)
        self.assertEqual(kpis["recommendation_coverage_pct"], 0.)
        self.assertIsNone(kpis["profit_impact_stability_pct"])
        self.assertIsNone(kpis["scenario_confidence_score"])

    def test_incomplete_joint_sensitivity_is_rejected(self):
        rows, cases = self.fixture()
        result = build_rankings(rows, cases, self.constraints, self.policy, speed_priority=1.)
        incomplete = cases[~(cases["Scenario ID"].eq("TEST-0-Secret Factory") & cases["Case"].eq(2))]
        with self.assertRaisesRegex(ValueError, "missing sensitivity cases"):
            portfolio_kpis(result, incomplete)


if __name__ == "__main__":
    unittest.main()
