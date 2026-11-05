# Upload error diagnosis

The screenshot's exact message, `Missing required columns: product_id, store_id,
units_sold`, was reproduced by selecting the supplied **test.csv** in the live app
on port 5180. The screenshot alone does not establish which file the user selected.

Selecting the original **train.csv**, with all mapping fields left at their defaults,
successfully uploaded **913,000 rows**. The file itself required no edits.

| Supplied file | Columns | Purpose |
|---|---|---|
| train.csv | date, store, item, sales | Historical sales for training; uploads successfully |
| test.csv | id, date, store, item | Future rows without observed sales; cannot train a model |
| sample_submission.csv | id, sales | Output template without dated history; cannot train a model |

The app now includes the selected filename in upload errors. These two known
non-training schemas receive specific guidance to upload `train.csv`, while the
structured validation details remain available to API clients. The upload card also
identifies `train.csv` as the file to choose for Kaggle Store Item data.

To upload, reload the page using the arrow beside `http://localhost:5180/`, select
**Change dataset** if needed, then **Upload CSV**. Choose:

```text
/Users/ketan/Downloads/demand-forecasting-kernels-only/train.csv
```

Leave the column fields at their defaults. The app recognizes the Kaggle header and
uses `date` for time, `sales` for demand, `store` for store and `item` for product.

The [initial browser reproduction](upload-error-recheck.json) records both rejected
files and the successful full upload. It used the original files from Downloads;
all uploads went to the local ForecastIQ app, with no external upload.
