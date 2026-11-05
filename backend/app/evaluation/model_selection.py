def rank_models(rows: list[dict]) -> list[dict]:
    """Require all folds; aggregate WAPE first, then consistency and secondary checks."""
    successful = [row for row in rows if row["status"] == "ok"]

    def value(row: dict, metric: str, statistic: str = "mean") -> float:
        result = row["summary"][metric][statistic]
        return result if result is not None else float("inf")

    eligible = [r for r in successful if r["summary"]["wape"]["defined_folds"] == len(r["folds"])]
    ranked = sorted(
        eligible,
        key=lambda r: (
            value(r, "wape"),
            value(r, "wape", "std"),
            value(r, "smape"),
            value(r, "mase"),
            r["forecast_stability"],
            r["model"],
        ),
    )
    if not ranked:
        # All-zero validation demand: do not pretend an undefined WAPE won.
        ranked = [r for r in successful if r["model"] == "naive"]
    for rank, row in enumerate(ranked, start=1):
        row["rank"] = rank
    return ranked
