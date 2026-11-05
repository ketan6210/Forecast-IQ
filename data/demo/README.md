This is **synthetic demo data**, generated with NumPy seed 42 by
`scripts/generate_demo.py`. It contains 2 stores × 6 products × 365 days in 2025,
annual seasonality, weekend effects, promotions, variable prices and synthetic
inventory balances. It is not real retail data or an external forecasting benchmark.

`discount` is a fraction in [0, 1]; `promotion` and `holiday` are binary indicators.
Inventory values are illustrative daily snapshots, not a simulated stock ledger.
Price currency is intentionally unspecified; revenue is in the same currency as price.
