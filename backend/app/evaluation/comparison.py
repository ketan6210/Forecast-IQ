from backend.app.schemas.forecast import Metrics


def select_model(validation: dict[str, Metrics]) -> tuple[str, str]:
    """Rank validation WAPE, then MASE; never accept test results for selection."""
    eligible = [(name, metrics) for name, metrics in validation.items() if metrics.wape is not None]
    if not eligible:
        return (
            "naive",
            "Validation WAPE is undefined for every model; deterministic naive fallback.",
        )
    name, _ = min(
        eligible,
        key=lambda item: (
            item[1].wape,
            item[1].mase if item[1].mase is not None else float("inf"),
            item[0],
        ),
    )
    return name, "Lowest validation WAPE; ties use lower validation MASE, then model name."
