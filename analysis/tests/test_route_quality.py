"""Checks that missing geography and unverified intervals remain unavailable."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cluster_routes import summarize, weighted_distance


class RouteQualityChecks(unittest.TestCase):
    def fixture(self):
        return pd.DataFrame({"Great Circle Distance Km": [100., 300., np.nan], "Units": [1, 3, 100],
                             "Sales": [5., 15., 500.], "Gross Profit": [3., 9., 300.],
                             "Order To Shipment Lead Time Days": [2003, 2004, 2005],
                             "Valid Historical Interval": [False, False, False]})

    def test_unmapped_demand_does_not_bias_distance_toward_zero(self):
        result = summarize(self.fixture())
        self.assertAlmostEqual(result["Unit Weighted Distance Km"], 250.)
        self.assertEqual(result["Units"], 104)
        self.assertEqual(result["Mapped Units"], 4)
        self.assertEqual(result["Mapped Records"], 2)

    def test_suspect_intervals_never_become_valid_lead_times(self):
        result = summarize(self.fixture())
        self.assertEqual(result["Valid Historical Interval Records"], 0)
        self.assertTrue(np.isnan(result["Valid Mean Lead Time Days"]))
        self.assertEqual(result["Suspect Interval Records"], 3)
        self.assertEqual(result["Diagnostic Mean Interval Days"], 2004.)

    def test_missing_geography_remains_unavailable(self):
        rows = self.fixture()
        rows["Great Circle Distance Km"] = np.nan
        result = summarize(rows)
        self.assertTrue(np.isnan(weighted_distance(rows)))
        self.assertTrue(np.isnan(result["Distance Exposure Unit Km"]))
        self.assertEqual(result["Mapped Records"], 0)


if __name__ == "__main__":
    unittest.main()
