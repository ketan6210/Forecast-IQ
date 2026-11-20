import { useEffect, useState } from "react";
import { ArrowRight, CalendarDays, SlidersHorizontal } from "lucide-react";
import { api } from "../api";
import {
  Bars,
  ErrorState,
  Loading,
  PageHeader,
  Panel,
  SalesChart,
  Stat,
} from "../components";
import { date, number } from "../format";
import { chartTheme } from "../theme";
import type { Analytics, Dataset, Options } from "../types";

export default function Dashboard({
  dataset,
  options,
  onForecast,
}: {
  dataset: Dataset;
  options: Options;
  onForecast: () => void;
}) {
  const [filters, setFilters] = useState({
    store: "",
    product: "",
    category: "",
    date_from: "",
    date_to: "",
  });
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    const query = new URLSearchParams(
      Object.entries(filters).filter(([, value]) => value),
    );
    setLoading(true);
    setError("");
    api<Analytics>(`/analytics/${dataset.dataset_id}?${query}`, {
      signal: controller.signal,
    })
      .then(setData)
      .catch((err: Error) => {
        if (err.name !== "AbortError") {
          setError(err.message);
          setData(null);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [dataset.dataset_id, filters]);
  const update = (key: string, value: string) =>
    setFilters((prev) => ({
      ...prev,
      [key]: value,
      ...(key === "store" ? { product: "" } : {}),
    }));
  return (
    <>
      <PageHeader
        eyebrow="The big picture"
        title="Demand overview"
        description="Explore sales performance, demand shape, and seasonal patterns across your selected data."
        action={
          <button className="button primary" onClick={onForecast}>
            Create a forecast <ArrowRight size={17} />
          </button>
        }
      />
      <div className="filter-bar">
        <SlidersHorizontal size={18} />
        <label>
          <span>Store</span>
          <select
            aria-label="Store"
            value={filters.store}
            onChange={(e) => update("store", e.target.value)}
          >
            <option value="">All stores</option>
            {options.stores.map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Product</span>
          <select
            aria-label="Product"
            value={filters.product}
            onChange={(e) => update("product", e.target.value)}
          >
            <option value="">All products</option>
            {(filters.store
              ? options.store_products[filters.store]
              : options.products
            ).map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Category</span>
          <select
            aria-label="Category"
            value={filters.category}
            onChange={(e) => update("category", e.target.value)}
            disabled={!options.categories.length}
          >
            <option value="">All categories</option>
            {options.categories.map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
        <label>
          <span>From</span>
          <input
            type="date"
            value={filters.date_from}
            min={options.date_min}
            max={options.date_max}
            onChange={(e) => update("date_from", e.target.value)}
          />
        </label>
        <label>
          <span>To</span>
          <input
            type="date"
            value={filters.date_to}
            min={options.date_min}
            max={options.date_max}
            onChange={(e) => update("date_to", e.target.value)}
          />
        </label>
        <button
          className="text-button"
          onClick={() =>
            setFilters({
              store: "",
              product: "",
              category: "",
              date_from: "",
              date_to: "",
            })
          }
        >
          Reset
        </button>
      </div>
      {loading ? (
        <Loading />
      ) : error ? (
        <ErrorState message={error} />
      ) : (
        data && (
          <>
            <div className="period-caption">
              <CalendarDays size={14} />
              {date(data.date_min)} — {date(data.date_max)}
              <span>{number(data.observation_count)} observations</span>
            </div>
            <div className="stats-grid">
              <Stat
                label="Total units sold"
                value={number(data.total_units)}
                note="Across the selected period"
                accent
              />
              <Stat
                label="Sales revenue"
                value={number(data.total_revenue, 2)}
                note={
                  data.revenue_is_partial
                    ? "Partial · missing price or sales values"
                    : "In the currency of your price column"
                }
              />
              <Stat
                label={
                  data.frequency === "D"
                    ? "Average daily units"
                    : "Average period units"
                }
                value={number(data.average_daily_units, 1)}
                note="Per observed period"
              />
              <Stat
                label="Products / stores"
                value={`${number(data.product_count)} / ${number(data.store_count)}`}
                note="In your current selection"
              />
            </div>
            {data.missing_sales_count > 0 && (
              <div className="alert warning">
                {number(data.missing_sales_count)} sales values are missing.
                Aggregates include observed values only.
              </div>
            )}
            <Panel
              title="Sales over time"
              subtitle={`Demand across your selection · ${data.frequency} frequency`}
              action={
                <span className="legend-label">
                  <i /> Actual units sold
                </span>
              }
            >
              <SalesChart data={data.sales_over_time} />
            </Panel>
            <Panel
              title="Demand statistics"
              subtitle="Observed period totals across the selected series"
            >
              <div className="stats-grid">
                <Stat
                  label="Median demand"
                  value={number(data.demand_statistics.median, 1)}
                />
                <Stat
                  label="Demand volatility"
                  value={number(data.demand_statistics.standard_deviation, 2)}
                  note="Sample standard deviation"
                />
                <Stat
                  label="Demand CV"
                  value={number(data.demand_statistics.cv, 3)}
                  note="Standard deviation / mean"
                />
                <Stat
                  label="Outlier periods"
                  value={number(data.demand_statistics.outlier_count)}
                  note="Scaled MAD heuristic"
                />
              </div>
              <p>
                Trend: {data.demand_statistics.trend ?? "Unavailable"}; slope{" "}
                {number(data.demand_statistics.trend_slope_per_period, 3)} units
                / period. Seasonality:{" "}
                {data.demand_statistics.seasonality_detected == null
                  ? "Unavailable with gaps"
                  : data.demand_statistics.seasonality_detected
                    ? "Pattern detected"
                    : "No supported pattern"}
                . Missing total-demand periods:{" "}
                {data.demand_statistics.missing_periods}.
              </p>
              <details className="methodology">
                <summary>Statistics and outlier details</summary>
                {data.demand_statistics.notes.map((note) => (
                  <p key={note}>{note}</p>
                ))}
                {data.demand_statistics.outliers.length > 0 && (
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Period</th>
                          <th>Observed units</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.demand_statistics.outliers.map((row) => (
                          <tr key={row.date}>
                            <td>{date(row.date)}</td>
                            <td>{number(row.value)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </details>
            </Panel>
            <div className="two-columns">
              <Panel
                title="Sales by store"
                subtitle="Total units by retail location"
              >
                <Bars data={data.sales_by_store} />
              </Panel>
              <Panel
                title="Sales by category"
                subtitle="The categories driving demand"
              >
                <Bars data={data.sales_by_category} color={chartTheme.indigo} />
              </Panel>
            </div>
            <div className="two-columns">
              <Panel
                title="Weekday sales pattern"
                subtitle="Average observed demand by timestamp weekday"
              >
                <Bars data={data.weekday_pattern} />
              </Panel>
              <Panel
                title="Monthly seasonality"
                subtitle="Average observed demand by calendar month"
              >
                <Bars
                  data={data.monthly_seasonality}
                  color={chartTheme.accent}
                />
              </Panel>
            </div>
            <Panel
              title="Top 10 products"
              subtitle="Ranked by total units sold in your selection"
            >
              <div className="ranking">
                {data.top_products.map((product, i) => (
                  <div className="rank-row" key={product.name}>
                    <span className="rank-number">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <strong>{product.name}</strong>
                    <div className="rank-track">
                      <span
                        style={{
                          width: `${data.top_products[0].units > 0 ? (product.units / data.top_products[0].units) * 100 : 0}%`,
                        }}
                      />
                    </div>
                    <span>
                      {number(product.units)} <small>units</small>
                    </span>
                  </div>
                ))}
              </div>
            </Panel>
          </>
        )
      )}
    </>
  );
}
