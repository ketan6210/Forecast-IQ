# Measured synthetic-demo experiment

Run at 2026-09-24T21:10:38.892555+00:00. Reproduce with `python -m scripts.run_experiment`.

These are actual local measurements on synthetic data, not external benchmark results.
One series: **STORE_01 / SKU_001**, requested horizon **28 days**.

- Data: 4,380 rows; 2 stores; 6 products; 2025-01-01 → 2025-12-31.
- Missing rate: 0.00%.
- Selected baseline: **moving_average**, based only on validation WAPE.
- Forecast total: **864.00 units**.

## Validation metrics

| Model | MAE | RMSE | WAPE | sMAPE | MASE |
|---|---:|---:|---:|---:|---:|
| naive | 4.5818 | 6.0693 | 13.969% | 13.992% | 0.6438 |
| seasonal_naive | 7.7091 | 9.6163 | 23.503% | 23.913% | 1.0832 |
| moving_average | 4.0805 | 5.3976 | 12.441% | 12.380% | 0.5734 |
| linear_regression | 5.3789 | 6.6308 | 16.399% | 17.442% | 0.7558 |

## Test metrics

| Model | MAE | RMSE | WAPE | sMAPE | MASE |
|---|---:|---:|---:|---:|---:|
| naive | 6.9273 | 9.1124 | 20.572% | 21.217% | 0.9934 |
| seasonal_naive | 6.4909 | 7.8752 | 19.276% | 19.973% | 0.9308 |
| moving_average | 5.7636 | 7.7682 | 17.117% | 17.140% | 0.8265 |
| linear_regression | 36.3350 | 119.8467 | 107.906% | 37.858% | 5.2104 |

## System timings

| Operation | Seconds |
|---|---:|
| dataset_load_seconds | 0.023215 |
| feature_generation_seconds | 0.003641 |
| training_seconds | 0.376296 |
| forecast_generation_seconds | 0.000038 |
| full_forecast_request_seconds | 0.396942 |

Training includes fitting all four models, validation forecasting, test refits and forecasting, and fitting the selected model on all history. Forecast generation is prediction-only latency after that final fit. Full request timing includes loading and persistence via the in-process HTTP test client, but excludes network transport.

Timing is one local run, not a performance benchmark or latency guarantee.

## Split

| Partition | Start | End | Days |
|---|---|---|---:|
| train | 2025-01-01 | 2025-09-12 | 255 |
| validation | 2025-09-13 | 2025-11-06 | 55 |
| test | 2025-11-07 | 2025-12-31 | 55 |

Each holdout uses a fixed forecast origin. Future prices are carried from the last known price; future promotion, discount and holiday indicators are zero.

Environment: `{'python': '3.12.13', 'platform': 'macOS-26.6.2-arm64-arm-64bit', 'numpy': '2.5.3', 'pandas': '2.3.3', 'scikit_learn': '1.9.1'}`
