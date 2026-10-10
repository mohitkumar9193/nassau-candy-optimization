"""Behavioral checks for chronological evaluation and preprocessing leakage.

Run: python -m unittest discover -s analysis/tests -v
Test fixtures are synthetic in-memory examples, never project dataset records.
"""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from train_compare_models import FEATURES, TARGET, chronological_split, make_pipeline, screen_training_outliers


class ModelingChecks(unittest.TestCase):
    def fixture(self):
        return pd.DataFrame({
            "Row ID": [str(i) for i in range(200)], "Order ID": [f"order-{i}" for i in range(200)],
            "Order Date": pd.to_datetime(np.repeat(pd.date_range("2024-01-01", periods=10), 20)),
        })

    def test_whole_dates_remain_in_one_partition(self):
        train, test, cutoff = chronological_split(self.fixture())
        self.assertEqual(len(train), 160)
        self.assertEqual(len(test), 40)
        self.assertLess(train["Order Date"].max(), test["Order Date"].min())
        self.assertFalse(set(train["Order ID"]) & set(test["Order ID"]))

    def test_split_rejects_order_id_leakage(self):
        data = self.fixture()
        data.loc[180, "Order ID"] = data.loc[0, "Order ID"]
        with self.assertRaisesRegex(ValueError, "Order IDs cross"):
            chronological_split(data, fraction=.6)

    def test_preprocessing_ignores_future_extremes_and_unknown_categories(self):
        train = pd.DataFrame({"Units": [1, 2, 3, 4, 5, 6], "Great Circle Distance Km": [10., 20., np.nan, 40., 50., 60.],
                              "Order Month": [1] * 6, "Order Weekday": list(range(6)),
                              "Product ID": ["A"] * 6, "Assigned Factory": ["Factory A"] * 6,
                              "Region": ["Region A"] * 6, "Ship Mode": ["Standard"] * 6,
                              "Ship Date": ["2099-01-01"] * 6, TARGET: [2000] * 6})
        future = train.iloc[:1].copy()
        future["Units"] = 1000000
        future["Great Circle Distance Km"] = np.nan
        future["Product ID"] = "Unseen product"
        future["Assigned Factory"] = "Unseen factory"
        model = make_pipeline("Linear Regression")
        model.fit(train[FEATURES], np.arange(6))
        pre = model.named_steps["preprocess"]
        numeric = pre.named_transformers_["numeric"]
        before = numeric.named_steps["impute"].statistics_.copy()
        prediction = model.predict(future[FEATURES])
        np.testing.assert_array_equal(before, numeric.named_steps["impute"].statistics_)
        self.assertAlmostEqual(before[0], 3.5)
        self.assertAlmostEqual(before[1], 40.)
        self.assertTrue(np.isfinite(prediction).all())
        categories = pre.named_transformers_["categorical"].named_steps["encode"].categories_[0]
        self.assertEqual(list(categories), ["A"])
        transformed = pre.get_feature_names_out()
        self.assertFalse(any("Ship Date" in name or TARGET in name for name in transformed))

    def test_extreme_training_targets_are_screened_without_using_global_eda_flags(self):
        train = pd.DataFrame({"Units": list(range(1, 41)), "Product ID": ["A"] * 40,
                              "Ship Mode": ["Standard"] * 40,
                              TARGET: list(np.tile([2003, 2004, 2005, 2006], 10)),
                              "Extreme Outlier": [True] * 40})
        train.loc[39, TARGET] = 9000
        fitted, excluded, thresholds = screen_training_outliers(train)
        self.assertEqual(len(excluded), 1)
        self.assertEqual(len(fitted), 39)
        self.assertEqual(excluded.index.tolist(), [39])


if __name__ == "__main__":
    unittest.main()
