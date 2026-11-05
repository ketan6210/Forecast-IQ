import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  CalendarDays,
  ChartNoAxesCombined,
  Info,
  Play,
  Sparkles,
} from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api";
import { Loading, Panel, Stat } from "../components";
import { date, metricValue, modelNames, number, shortDate } from "../format";
import type { Dataset, Forecast, Metric, Options } from "../types";

export default function ForecastPage({
  dataset,
  options,
  result,
  setResult,
  onCompare,
}: {
  dataset: Dataset;
  options: Options;
  result: Forecast | null;
  setResult: (result: Forecast | null) => void;
  onCompare: () => void;
}) {
  const [store, setStore] = useState(result?.store_id ?? options.stores[0]);
  const [product, setProduct] = useState(
    result?.product_id ?? options.store_products[options.stores[0]][0],
  );
  const [horizon, setHorizon] = useState(result?.horizon ?? 28);
  const [missingPolicy, setMissingPolicy] = useState(
    result?.missing_policy ?? "flag",
  );
  const generation = useRef<AbortController | null>(null);
  useEffect(() => () => generation.current?.abort(), []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const hasMissing =
    dataset.missing_date_count > 0 ||
    dataset.missing_value_summary.units_sold > 0;
  async function generate() {
    const controller = new AbortController();
    generation.current = controller;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const nextResult = await api<Forecast>("/forecast", {
        signal: controller.signal,
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          dataset_id: dataset.dataset_id,
          store_id: store,
          product_id: product,
          horizon,
          missing_policy: missingPolicy,
        }),
      });
      if (!controller.signal.aborted) setResult(nextResult);
    } catch (err) {
      if (!controller.signal.aborted)
        setError(err instanceof Error ? err.message : "Forecast failed.");
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  const history = result?.history.slice(-90) ?? [];
  const last = history[history.length - 1];
  const chart = result
    ? [
        ...history.map((p) => ({
          date: p.date,
          actual: p.actual,
          predicted: p === last ? p.actual : null,
        })),
        ...result.forecast.map((p) => ({
          date: p.date,
          actual: null,
          predicted: p.predicted_units,
        })),
      ]
    : [];
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">FROM HISTORY TO WHAT’S NEXT</span>
          <h1>Demand forecast</h1>
          <p>A grounded outlook for one product, at one store.</p>
        </div>
        <span className="outline-badge">
          <ChartNoAxesCombined size={15} /> 4 baseline models
        </span>
      </div>
      <div className="forecast-controls">
        <label>
          <span>Store</span>
          <select
            aria-label="Store"
            disabled={busy}
            value={store}
            onChange={(e) => {
              setStore(e.target.value);
              setProduct(options.store_products[e.target.value][0]);
              setResult(null);
            }}
          >
            {options.stores.map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Product</span>
          <select
            aria-label="Product"
            disabled={busy}
            value={product}
            onChange={(e) => {
              setProduct(e.target.value);
              setResult(null);
            }}
          >
            {options.store_products[store].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
        <fieldset disabled={busy}>
          <legend>Forecast horizon</legend>
          <div className="segmented">
            {[7, 14, 28].map((days) => (
              <button
                key={days}
                aria-pressed={horizon === days}
                className={horizon === days ? "selected" : ""}
                onClick={() => {
                  setHorizon(days);
                  setResult(null);
                }}
              >
                {days} days
              </button>
            ))}
          </div>
        </fieldset>
        <button
          className="button primary generate"
          disabled={busy}
          onClick={() => void generate()}
        >
          <Play size={15} />
          {busy ? "Training baselines…" : "Generate forecast"}
        </button>
      </div>
      {hasMissing && (
        <div className="missing-policy">
          <label>
            <input
              type="checkbox"
              disabled={busy}
              checked={missingPolicy === "zero"}
              onChange={(e) => {
                setMissingPolicy(e.target.checked ? "zero" : "flag");
                setResult(null);
              }}
            />
            I confirm that missing observations for this series mean zero sales.
          </label>
          <small>
            Leave unchecked to keep gaps flagged. Forecasting requires complete
            daily sales.
          </small>
        </div>
      )}
      {error && (
        <div className="alert error" role="alert">
          {error}
        </div>
      )}
      {busy ? (
        <Loading text="Training four baselines, comparing validation results, and evaluating on the test period…" />
      ) : !result ? (
        <div className="forecast-empty">
          <div className="empty-chart-icon">
            <ChartNoAxesCombined size={38} />
          </div>
          <h2>Your next forecast starts here</h2>
          <p>
            Choose a store, a product, and a horizon.
            <br />
            We’ll compare four baselines using chronological validation.
          </p>
          <span>
            <Info size={14} /> At least 90 days of daily history required
          </span>
        </div>
      ) : (
        <>
          <div className="forecast-context">
            <span>
              <strong>{result.product_id}</strong>
              <span className="context-divider">/</span>
              {result.store_id}
            </span>
            <span>
              <CalendarDays size={14} />
              History: {date(result.history[0].date)} — {date(last.date)}
            </span>
          </div>
          {result.warnings.map((w) => (
            <div className="alert warning" key={w}>
              {w}
            </div>
          ))}
          <div className="forecast-hero">
            <div>
              <span className="eyebrow">
                {result.horizon}-DAY DEMAND FORECAST
              </span>
              <div className="forecast-total">
                {number(result.summary.forecast_total)} <span>units</span>
              </div>
              <p>
                {date(result.forecast[0].date)} —{" "}
                {date(result.forecast[result.forecast.length - 1].date)}
              </p>
            </div>
            <div className="hero-divider" />
            <div className="forecast-hero-side">
              <span>SELECTED BASELINE</span>
              <strong>
                <Sparkles size={18} />
                {modelNames[result.model]}
              </strong>
              <p>
                {result.selection_reason.startsWith(
                  "Validation WAPE is undefined",
                )
                  ? "Validation WAPE undefined · fallback model"
                  : "Selected on validation WAPE"}
              </p>
              <button onClick={onCompare}>
                View model comparison <ArrowRight size={15} />
              </button>
            </div>
          </div>
          <Panel
            title="Historical sales & forecast"
            subtitle="The last 90 days of history, followed by your selected forecast horizon"
            action={
              <div className="chart-legend">
                <span>
                  <i />
                  Actual sales
                </span>
                <span>
                  <i className="dashed" />
                  Forecast
                </span>
              </div>
            }
          >
            <div
              className="chart forecast-chart"
              role="img"
              aria-label="Historical actual units and future forecast units"
            >
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={chart}
                  margin={{ top: 24, right: 22, bottom: 15, left: 12 }}
                >
                  <CartesianGrid
                    strokeDasharray="3 5"
                    vertical={false}
                    stroke="#e8edeb"
                  />
                  <XAxis
                    dataKey="date"
                    tickFormatter={shortDate}
                    minTickGap={48}
                    tickLine={false}
                    axisLine={false}
                    tick={{ fill: "#768583", fontSize: 11 }}
                    label={{
                      value: "Date",
                      position: "insideBottom",
                      offset: -10,
                      fill: "#87918f",
                      fontSize: 11,
                    }}
                  />
                  <YAxis
                    tickLine={false}
                    axisLine={false}
                    width={46}
                    tick={{ fill: "#768583", fontSize: 11 }}
                    label={{
                      value: "Units",
                      angle: -90,
                      position: "insideLeft",
                      fill: "#87918f",
                      fontSize: 11,
                    }}
                  />
                  <Tooltip
                    labelFormatter={(v) => date(String(v))}
                    formatter={(value, key) => [
                      number(Number(value), 1),
                      key === "actual" ? "Actual" : "Predicted",
                    ]}
                    contentStyle={{
                      borderRadius: 10,
                      border: "1px solid #e2e8e5",
                    }}
                  />
                  <ReferenceArea
                    x1={last.date}
                    x2={result.forecast[result.forecast.length - 1].date}
                    fill="#e7f3ef"
                    fillOpacity={0.6}
                    label={{
                      value: "FORECAST",
                      position: "insideTop",
                      fill: "#458878",
                      fontSize: 10,
                    }}
                  />
                  <Line
                    dataKey="actual"
                    type="monotone"
                    stroke="#2a716b"
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                  />
                  <Line
                    dataKey="predicted"
                    type="monotone"
                    stroke="#d69446"
                    strokeWidth={2.5}
                    strokeDasharray="6 5"
                    dot={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Panel>
          <div className="section-title">
            <h2>The numbers behind the outlook</h2>
            <span>Units per day</span>
          </div>
          <div className="stats-grid">
            <Stat
              label="Historical daily average"
              value={number(result.summary.historical_daily_average, 1)}
              note="Across all observed history"
            />
            <Stat
              label="Last 7-day average"
              value={number(result.summary.last_7_day_average, 1)}
              note="Most recent week"
            />
            <Stat
              label="Last 28-day average"
              value={number(result.summary.last_28_day_average, 1)}
              note="Most recent four weeks"
            />
            <Stat
              label="Forecast daily average"
              value={number(result.summary.forecast_daily_average, 1)}
              note={`Over the next ${result.horizon} days`}
              accent
            />
          </div>
          <Panel
            title="How this model performed"
            subtitle={`Final test period · ${date(result.split.test.start)} – ${date(result.split.test.end)} · lower is better`}
            action={
              <button className="text-button" onClick={onCompare}>
                View model comparison <ArrowRight size={14} />
              </button>
            }
          >
            <div className="metric-grid">
              {(["wape", "mase", "mae", "rmse", "smape"] as Metric[]).map(
                (key) => (
                  <div key={key}>
                    <span>{key === "smape" ? "sMAPE" : key.toUpperCase()}</span>
                    <strong>
                      {metricValue(key, result.test_metrics[key])}
                    </strong>
                    <small>
                      {key === "mase"
                        ? "Weekly naive scale"
                        : key === "wape"
                          ? "Weighted absolute error"
                          : key === "smape"
                            ? "Symmetric percentage error"
                            : "Units"}
                    </small>
                  </div>
                ),
              )}
            </div>
            <p className="panel-footnote">
              Measured on the test period after model selection. These are
              historical evaluation errors, not estimates of future certainty. —
              means mathematically undefined.
            </p>
          </Panel>
          {result.summary.current_inventory !== null && (
            <Panel
              title="Inventory gap"
              subtitle="A simple comparison with forecast demand"
            >
              <div className="inventory-grid">
                <div>
                  <span>Current inventory</span>
                  <strong>
                    {number(result.summary.current_inventory)}{" "}
                    <small>units</small>
                  </strong>
                </div>
                <span className="math-symbol">−</span>
                <div>
                  <span>{result.horizon}-day forecast demand</span>
                  <strong>
                    {number(result.summary.forecast_total)} <small>units</small>
                  </strong>
                </div>
                <span className="math-symbol">=</span>
                <div>
                  <span>Inventory gap</span>
                  <strong
                    className={
                      (result.summary.inventory_gap ?? 0) < 0 ? "negative" : ""
                    }
                  >
                    {number(result.summary.inventory_gap)} <small>units</small>
                  </strong>
                </div>
              </div>
              <p className="panel-footnote">
                Inventory gap = latest inventory − forecast demand. This is not
                a reorder recommendation; lead times, safety stock, and incoming
                orders are not modeled.
              </p>
            </Panel>
          )}
          <details className="methodology">
            <summary>Forecast assumptions &amp; run details</summary>
            <ul>
              {result.assumptions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
            <p>{result.selection_reason}</p>
            <p>
              Features:{" "}
              {number(result.timings.feature_generation_seconds * 1000, 1)} ms ·
              Training and evaluation:{" "}
              {number(result.timings.training_seconds, 3)} s · Forecast:{" "}
              {number(result.timings.forecast_generation_seconds * 1000, 2)} ms
            </p>
            <small>Run {result.run_id}</small>
          </details>
        </>
      )}
    </>
  );
}
