from backend.app.features.feature_engineering import FeatureEngineer


class AdvancedFeatures(FeatureEngineer):
    """Period-based lags; timestamp-derived calendars support daily, weekly, monthly data."""

    # Keep the class path stable so earlier saved artifacts remain loadable.
