export type Page =
  | "welcome"
  | "quality"
  | "dashboard"
  | "forecast"
  | "comparison"
  | "advanced"
  | "inventory";
export interface Dataset {
  external_features: string[];
  frequency: string;
  column_mapping: Record<string, string>;
  dataset_id: string;
  filename: string;
  is_demo: boolean;
  created_at: string;
  row_count: number;
  processed_row_count: number;
  date_min: string;
  date_max: string;
  store_count: number;
  product_count: number;
  category_count: number | null;
  missing_value_summary: Record<string, number>;
  missing_rate: number;
  duplicate_count: number;
  duplicate_observation_count: number;
  invalid_date_count: number;
  negative_sales_count: number;
  invalid_price_count: number;
  missing_date_count: number;
  chronologically_ordered: boolean;
  validation_status: "PASS" | "PASS_WITH_WARNINGS" | "FAIL";
  warnings: string[];
  errors: string[];
  timings: Record<string, number>;
}
export interface Options {
  frequency: string;
  stores: string[];
  products: string[];
  categories: string[];
  store_products: Record<string, string[]>;
  date_min: string;
  date_max: string;
}
export interface Group {
  name: string;
  units: number;
}
export interface Analytics {
  demand_statistics: {
    mean: number | null;
    median: number | null;
    standard_deviation: number | null;
    cv: number | null;
    minimum: number | null;
    maximum: number | null;
    trend: string | null;
    trend_slope_per_period: number | null;
    outlier_count: number;
    outliers: { date: string; value: number }[];
    seasonality_detected: boolean | null;
    missing_periods: number;
    notes: string[];
  };
  frequency: string;
  total_units: number | null;
  total_revenue: number | null;
  revenue_is_partial: boolean;
  average_daily_units: number | null;
  product_count: number;
  store_count: number;
  observation_count: number;
  missing_sales_count: number;
  date_min: string;
  date_max: string;
  sales_over_time: { date: string; units: number | null }[];
  sales_by_store: Group[];
  sales_by_category: Group[];
  top_products: Group[];
  weekday_pattern: Group[];
  monthly_seasonality: Group[];
}
export type Metric = "mae" | "rmse" | "wape" | "smape" | "mase";
export type Metrics = Record<Metric, number | null>;
export type ModelName =
  "naive" | "seasonal_naive" | "moving_average" | "linear_regression";
export interface Forecast {
  missing_policy: "flag" | "zero";
  run_id: string;
  dataset_id: string;
  store_id: string;
  product_id: string;
  horizon: number;
  model: ModelName;
  forecast: { date: string; predicted_units: number }[];
  history: { date: string; actual: number }[];
  metrics: Metrics;
  validation_metrics: Metrics;
  test_metrics: Metrics;
  comparison: {
    model: ModelName;
    validation_metrics: Metrics;
    test_metrics: Metrics;
  }[];
  split: Record<string, { start: string; end: string; days: number }>;
  summary: Record<string, number | null>;
  timings: Record<string, number>;
  warnings: string[];
  assumptions: string[];
  selection_reason: string;
}
