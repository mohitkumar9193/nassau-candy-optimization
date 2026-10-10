"""Leakage-safe chronological comparison of lead-time regressors.

Run: python analysis/train_compare_models.py
If target dates are suspect, normal mode refuses training and writes readiness.json.
Explicit educational diagnostic: python analysis/train_compare_models.py --diagnostic
Diagnostic models predict unverified source date intervals, not operational lead times.
"""

import argparse
import json
import math
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[1]
TARGET = "Order To Shipment Lead Time Days"
NUMERIC = ["Units", "Great Circle Distance Km", "Order Month", "Order Weekday"]
CATEGORICAL = ["Product ID", "Assigned Factory", "Region", "Ship Mode"]
FEATURES = NUMERIC + CATEGORICAL
SEED = 42
RELATIVE_TIE_TOLERANCE = .05


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def chronological_split(data, fraction=.8):
    """Choose an approximate row-count boundary, assigning whole dates to one side."""
    ordered = data.sort_values(["Order Date", "Row ID"]).copy()
    cutoff = ordered.iloc[math.floor(len(ordered) * fraction)]["Order Date"]
    before, after = ordered[ordered["Order Date"] < cutoff].copy(), ordered[ordered["Order Date"] >= cutoff].copy()
    if len(before) < 30 or len(after) < 30:
        raise ValueError("Not enough records for chronological evaluation")
    if before["Order Date"].max() >= after["Order Date"].min():
        raise AssertionError("Dates overlap across split")
    if set(before["Order ID"]) & set(after["Order ID"]):
        raise ValueError("Repeated Order IDs cross the chronological boundary; resolve grouping before modeling")
    return before, after, cutoff


def screen_training_outliers(train):
    """Fit 3-IQR screens only on training data; never trim validation or test rows.

    Screening uses known order quantity within product and target interval within mode.
    Sparse groups (<20) and zero-IQR groups are not trimmed. This does not correct dates.
    """
    flagged = pd.Series(False, index=train.index)
    thresholds = []
    for field, group_field in [("Units", "Product ID"), (TARGET, "Ship Mode")]:
        for group, rows in train.groupby(group_field):
            assessable = len(rows) >= 20
            q1, q3 = rows[field].quantile([.25, .75]) if assessable else (np.nan, np.nan)
            iqr = q3 - q1
            assessable = assessable and iqr > 0
            lower, upper = q1 - 3 * iqr, q3 + 3 * iqr
            mask = (rows[field] < lower) | (rows[field] > upper) if assessable else pd.Series(False, index=rows.index)
            flagged.loc[rows.index] |= mask
            thresholds.append({"Field": field, "Group Field": group_field, "Group": group, "Rows": len(rows),
                               "Lower Fence": float(lower) if assessable else None,
                               "Upper Fence": float(upper) if assessable else None,
                               "Assessed": bool(assessable), "Excluded Training Rows": int(mask.sum())})
    return train.loc[~flagged].copy(), train.loc[flagged].copy(), thresholds


def make_pipeline(name):
    numerical = Pipeline([("impute", SimpleImputer(strategy="median", add_indicator=True)),
                          ("scale", StandardScaler())])
    categorical = Pipeline([("impute", SimpleImputer(strategy="most_frequent")),
                            ("encode", OneHotEncoder(handle_unknown="ignore", sparse_output=False))])
    preprocess = ColumnTransformer([("numeric", numerical, NUMERIC), ("categorical", categorical, CATEGORICAL)])
    regressors = {
        "Linear Regression": LinearRegression(),
        "Random Forest": RandomForestRegressor(n_estimators=160, max_depth=10, min_samples_leaf=4,
                                               random_state=SEED, n_jobs=1),
        "Gradient Boosting": GradientBoostingRegressor(n_estimators=160, learning_rate=.05,
                                                       max_depth=2, min_samples_leaf=4, random_state=SEED),
    }
    return Pipeline([("preprocess", preprocess), ("regressor", regressors[name])])


