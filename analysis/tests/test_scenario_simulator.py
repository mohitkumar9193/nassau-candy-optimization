"""Behavioral scenario tests; in-memory fixtures never alter source datasets."""

import copy
import json
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scenario_simulator import DEFAULT_ASSUMPTIONS, read_inputs, simulate


class ScenarioChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data, products, cls.factories = read_inputs()
        cls.product_id = "CHO-MIL-31000"
        cls.data = data[data["Product ID"].eq(cls.product_id) & data["Destination Latitude"].notna()].head(6).copy()
        cls.products = products[products["Product ID"].eq(cls.product_id)].copy()
        cls.assumptions = json.loads(DEFAULT_ASSUMPTIONS.read_text())

    def test_current_factory_is_identity_under_every_sensitivity_case(self):
        result = simulate(self.data, self.products, self.factories, self.assumptions)
        current = result["scenarios"][result["scenarios"]["Is Current Assignment"]].iloc[0]
        cases = result["sensitivity"][result["sensitivity"]["Scenario ID"].eq(current["Scenario ID"])]
        self.assertEqual(len(result["scenarios"]), 5)
        self.assertEqual(len(cases), 81)
        self.assertTrue(np.allclose(cases["Modeled Contribution Change"], 0))
        self.assertTrue(np.allclose(cases["Modeled Dispatch Lead Reduction Days"], 0))
        self.assertTrue(np.allclose(cases["Assumed Reassignment Cost"], 0))

    def test_alternatives_are_uncertain_and_setup_is_charged_once(self):
        scenarios = simulate(self.data, self.products, self.factories, self.assumptions)["scenarios"]
        alternatives = scenarios[~scenarios["Is Current Assignment"]]
        self.assertTrue(alternatives["Factory Product Combination Uncertain"].all())
        self.assertTrue(alternatives["Static Assignment Record Support"].eq(0).all())
        self.assertTrue(alternatives["Assumed Reassignment Cost"].eq(100.).all())
        self.assertTrue(alternatives["Operational Feasibility"].eq("not_established").all())

    def test_setup_changes_profit_but_not_dispatch_estimates(self):
        original = simulate(self.data, self.products, self.factories, self.assumptions)["scenarios"]
        changed = copy.deepcopy(self.assumptions)
        changed["one_time_reassignment_cost_per_product"] = 140.
        updated = simulate(self.data, self.products, self.factories, changed)["scenarios"]
        mask = ~original["Is Current Assignment"]
        self.assertTrue(np.allclose(updated.loc[mask, "Modeled Contribution Change"] - original.loc[mask, "Modeled Contribution Change"], -40))
        self.assertTrue(np.allclose(updated["Candidate Modeled Dispatch Lead Days"], original["Candidate Modeled Dispatch Lead Days"]))

    def test_unmapped_cohort_has_unavailable_estimates_not_zero(self):
        data = self.data.copy()
        data["Destination Latitude"] = np.nan
        data["Destination Longitude"] = np.nan
        result = simulate(data, self.products, self.factories, self.assumptions)
        scenarios = result["scenarios"]
        self.assertTrue(scenarios["Modeled Contribution Change"].isna().all())
        self.assertTrue(scenarios["Modeled Dispatch Lead Reduction Days"].isna().all())
        self.assertTrue(scenarios["Estimate Status"].eq("unavailable_no_coordinates").all())
        self.assertTrue(result["sensitivity"].empty)

    def test_base_case_is_inside_sensitivity_bounds(self):
        scenarios = simulate(self.data, self.products, self.factories, self.assumptions)["scenarios"]
        self.assertTrue((scenarios["Modeled Contribution Change"] >= scenarios["Sensitivity Min Contribution Change"] - 1e-9).all())
        self.assertTrue((scenarios["Modeled Contribution Change"] <= scenarios["Sensitivity Max Contribution Change"] + 1e-9).all())

    def test_invalid_assumption_and_unknown_filter_are_rejected(self):
        assumptions = copy.deepcopy(self.assumptions)
        assumptions["distance_cost_per_unit_per_1000_km"] = -1.
        with self.assertRaisesRegex(ValueError, "Invalid assumption"):
            simulate(self.data, self.products, self.factories, assumptions)
        with self.assertRaisesRegex(ValueError, "Unknown Region"):
            simulate(self.data, self.products, self.factories, self.assumptions, region="Imaginary")


if __name__ == "__main__":
    unittest.main()
