from backend.app.models.supervised import SupervisedModel


class XGBoostModel(SupervisedModel):
    name = "xgboost"

    def estimator(self):
        from xgboost import XGBRegressor

        return XGBRegressor(
            objective="reg:squarederror",
            random_state=42,
            n_jobs=1,
            tree_method="hist",
            **self.params,
        )

    def contributions(self, features):
        from xgboost import DMatrix

        return self.regressor.get_booster().predict(
            DMatrix(features), pred_contribs=True, approx_contribs=False
        )
