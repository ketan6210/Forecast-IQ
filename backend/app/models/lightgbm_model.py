from backend.app.models.supervised import SupervisedModel


class LightGBMModel(SupervisedModel):
    name = "lightgbm"

    def estimator(self):
        from lightgbm import LGBMRegressor

        return LGBMRegressor(
            objective="regression",
            random_state=42,
            n_jobs=1,
            deterministic=True,
            force_col_wise=True,
            verbosity=-1,
            **self.params,
        )

    def contributions(self, features):
        return self.regressor.booster_.predict(features, pred_contrib=True)
