import type { Metric, ModelName } from "./types";

export const number = (value: number | null | undefined, decimals = 0) =>
  value == null
    ? "—"
    : new Intl.NumberFormat("en-US", {
        maximumFractionDigits: decimals,
      }).format(value);
export const date = (value: string) =>
  new Date(`${value}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
export const shortDate = (value: string) =>
  new Date(`${value}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
export const modelNames: Record<ModelName, string> = {
  naive: "Naive",
  seasonal_naive: "Seasonal naive",
  moving_average: "Moving average",
  linear_regression: "Linear regression",
};
export const metricValue = (key: Metric, value: number | null) =>
  value == null
    ? "—"
    : key === "wape" || key === "smape"
      ? `${(value * 100).toFixed(2)}%`
      : number(value, 3);
