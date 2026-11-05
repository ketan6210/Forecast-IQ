import type { Metrics, Metric } from "./types";

export interface QuantilePoint {
  date: string;
  p10: number;
  p50: number;
  p90: number;
  actual?: number;
}
export interface Bound {
  start: string;
  end: string;
  periods: number;
}
export interface Fold {
  fold: number;
  train: Bound;
  validation: Bound;
  metrics: Metrics;
  predictions: { date: string; actual: number; predicted: number }[];
}
export interface Aggregate {
  mean: number | null;
  median: number | null;
  std: number | null;
  best_fold: number | null;
  worst_fold: number | null;
  defined_folds: number;
}
export interface CandidateResult {
  model: string;
  family: string;
  status: string;
  rank: number | null;
  reason?: string;
  summary?: Record<Metric, Aggregate>;
  folds?: Fold[];
  parameters?: Record<string, number>;
  forecast_stability?: number;
  duration_seconds?: number;
  tuning_duration_seconds?: number;
  notes?: string[];
  trials: {
    parameters: Record<string, number>;
    status: string;
    reason?: string;
    duration_seconds: number;
  }[];
}
export interface Explanation {
  model: string;
  method: string;
  reference_rows: number;
  global_importance: {
    feature: string;
    mean_absolute_shap: number;
    mean_shap: number;
  }[];
  forecast_drivers: {
    date: string;
    base_value: number;
    raw_prediction: number;
    drivers: { feature: string; value: number; shap_value: number }[];
  }[];
  summary_samples: { feature: string; value: number; shap_value: number }[];
  notes: string[];
}
export interface AdvancedRun {
  run_id: string;
  dataset_id: string;
  store_id: string;
  product_id: string;
  frequency: string;
  forecast_horizon: number;
  champion_model: string;
  created_at: string;
  configuration: {
    horizon: number;
    folds: number;
    window: string;
    window_size: number;
    frequency: string;
    missing_policy: string;
    tune: boolean;
    tuning_trials?: number;
    tuning_seed?: number;
    models: string[];
    neural_epochs: number;
  };
  selection_reason: string;
  comparison: CandidateResult[];
  forecast: QuantilePoint[];
  history: { date: string; actual: number }[];
  test_metrics: Metrics;
  probabilistic_metrics: {
    pinball_p10: number;
    pinball_p50: number;
    pinball_p90: number;
    coverage: number;
    mean_interval_width: number;
  };
  partitions: { selection: Bound; calibration: Bound; test: Bound };
  calibration: {
    method: string;
    residual_count: number;
    offsets: number[];
    nominal_coverage: number;
  };
  diagnostics: {
    trend: string;
    trend_slope_per_period: number;
    seasonality_detected: boolean;
    seasonal_period: number;
    seasonal_autocorrelation: number | null;
    missing_periods: number;
    outlier_count: number;
    acf: { lag: number; value: number }[];
    pacf: { lag: number; value: number }[];
    notes: string[];
  };
  explainability: Record<string, Explanation>;
  artifacts: Record<
    string,
    {
      hyperparameters: Record<string, number>;
      features: string[];
      training_date_range: Bound;
    }
  >;
  training_duration_seconds: number;
  warnings: string[];
  assumptions: string[];
}
export interface SavedRun {
  run_id: string;
  champion_model: string;
  created_at: string;
  configuration: { store_id: string; product_id: string; horizon: number };
  models: string[];
  test_metrics: Metrics;
}
export interface SeriesResult {
  store_id: string;
  product_id: string;
  status: string;
  run_id?: string;
  champion_model?: string;
  frequency?: string;
  horizon?: number;
  test_period?: Bound;
  test_metrics?: Metrics;
  probabilistic_metrics?: { coverage: number };
  median_total?: number;
}
export const advancedNames: Record<string, string> = {
  naive: "Naive",
  seasonal_naive: "Seasonal naive",
  moving_average: "Moving average",
  linear_regression: "Linear regression",
  arima: "ARIMA",
  sarima: "SARIMA",
  ets: "Exponential smoothing",
  lightgbm: "LightGBM",
  xgboost: "XGBoost",
  nbeats: "N-BEATS",
};
