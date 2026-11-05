# Phase 2 measured experiments

Measured at 2026-09-27T05:31:52.520619+00:00 on `{'python': '3.12.13', 'platform': 'macOS-26.6.2-arm64-arm-64bit'}`.

Reproduce with `python -m scripts.run_phase2_experiment --include-neural` after installing the optional PyTorch requirements. Omit `--include-neural` for core only.

These are actual, deterministic synthetic-data experiments, not external benchmark results. Timing is a single local run, excludes network transport, and is not a guarantee. The JSON report contains every fold, trial, forecast, SHAP value, and artifact manifest.

## Retail demo: STORE_01 / SKU_001

365 daily observations; horizon 28; three expanding folds; bounded two-setting tree search. Baselines are legitimate candidates and may beat more complex models.

Champion: **xgboost**, selected using mean rolling WAPE.

### Rolling selection metrics (mean across folds)

| Rank | Model | WAPE | sMAPE | MASE | RMSE | MAE | WAPE std |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | xgboost | 12.605% | 12.657% | 0.6806 | 6.2221 | 4.8138 | 1.438% |
| 2 | lightgbm | 13.057% | 13.098% | 0.7008 | 6.3860 | 4.9588 | 0.365% |
| 3 | linear_regression | 14.106% | 14.447% | 0.7509 | 7.0670 | 5.3169 | 2.433% |
| 4 | ets | 15.086% | 15.636% | 0.7988 | 7.4775 | 5.6579 | 4.218% |
| 5 | moving_average | 15.563% | 15.589% | 0.8367 | 7.5460 | 5.9201 | 0.890% |
| 6 | seasonal_naive | 16.365% | 17.045% | 0.8768 | 8.1213 | 6.2024 | 2.673% |
| 7 | sarima | 17.777% | 17.516% | 0.9458 | 8.0733 | 6.6985 | 2.947% |
| 8 | arima | 19.412% | 18.872% | 1.0281 | 8.5594 | 7.2831 | 4.891% |
| 9 | naive | 25.719% | 29.113% | 1.3414 | 10.9682 | 9.5119 | 14.866% |
| — | nbeats: skipped | — | — | — | — | — | — |

### Final untouched test (calibrated P50)

| Metric | Measured value |
|---|---:|
| mae | 8.3231 |
| rmse | 9.7956 |
| wape | 24.583% |
| smape | 27.058% |
| mase | 1.1783 |
| pinball_p10 | 2.892244 |
| pinball_p50 | 4.161544 |
| pinball_p90 | 1.107138 |
| coverage | 89.2857% |
| mean_interval_width | 34.942892 |

### Evaluation boundaries

| Partition | Start | End | Periods |
|---|---|---|---:|
| selection | 2025-01-01 | 2025-10-08 | 281 |
| calibration | 2025-10-09 | 2025-12-03 | 56 |
| test | 2025-12-04 | 2025-12-31 | 28 |

- Calibration residuals: 56; P10/P50/P90 signed offsets: `[-26.697471618652344, -6.022317886352539, 8.245420455932617]`.
- Service training duration: 2.512580 s.
- Full in-process HTTP request: 2.532643 s.
- Saved model + calibrator reload reproduced quantiles; CSV row count verified.
- SHAP explanations calculated for: lightgbm, xgboost.

- nbeats: N-BEATS skipped: at least 512 periods are required in every training fold.

## Eligible N-BEATS example

700 synthetic daily observations generated with NumPy seed 84. Poisson demand with mild trend and weekly seasonality; horizon 14; three expanding folds; 12 epochs per N-BEATS fit. This is a functionality example, not a neural benchmark.

Champion: **xgboost**, selected using mean rolling WAPE.

### Rolling selection metrics (mean across folds)

| Rank | Model | WAPE | sMAPE | MASE | RMSE | MAE | WAPE std |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | xgboost | 7.739% | 8.317% | 0.5077 | 5.2988 | 4.1419 | 0.291% |
| 2 | lightgbm | 8.182% | 8.731% | 0.5355 | 5.3956 | 4.3667 | 0.952% |
| 3 | nbeats | 8.633% | 9.010% | 0.5641 | 5.7764 | 4.5992 | 1.476% |
| 4 | seasonal_naive | 11.509% | 12.200% | 0.7584 | 7.5210 | 6.1905 | 2.750% |
| 5 | moving_average | 15.100% | 15.480% | 0.9900 | 9.6169 | 8.0748 | 1.657% |
| 6 | naive | 21.805% | 23.545% | 1.4451 | 13.3722 | 11.8095 | 7.800% |

### Final untouched test (calibrated P50)

| Metric | Measured value |
|---|---:|
| mae | 6.5496 |
| rmse | 8.0041 |
| wape | 11.306% |
| smape | 11.880% |
| mase | 0.8095 |
| pinball_p10 | 1.578451 |
| pinball_p50 | 3.274794 |
| pinball_p90 | 1.070208 |
| coverage | 85.7143% |
| mean_interval_width | 24.578957 |

### Evaluation boundaries

| Partition | Start | End | Periods |
|---|---|---|---:|
| selection | 2023-01-01 | 2024-10-19 | 658 |
| calibration | 2024-10-20 | 2024-11-16 | 28 |
| test | 2024-11-17 | 2024-11-30 | 14 |

- Calibration residuals: 28; P10/P50/P90 signed offsets: `[-9.529365539550781, 1.590188980102539, 15.049591064453125]`.
- Service training duration: 2.509743 s.
- Full in-process HTTP request: 2.521673 s.
- Saved model + calibrator reload reproduced quantiles; CSV row count verified.
- SHAP explanations calculated for: lightgbm, xgboost.


## Interpretation and targets

WAPE <15%, sMAPE <18%, MASE <0.9 and interval coverage near 80–90% are objectives, not acceptance criteria for software correctness. The short demo can miss these objectives. No parameter or interval was chosen using final-test performance.

Intervals use separate prequential signed residuals pooled across forecast leads. Small calibration samples, time dependence and distribution changes can cause substantial undercoverage. These empirical marginal intervals carry no unconditional coverage guarantee. Refitting on all history happens only after test evaluation.
