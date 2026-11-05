from sklearn.model_selection import ParameterSampler

from backend.app.models.baselines import PeriodBaseline
from backend.app.models.lightgbm_model import LightGBMModel
from backend.app.models.statistical import StatisticalModel
from backend.app.models.supervised import SupervisedModel
from backend.app.models.xgboost_model import XGBoostModel

FAMILIES = {
    "naive": "baseline",
    "seasonal_naive": "baseline",
    "moving_average": "baseline",
    "linear_regression": "baseline",
    "arima": "statistical",
    "sarima": "statistical",
    "ets": "statistical",
    "lightgbm": "machine_learning",
    "xgboost": "machine_learning",
    "nbeats": "neural",
}


def parameter_grid(
    name: str, tune: bool, epochs: int, trials: int = 4, seed: int = 42
) -> list[dict]:
    """Seeded parameter sampling; every candidate uses the same chronological folds."""
    if tune and name in {"lightgbm", "xgboost"}:
        space = {
            "n_estimators": [60, 80, 120, 160],
            "learning_rate": [0.03, 0.05, 0.1],
            "reg_lambda": [1.0, 3.0, 5.0],
        }
        if name == "lightgbm":
            space.update(num_leaves=[7, 15], max_depth=[4, 5, 6], min_child_samples=[10, 15, 20])
        else:
            space.update(max_depth=[2, 3, 4], min_child_weight=[3, 5, 10])
        return list(ParameterSampler(space, n_iter=trials, random_state=seed))
    if name == "lightgbm":
        grid = [
            {
                "n_estimators": 80,
                "num_leaves": 7,
                "max_depth": 3,
                "learning_rate": 0.05,
                "min_child_samples": 10,
                "reg_lambda": 1.0,
            },
        ]
    elif name == "xgboost":
        grid = [
            {
                "n_estimators": 80,
                "max_depth": 2,
                "learning_rate": 0.05,
                "min_child_weight": 3,
                "reg_lambda": 1.0,
            },
        ]
    elif name == "nbeats":
        grid = [{"epochs": epochs}]
    else:
        grid = [{}]
    return grid


def create_model(
    name: str, frequency: str, season: int, horizon: int, params: dict, training_size: int
):
    common = dict(frequency=frequency, season=season, horizon=horizon, **params)
    if name in {"naive", "seasonal_naive", "moving_average"}:
        return PeriodBaseline(name=name, **common)
    if name in {"arima", "sarima", "ets"}:
        return StatisticalModel(name=name, **common)
    if name == "nbeats":
        if training_size < 512:
            raise ValueError(
                "N-BEATS skipped: at least 512 periods are required in every training fold."
            )
        from backend.app.models.deep_forecaster import NBeatsModel

        return NBeatsModel(**common)
    return {
        "linear_regression": SupervisedModel,
        "lightgbm": LightGBMModel,
        "xgboost": XGBoostModel,
    }[name](**common)