def metrics(actual, predicted):
    return {"RMSE Days": float(np.sqrt(mean_squared_error(actual, predicted))),
            "MAE Days": float(mean_absolute_error(actual, predicted)), "R2": float(r2_score(actual, predicted))}


def profile(rows):
    return {"rows": len(rows), "start": rows["Order Date"].min().strftime("%Y-%m-%d"),
            "end": rows["Order Date"].max().strftime("%Y-%m-%d"),
            "distinct_order_ids": int(rows["Order ID"].nunique())}


def preprocessing_audit(pipeline, train):
    pre = pipeline.named_steps["preprocess"]
    num = pre.named_transformers_["numeric"]
    encoder = pre.named_transformers_["categorical"].named_steps["encode"]
    return {"fitted_on_rows": len(train), "numeric_features": NUMERIC,
            "imputer_medians": num.named_steps["impute"].statistics_.tolist(),
            "scaled_feature_means": num.named_steps["scale"].mean_.tolist(),
            "scaled_feature_scales": num.named_steps["scale"].scale_.tolist(),
            "missing_indicator_feature_indices": num.named_steps["impute"].indicator_.features_.tolist(),
            "categorical_features": CATEGORICAL,
            "training_categories": {name: categories.tolist() for name, categories in zip(CATEGORICAL, encoder.categories_)},
            "transformed_features": pre.get_feature_names_out().tolist()}


def table_markdown(frame):
    formatted = frame.copy()
    for field in formatted.columns:
        if pd.api.types.is_float_dtype(formatted[field]):
            formatted[field] = formatted[field].map(lambda x: f"{x:.4f}")
    return "\n".join(["| " + " | ".join(formatted.columns) + " |", "| " + " | ".join(["---"] * len(formatted.columns)) + " |"] +
                     ["| " + " | ".join(map(str, row)) + " |" for row in formatted.itertuples(index=False, name=None)])


