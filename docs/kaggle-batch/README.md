# Full Kaggle Store Item forecast

Completed **500 store–item series and all 45,000 test rows** using the original
913,000-row training file. Download [submission.csv](submission.csv), which contains
exactly `id,sales` in the supplied template's ID order. Each sales value is a daily
P50 forecast. All output remains on this computer; nothing was submitted to Kaggle.

The run completed on October 5, 2026, local time (October 6 UTC), in 497.43 seconds
using four local worker processes. [Measured results and provenance](summary.json)
and [independent verification](verification.json) accompany the CSV files.

## Historical test result

These scores use **October 3–December 31, 2017**, covering 45,000 observed sales
values that were held out during model selection. The supplied `test.csv` covers
January–March 2018 and contains no actual sales, so these are historical validation
scores, not a Kaggle score. The placeholder sales in `sample_submission.csv` were
never used as training targets or observed demand.

| Measure | Result |
|---|---:|
| Aggregate WAPE | 14.81% |
| MAE per store–item day | 8.09 units |
| RMSE per store–item day | 10.53 units |
| sMAPE | 16.20% |
| Median series WAPE | 15.24% |
| Observed P10–P90 coverage | 73.91% |

WAPE is total absolute prediction error divided by total observed sales; it is an
error measure. The interval coverage is below the nominal 80%, so the uncertainty
bands underestimate some historical variation. Future performance remains unknown.

## Models and evaluation

Each series compared naive, seasonal naive, moving average, ETS, LightGBM and
XGBoost using three chronological 90-day folds and expanding training history.
All six candidates completed for every series: **3,000 successful evaluations**,
with no candidate failures or training-result warnings.

Model selection used mean WAPE across the selection folds. Selection history ended
April 5, 2017. A separate 180-day period, April 6–October 2, supplied residuals for
interval calibration, followed by the independent 90-day historical test.
Production models were then fitted on all 1,826 days through December 31, 2017.

| Selected model | Series |
|---|---:|
| LightGBM | 441 |
| XGBoost | 59 |

This batch uses fixed model settings (`tune=False`) and six candidates. The earlier
[single-series example](../kaggle-results/README.md) used ten candidates and a bounded
tree-parameter search. Its selected model and predictions can therefore differ.
The batch does not calculate inventory orders or costs; those require business inputs.

## January–March 2018 predictions

| Month | Sum of daily P50 forecasts across all series |
|---|---:|
| January | 766,575.60 units |
| February | 715,917.89 units |
| March | 844,085.35 units |
| Total | 2,326,578.85 units |

These are sums of daily estimates, not calibrated quantiles for aggregate demand.
Daily P10/P90 values are marginal intervals, not joint bounds for the entire catalog.

## Files and storage locations

| File | Contents |
|---|---|
| [submission.csv](submission.csv) | All 45,000 IDs and predicted sales, ready for review |
| [predictions-with-intervals.csv](predictions-with-intervals.csv) | ID, date, store, item, P10, P50 and P90 |
| [series-results.csv](series-results.csv) | Champion, historical metrics and forecast total for each of 500 series |
| [historical-test-predictions.csv](historical-test-predictions.csv) | Historical actuals and predicted quantiles for checking errors |
| [monthly-forecast.csv](monthly-forecast.csv) | Catalog forecast totals by month |
| [summary.json](summary.json) | Aggregate results, configuration and source hashes |
| [verification.json](verification.json) | Checks of IDs, predictions, metrics and persisted artifacts |

The original files remain unchanged in
`/Users/ketan/Downloads/demand-forecasting-kernels-only/`.
The report and exported predictions are in
`/Users/ketan/Desktop/ForecastIQ/docs/kaggle-batch/`.
The 500 complete run records are in
`/Users/ketan/Desktop/ForecastIQ/storage/kaggle-batch/runs/`;
models and calibrators are in `storage/kaggle-batch/artifacts/<run_id>/`.
`storage/kaggle-batch/manifest.json` records input and source-code hashes.

The earlier browser upload remains in the local ForecastIQ app at
[localhost:5180](http://localhost:5180/?dataset=ce584990-809f-468f-80fa-727d34d4a0de).
Its normalized CSV is stored inside the backend container at
`/app/storage/ce584990-809f-468f-80fa-727d34d4a0de.csv`, backed by the Docker Compose
`dataset_storage` volume; its metadata and saved training-run records are in local
PostgreSQL. Choose **Advanced forecasting** and use **Open a saved training run** to open
the earlier Store 1 / Item 1 LightGBM example.

This full batch reads the original files and calls the same training pipeline
locally. It does not change the app database, so its 500 runs are available in the
exported files and checkpoints rather than the app's saved-run dropdown.

To upload the original training file yourself, reload ForecastIQ, choose
**Change dataset**, then select `train.csv` with the default column settings.
The app now recognizes `date,store,item,sales` automatically and allows up to
1,000,000 rows. Use `train.csv` for that upload; the other two CSVs do not contain
historical sales labels.

## Verification and reproduction

The final checks confirmed the exact 45,000 IDs and original order, 90 predictions
per series, finite nonnegative predictions, ordered intervals and unchanged source
CSVs. Every exported forecast matches its saved checkpoint. Historical actuals
match `train.csv`, and recomputed aggregate metrics match the summary.
All 500 runs have chronological partitions. Integrity hashes passed for all 3,500
model/calibrator files. Three sampled champion models, covering both selected model
types, reproduced all 90 saved quantile forecasts exactly after loading.

Run from the ForecastIQ project directory using its existing Python environment:

```sh
DYLD_LIBRARY_PATH="$PWD/.venv/lib/python3.12/site-packages/torch/lib" \
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
PYTHONWARNINGS=once::DeprecationWarning \
.venv/bin/python -m scripts.run_kaggle_batch \
  --input-dir /Users/ketan/Downloads/demand-forecasting-kernels-only \
  --dataset-id ce584990-809f-468f-80fa-727d34d4a0de \
  --workers 4
```

The `DYLD_LIBRARY_PATH` setting uses the OpenMP library already present in this
workspace's PyTorch installation. Existing checkpoints are reused only when the
input hashes, training source, settings and storage path match the saved manifest.
For a new training experiment, use new `--storage-dir` and `--output-dir` paths.
The batch runner is [scripts/run_kaggle_batch.py](../../scripts/run_kaggle_batch.py).
