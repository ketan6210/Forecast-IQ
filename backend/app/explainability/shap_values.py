import numpy as np

from backend.app.data.frequency import future_dates


def explain_tree(model, horizon: int) -> dict:
    """Native exact TreeSHAP, verified against raw predictions before clipping/calibration."""
    model.predict(horizon)
    reference = model.training_features
    global_values = np.asarray(model.contributions(reference))
    local_values = np.asarray(model.contributions(model.forecast_features))
    raw = np.asarray(model.regressor.predict(model.forecast_features))
    if not np.allclose(local_values.sum(axis=1), raw, rtol=1e-4, atol=1e-4):
        raise ValueError("SHAP contributions did not reconstruct model predictions.")
    importance = [
        {
            "feature": feature,
            "mean_absolute_shap": float(np.abs(global_values[:, i]).mean()),
            "mean_shap": float(global_values[:, i].mean()),
        }
        for i, feature in enumerate(model.features)
    ]
    importance.sort(key=lambda row: row["mean_absolute_shap"], reverse=True)
    dates = future_dates(model.history.date.iloc[-1], horizon, model.frequency)
    forecasts = []
    for row, date in enumerate(dates):
        contributions = [
            {
                "feature": feature,
                "value": float(model.forecast_features[row, i]),
                "shap_value": float(local_values[row, i]),
            }
            for i, feature in enumerate(model.features)
        ]
        contributions.sort(key=lambda item: abs(item["shap_value"]), reverse=True)
        forecasts.append(
            {
                "date": date.date().isoformat(),
                "base_value": float(local_values[row, -1]),
                "raw_prediction": float(raw[row]),
                "drivers": contributions,
            }
        )
    return {
        "model": model.name,
        "method": "Native exact TreeSHAP",
        "reference_rows": len(reference),
        "global_importance": importance,
        "forecast_drivers": forecasts,
        "summary_samples": [
            {
                "feature": feature,
                "value": float(reference[row, i]),
                "shap_value": float(global_values[row, i]),
            }
            for row in range(min(len(reference), 40))
            for i, feature in enumerate(model.features)
        ],
        "notes": [
            "Global importance summarizes up to 200 recent training rows.",
            "Contributions explain this tree model's raw point prediction, "
            "before nonnegative clipping and residual calibration.",
            "Positive/negative contributions are relative to the SHAP expected value, "
            "not causal effects or changes from yesterday.",
            "Correlated lags can share attribution. A candidate explanation is not "
            "the champion's explanation unless its model name matches.",
        ],
    }