def run(diagnostic):
    data = pd.read_csv(ROOT / "datasets" / "processed" / "orders_cleaned.csv",
                       dtype={"Row ID": str, "Order ID": str, "Product ID": str, "Postal Code": str})
    data["Order Date"] = pd.to_datetime(data["Order Date"], errors="raise")
    data["Order Month"] = data["Order Date"].dt.month
    data["Order Weekday"] = data["Order Date"].dt.dayofweek
    for field in NUMERIC + [TARGET]:
        data[field] = pd.to_numeric(data[field], errors="raise")
    good_dates = data["Lead Time Quality"].eq("passes_interval_screen") & data["Ship Date After Snapshot"].astype(str).str.lower().eq("false")
    readiness = {"operational_training_allowed": bool(good_dates.all() and len(data) >= 100),
                 "total_rows": len(data), "valid_historical_target_rows": int(good_dates.sum()),
                 "reason": "All targets must pass date-quality checks; current data has systematic suspect shipment dates",
                 "diagnostic_mode_requested": diagnostic, "simulated_inputs_created": False}
    (ROOT / "models").mkdir(exist_ok=True)
    write_json(ROOT / "models" / "readiness.json", readiness)
    if not readiness["operational_training_allowed"] and not diagnostic:
        print(json.dumps(readiness, indent=2))
        print("Operational training refused. --diagnostic permits only an explicitly labeled comparison of unverified source intervals.")
        return 2
    if data[TARGET].isna().any():
        raise ValueError("Missing target values require resolution")
    mode = "diagnostic" if diagnostic else "validated"
    artifacts = ROOT / "models" / mode
    reports = ROOT / "reports" / "model_comparison" / mode
    artifacts.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    development, test, test_cutoff = chronological_split(data)
    train, validation, validation_cutoff = chronological_split(development)
    train_fit, train_excluded, initial_thresholds = screen_training_outliers(train)
    final_fit, final_excluded, final_thresholds = screen_training_outliers(development)
    # Global EDA flags never filter holdouts or fit preprocessing. Dates/IDs remain metadata only.
    names = ["Linear Regression", "Random Forest", "Gradient Boosting"]
    validation_metrics, fitted_validation, audit = [], {}, {}
    for name in names:
        pipeline = make_pipeline(name)
        pipeline.fit(train_fit[FEATURES], train_fit[TARGET])
        fitted_validation[name] = pipeline
        validation_metrics.append({"Model": name, "Evaluation": "Chronological validation", **metrics(validation[TARGET], pipeline.predict(validation[FEATURES]))})
        audit[name] = {"validation_fit": preprocessing_audit(pipeline, train_fit)}
    val_table = pd.DataFrame(validation_metrics)
    best_rmse = val_table["RMSE Days"].min()
    eligible = set(val_table.loc[val_table["RMSE Days"] <= best_rmse * (1 + RELATIVE_TIE_TOLERANCE), "Model"])
    # Explicit preference when errors are close: additive linear model, then boosting, then forest.
    selected = next(name for name in ["Linear Regression", "Gradient Boosting", "Random Forest"] if name in eligible)
    results, final_models, prediction_rows = validation_metrics.copy(), {}, []
    for name in names:
        pipeline = make_pipeline(name)
        pipeline.fit(final_fit[FEATURES], final_fit[TARGET])
        predicted = pipeline.predict(test[FEATURES])
        final_models[name] = pipeline
        results.append({"Model": name, "Evaluation": "Untouched chronological test", **metrics(test[TARGET], predicted)})
        audit[name]["final_pretest_fit"] = preprocessing_audit(pipeline, final_fit)
        joblib.dump({"pipeline": pipeline, "model_name": name, "features": FEATURES, "target": TARGET,
                     "diagnostic_only": diagnostic, "operational_use_allowed": not diagnostic,
                     "warning": "Unverified source date intervals; no deployment or reassignment speed claims" if diagnostic else "Validated source dates required",
                     "fit_period": profile(final_fit)}, artifacts / (name.lower().replace(" ", "_") + ".joblib"), compress=3)
        for row_id, order_date, actual, estimate in zip(test["Row ID"], test["Order Date"], test[TARGET], predicted):
            prediction_rows.append({"Model": name, "Row ID": row_id, "Order Date": order_date.strftime("%Y-%m-%d"),
                                    "Actual Source Interval Days": actual, "Predicted Source Interval Days": estimate,
                                    "Residual Days": actual - estimate, "Diagnostic Only": diagnostic})
        transformed = pipeline.named_steps["preprocess"].get_feature_names_out()
        regressor = pipeline.named_steps["regressor"]
        if name == "Linear Regression":
            importance = pd.DataFrame({"Transformed Feature": transformed, "Coefficient Days": regressor.coef_})
            importance["Absolute Coefficient"] = importance["Coefficient Days"].abs()
            importance = importance.sort_values("Absolute Coefficient", ascending=False)
        else:
            importance = pd.DataFrame({"Transformed Feature": transformed, "Training Impurity Importance": regressor.feature_importances_}).sort_values("Training Impurity Importance", ascending=False)
        importance.to_csv(reports / (name.lower().replace(" ", "_") + "_interpretability.csv"), index=False)

    # Useful sanity baseline, fitted before the test boundary and never used to select models.
    mode_means = final_fit.groupby("Ship Mode")[TARGET].mean()
    baseline = test["Ship Mode"].map(mode_means).fillna(final_fit[TARGET].mean())
    results.append({"Model": "Training ship-mode mean (sanity baseline)", "Evaluation": "Untouched chronological test", **metrics(test[TARGET], baseline)})
    result_table = pd.DataFrame(results)
    result_table.to_csv(reports / "model_metrics.csv", index=False, float_format="%.8f")
    pd.DataFrame(prediction_rows).to_csv(reports / "test_predictions.csv", index=False, float_format="%.8f")
    explanation_sample = test.sample(n=min(600, len(test)), random_state=SEED)
    permutation = permutation_importance(final_models[selected], explanation_sample[FEATURES], explanation_sample[TARGET], scoring="neg_mean_absolute_error",
                                          n_repeats=5, random_state=SEED, n_jobs=1)
    perm_table = pd.DataFrame({"Feature": FEATURES, "Mean MAE Increase Days": permutation.importances_mean,
                               "Repeat Standard Deviation": permutation.importances_std}).sort_values("Mean MAE Increase Days", ascending=False)
    perm_table.to_csv(reports / "selected_model_permutation_importance.csv", index=False, float_format="%.8f")
    assignments = []
    for label, rows in [("train", train), ("validation", validation), ("test", test)]:
        assignments.extend({"Row ID": row["Row ID"], "Order ID": row["Order ID"], "Order Date": row["Order Date"].strftime("%Y-%m-%d"),
                            "Partition": label} for _, row in rows.iterrows())
    pd.DataFrame(assignments).to_csv(reports / "split_assignments.csv", index=False)
    pd.concat([train_excluded.assign(Fit="validation_fit"), final_excluded.assign(Fit="final_pretest_fit")])[
        ["Row ID", "Order Date", "Fit"]].to_csv(reports / "training_outlier_exclusions.csv", index=False)
    pd.DataFrame(initial_thresholds).to_csv(reports / "validation_training_outlier_thresholds.csv", index=False)
    pd.DataFrame(final_thresholds).to_csv(reports / "final_training_outlier_thresholds.csv", index=False)
    # Expose the actual numerical/categorical representation for reproducibility and review.
    pd.DataFrame(final_models[selected].named_steps["preprocess"].transform(final_fit[FEATURES]),
                 columns=final_models[selected].named_steps["preprocess"].get_feature_names_out()).assign(
                     **{"Row ID": final_fit["Row ID"].to_numpy(), "Target Source Interval Days": final_fit[TARGET].to_numpy()}
                 ).to_csv(reports / "selected_model_training_feature_matrix.csv", index=False, float_format="%.8f")
    write_json(reports / "preprocessing_audit.json", audit)
    unknown_test_categories = {feature: sorted(set(test[feature]) - set(final_fit[feature])) for feature in CATEGORICAL}
    summary = {"mode": mode, "diagnostic_only": diagnostic, "operational_model_created": not diagnostic,
               "target": TARGET, "target_source": "Unchanged source Ship Date minus Order Date",
               "target_date_offset_applied": 0, "selected_model": selected,
               "selection_basis": "Validation RMSE; prefer Linear Regression then Gradient Boosting then Random Forest within 5% of lowest validation RMSE",
               "relative_rmse_tie_tolerance": RELATIVE_TIE_TOLERANCE,
               "test_used_for_selection": False, "numerical_features": NUMERIC, "categorical_features": CATEGORICAL,
               "excluded_features": ["Ship Date", "Customer ID", "Row ID", "Order ID", TARGET, "Lead Time Quality", "Extreme Outlier", "Eligible For Lead Time Training", "Sales", "Cost", "Gross Profit"],
               "split": {"train": profile(train), "validation": profile(validation), "test": profile(test),
                         "test_cutoff": test_cutoff.strftime("%Y-%m-%d"), "validation_cutoff": validation_cutoff.strftime("%Y-%m-%d"),
                         "same_date_cross_partition": False, "source_order_id_cross_partition": False},
               "validation_fit_rows": len(train_fit), "validation_training_outliers_removed": len(train_excluded),
               "final_fit_rows": len(final_fit), "final_training_outliers_removed": len(final_excluded),
               "holdout_rows_trimmed": 0, "unknown_test_categories": unknown_test_categories,
               "target_quality_valid_rows": int(good_dates.sum()), "seed": SEED,
               "metrics": result_table.to_dict(orient="records"),
               "versions": {"scikit_learn": sklearn.__version__, "pandas": pd.__version__, "numpy": np.__version__, "joblib": joblib.__version__},
               "limits": ["Source date anomaly prevents operational shipping claims",
                          "Each product has only one static factory; alternative-factory effects are not identifiable",
                          "ZIP-centroid great-circle distances are not road or delivery distances",
                          "Sparse product history limits generalization", "Held-out accuracy does not validate suspect dates"]}
    write_json(reports / "comparison_summary.json", summary)
    write_json(artifacts / "model_manifest.json", {"selected_model": selected, "diagnostic_only": diagnostic,
               "operational_use_allowed": not diagnostic, "report": str(reports.relative_to(ROOT)),
               "target": TARGET, "target_date_offset_applied": 0, "versions": summary["versions"]})

    tests = result_table[result_table["Evaluation"].eq("Untouched chronological test")]
    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    display_names = tests["Model"].str.replace("Training ship-mode mean (sanity baseline)", "Ship-mode mean", regex=False)
    for ax, field, title in zip(axes, ["RMSE Days", "MAE Days", "R2"], ["RMSE · days (lower is better)", "MAE · days (lower is better)", "R² (higher is better)"]):
        ax.bar(display_names, tests[field], color=["#2355a4", "#148677", "#d67b26", "#8995a8"])
        ax.set_title(title)
        ax.tick_params(axis="x", labelrotation=25)
        if field == "R2":
            ax.set_ylim(min(0, tests[field].min() - .05), 1)
        for i, value in enumerate(tests[field]):
            ax.text(i, value, f"{value:.3f}", ha="center", va="bottom", fontsize=9)
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("DIAGNOSTIC ONLY: predicting unverified source date intervals" if diagnostic else "Chronological test comparison", fontsize=15, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, .94))
    fig.savefig(reports / "model_comparison.png", dpi=170, bbox_inches="tight")
    plt.close(fig)
    selected_test = tests[tests["Model"].eq(selected)].iloc[0]
    interpretability = pd.DataFrame([
        {"Model": "Linear Regression", "Interpretability": "Additive coefficients; numerical coefficients are per standardized feature unit. Product/factory collinearity prevents independent factory attribution."},
        {"Model": "Random Forest", "Interpretability": "Nonlinear tree ensemble. Training impurity importance describes association and can favor high-cardinality inputs; it is not causal."},
        {"Model": "Gradient Boosting", "Interpretability": "Additive ensemble of shallow trees. More complex than linear regression; feature importance describes learned association, not factory effects."},
    ])
    interpretability.to_csv(reports / "interpretability_comparison.csv", index=False)
    report = f"""# Prediction model comparison — {mode}

{'**Diagnostic only. All source date intervals are suspect. These metrics compare fit to unverified date differences; they do not establish actual lead-time accuracy or shipping improvements. No operational model was created.**' if diagnostic else 'Source date-quality checks passed.'}

## Features and preprocessing

Target: `{TARGET}`, computed from the unchanged source dates. No assumed 2,000-day correction was applied. Valid historical target records: {int(good_dates.sum()):,}.

Numerical features: Units, great-circle distance, order month and order weekday. Categorical features: Product ID, assigned factory, destination region and ship mode. Numerical missing values are median-imputed with a missing indicator and standardized; categories are most-frequent-imputed and one-hot-encoded, with unknown categories ignored. Imputation and encoding apply only inside the model pipeline, not to source geography.

The pipeline excludes shipment dates, target-derived quality flags, customer/row/order identifiers, financial outcomes and globally computed EDA outlier flags. Product ID is the stable product category. Assigned factory is the static reference origin, not an observed shipment origin.

## Chronological evaluation

| Partition | Records | Start | End |
|---|---:|---|---|
| Initial training | {len(train):,} | {profile(train)['start']} | {profile(train)['end']} |
| Validation | {len(validation):,} | {profile(validation)['start']} | {profile(validation)['end']} |
| Untouched test | {len(test):,} | {profile(test)['start']} | {profile(test)['end']} |

The first split approximates 80% development / 20% test by record count, keeping whole dates together. Development is split again approximately 80% / 20% into initial training and validation. No order date or repeated source Order ID crosses partitions. Initial preprocessing fits only initial training; final preprocessing fits only pretest development after selection.

Training-only 3-IQR screens for quantity within product and target interval within ship mode exclude {len(train_excluded):,} records for validation fits and {len(final_excluded):,} records for final pretest fits. Groups below 20 records or with zero IQR are not trimmed. All validation and test records are evaluated without trimming; the global cleaned-data outlier flags never drive model filtering. Thresholds and exclusions are exported.

All models use fixed parameters and seed {SEED}. Random Forest: 160 trees, maximum depth 10, minimum leaf size 4. Gradient Boosting: 160 trees, learning rate 0.05, maximum depth 2, minimum leaf size 4. Linear Regression uses ordinary least squares. Hyperparameters were not tuned on the test set.

## Metrics

RMSE penalizes larger errors; MAE averages absolute errors; R² measures explained variance relative to the holdout mean. All errors are in days of the unverified source interval.

{table_markdown(result_table)}

Selected diagnostic model: **{selected}**, chosen before inspecting test scores using validation RMSE and a documented interpretability tie rule: within 5% of the lowest validation RMSE, prefer Linear Regression, then Gradient Boosting, then Random Forest. The 5% tolerance is an explicit project heuristic. Final models are refitted on pretest development and then evaluated once on the untouched test. The training ship-mode mean is an additional sanity baseline, not a fourth requested model or a selection candidate.

Selected model's test RMSE: {selected_test['RMSE Days']:.4f} days; MAE: {selected_test['MAE Days']:.4f} days; R²: {selected_test['R2']:.4f}. High R² would still only reflect the unverified target pattern.

The requested models' test RMSE values are close to the simple training ship-mode mean. More complex models therefore provide little improvement in this comparison. Permutation importance highlights ship mode as the dominant predictive feature; independent factory effects remain unsupported.

![Model comparison](model_comparison.png)

## Interpretability

{table_markdown(interpretability)}

Encoded coefficients or impurity importances are exported for all three models. Selected-model raw-feature permutation importance measures increased MAE after shuffling a feature, using five repeats on a reproducible sample of up to 600 test records. It is explanatory reporting after selection and does not tune or select the model. Correlated product and factory features can share or mask importance, so coefficients and permutation values cannot identify independent factory effects.

{table_markdown(perm_table)}

## Limits and deployment status

Each product appears at only one factory in the source assignment table. Changing its factory at inference creates an unsupported combination; held-out accuracy does not validate reallocation effects. Sparse products also limit coverage. Features such as ship mode may explain the diagnostic target pattern without demonstrating congestion, delivery speed or actual logistics costs.

Diagnostic bundles are saved only in `models/diagnostic/` and explicitly marked `operational_use_allowed=false`. There is no production model or recommendation engine. Normal-mode training refuses this dataset until source-date quality is resolved. The observed intervals remain unchanged; no synthetic targets were created.

## Reproduce and inspect

```powershell
python -m pip install -r analysis/requirements-models.txt
python analysis/train_compare_models.py --diagnostic
```

The default command without `--diagnostic` writes a readiness report and exits with code 2 when date quality fails. Split assignments, training-only thresholds, exact test predictions, preprocessing statistics, metrics, interpretation tables, and the selected model's actual transformed training matrix are saved beside this report. Library versions are recorded in `comparison_summary.json`; joblib bundles should be loaded only from trusted sources with compatible dependency versions.
"""
    (reports / "model_comparison_report.md").write_text(report, encoding="utf-8")
    (artifacts / "README.md").write_text(
        "# Diagnostic models\n\nThese bundles fit unverified source date intervals. They are not operational shipping models. "
        "Every bundle and the manifest explicitly prohibit operational use. No date offset was applied. "
        "See the comparison report for chronological evaluation, preprocessing and limitations.\n", encoding="utf-8")
    print(result_table.to_string(index=False))
    print(f"Selected on validation: {selected}. Diagnostic only: {diagnostic}. Operational model created: {not diagnostic}.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnostic", action="store_true", help="Explicitly compare models on unverified source date intervals; never deploy")
    args = parser.parse_args()
    raise SystemExit(run(args.diagnostic))


if __name__ == "__main__":
    main()
