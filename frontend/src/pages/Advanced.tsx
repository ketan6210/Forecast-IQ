import { useEffect, useRef, useState } from "react";
import { Download, Play, Sparkles, Waves } from "lucide-react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, forecastRuns } from "../api";
import { Loading, Panel, Stat } from "../components";
import { date, metricValue, number, shortDate } from "../format";
import type { Dataset, Metric, Options } from "../types";
import type { AdvancedRun, SavedRun, SeriesResult } from "../advancedTypes";
import { advancedNames as names } from "../advancedTypes";

export default function Advanced({
  dataset,
  options,
}: {
  dataset: Dataset;
  options: Options;
}) {
  const [store, setStore] = useState(options.stores[0]);
  const [product, setProduct] = useState(
    options.store_products[options.stores[0]][0],
  );
  const [horizon, setHorizon] = useState(28);
  const [folds, setFolds] = useState(3);
  const [frequency, setFrequency] = useState("auto");
  const [window, setWindow] = useState("expanding");
  const [windowSize, setWindowSize] = useState(180);
  const [zero, setZero] = useState(false);
  const [tune, setTune] = useState(true);
  const [tuningTrials, setTuningTrials] = useState(4);
  const [tuningSeed, setTuningSeed] = useState(42);
  const [neural, setNeural] = useState(true);
  const [run, setRun] = useState<AdvancedRun | null>(null);
  const [saved, setSaved] = useState<SavedRun[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [backtestModel, setBacktestModel] = useState("");
  const [fold, setFold] = useState(0);
  const [statistic, setStatistic] = useState<"mean" | "median" | "std">("mean");
  const [tree, setTree] = useState("lightgbm");
  const [driverDate, setDriverDate] = useState(0);
  const [feature, setFeature] = useState("sales_lag_7");
  const [otherSeries, setOtherSeries] = useState("");
  const [seriesComparison, setSeriesComparison] = useState<SeriesResult[]>([]);
  const controller = useRef<AbortController | null>(null);
  const comparisonController = useRef<AbortController | null>(null);
  const key = `forecastiq.advanced.${dataset.dataset_id}`;

  function clearComparison() {
    comparisonController.current?.abort();
    setSeriesComparison([]);
  }

  function accept(result: AdvancedRun) {
    setRun(result);
    setStore(result.store_id);
    setProduct(result.product_id);
    setHorizon(result.forecast_horizon);
    setFolds(result.configuration.folds);
    setFrequency(result.configuration.frequency);
    setWindow(result.configuration.window);
    setWindowSize(result.configuration.window_size);
    setZero(result.configuration.missing_policy === "zero");
    setTune(result.configuration.tune);
    setTuningTrials(result.configuration.tuning_trials ?? 4);
    setTuningSeed(result.configuration.tuning_seed ?? 42);
    setNeural(result.configuration.models.includes("nbeats"));
    setBacktestModel(result.champion_model);
    setFold(0);
    setDriverDate(0);
    setTree(Object.keys(result.explainability)[0] || "lightgbm");
    clearComparison();
    setOtherSeries("");
    localStorage.setItem(key, result.run_id);
  }
  useEffect(() => {
    const listAbort = new AbortController();
    const abort = new AbortController();
    controller.current = abort;
    forecastRuns<SavedRun>(dataset.dataset_id, listAbort.signal)
      .then(async (rows) => {
        if (listAbort.signal.aborted || controller.current !== abort) return;
        setSaved(rows);
        if (abort.signal.aborted) return;
        const id = localStorage.getItem(key);
        if (id) {
          const result = await api<AdvancedRun>(`/forecast/runs/${id}`, {
            signal: abort.signal,
          });
          if (!abort.signal.aborted) accept(result);
        }
      })
      .catch((err: Error) => {
        if (!abort.signal.aborted) setError(err.message);
      });
    return () => {
      listAbort.abort();
      abort.abort();
      controller.current?.abort();
      comparisonController.current?.abort();
    };
    // This page is keyed by dataset; restoration runs once for that dataset.
  }, [dataset.dataset_id]);

  async function train() {
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    clearComparison();
    setBusy(true);
    setError("");
    setRun(null);
    try {
      const result = await api<AdvancedRun>("/forecast/train", {
        method: "POST",
        signal: abort.signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          dataset_id: dataset.dataset_id,
          store_id: store,
          product_id: product,
          horizon,
          folds,
          frequency,
          window,
          window_size: windowSize,
          missing_policy: zero ? "zero" : "flag",
          tune,
          tuning_trials: tuningTrials,
          tuning_seed: tuningSeed,
          models: Object.keys(names).filter(
            (name) => neural || name !== "nbeats",
          ),
        }),
      });
      if (abort.signal.aborted) return;
      accept(result);
      setSaved(await forecastRuns<SavedRun>(dataset.dataset_id, abort.signal));
    } catch (err) {
      if (!abort.signal.aborted)
        setError(err instanceof Error ? err.message : "Training failed.");
    } finally {
      if (!abort.signal.aborted) setBusy(false);
    }
  }
  async function restore(id: string) {
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    clearComparison();
    setError("");
    setBusy(true);
    try {
      const result = await api<AdvancedRun>(`/forecast/runs/${id}`, {
        signal: abort.signal,
      });
      if (!abort.signal.aborted) accept(result);
    } catch (err) {
      if (!abort.signal.aborted)
        setError(
          err instanceof Error ? err.message : "Could not open this run.",
        );
    } finally {
      if (!abort.signal.aborted) setBusy(false);
    }
  }
  async function compareSeries() {
    if (!run || !otherSeries) return;
    clearComparison();
    const abort = new AbortController();
    comparisonController.current = abort;
    setError("");
    const [otherStore, otherProduct] = JSON.parse(otherSeries) as string[];
    try {
      const response = await api<{ series: SeriesResult[] }>(
        "/forecast/series-comparison",
        {
          method: "POST",
          signal: abort.signal,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            dataset_id: dataset.dataset_id,
            series: [
              { store_id: run.store_id, product_id: run.product_id },
              { store_id: otherStore, product_id: otherProduct },
            ],
          }),
        },
      );
      if (!abort.signal.aborted) setSeriesComparison(response.series);
    } catch (err) {
      if (!abort.signal.aborted)
        setError(err instanceof Error ? err.message : "Comparison failed.");
    }
  }
  const selected = run?.comparison.find((row) => row.model === backtestModel);
  const selectedFold = selected?.folds?.[fold];
  const explanation = run?.explainability[tree];
  const driver = explanation?.forecast_drivers[driverDate];
  const chart = run
    ? [
        ...run.history
          .slice(-90)
          .map((p) => ({ date: p.date, actual: p.actual })),
        ...run.forecast.map((p) => ({ ...p, interval: [p.p10, p.p90] })),
      ]
    : [];
  const autocorrelations =
    run?.diagnostics.acf.map((point) => ({
      lag: point.lag,
      acf: point.value,
      pacf: run.diagnostics.pacf.find((p) => p.lag === point.lag)?.value,
    })) ?? [];
  const clear = () => {
    controller.current?.abort();
    setBusy(false);
    setError("");
    setRun(null);
    clearComparison();
  };

  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">ADVANCED FORECASTING · PHASE 2</span>
          <h1>Forecast quality lab</h1>
          <p>
            Compare models over time. See the uncertainty. Understand the
            drivers.
          </p>
        </div>
        <span className="outline-badge">
          <Waves size={16} /> P10 · P50 · P90
        </span>
      </div>
      {saved.length > 0 && (
        <label className="saved-runs">
          <span>Open a saved training run</span>
          <select
            aria-label="Saved training run"
            value={run?.run_id || ""}
            disabled={busy}
            onChange={(e) => {
              if (e.target.value) void restore(e.target.value);
            }}
          >
            <option value="">Choose a run…</option>
            {saved.map((item) => (
              <option value={item.run_id} key={item.run_id}>
                {item.configuration.store_id} / {item.configuration.product_id}{" "}
                · {names[item.champion_model]} ·{" "}
                {new Date(item.created_at).toLocaleString()}
              </option>
            ))}
          </select>
        </label>
      )}
      <fieldset className="advanced-form" disabled={busy}>
        <div className="advanced-controls">
          <label>
            <span>Store</span>
            <select
              aria-label="Advanced store"
              value={store}
              onChange={(e) => {
                setStore(e.target.value);
                setProduct(options.store_products[e.target.value][0]);
                clear();
              }}
            >
              {options.stores.map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Product / SKU</span>
            <select
              aria-label="Advanced product"
              value={product}
              onChange={(e) => {
                setProduct(e.target.value);
                clear();
              }}
            >
              {options.store_products[store].map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Forecast horizon (periods)</span>
            <input
              aria-label="Forecast horizon (periods)"
              type="number"
              min={1}
              max={90}
              value={horizon}
              onChange={(e) => {
                setHorizon(Number(e.target.value));
                clear();
              }}
            />
          </label>
          <label>
            <span>Frequency</span>
            <select
              aria-label="Forecast frequency"
              value={frequency}
              onChange={(e) => {
                setFrequency(e.target.value);
                clear();
              }}
            >
              <option value="auto">Detect from dates</option>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
          </label>
          <button
            className="button primary"
            disabled={busy || horizon < 1 || horizon > 90}
            onClick={() => void train()}
          >
            <Play size={14} />
            {busy ? "Evaluating models…" : "Train & forecast"}
          </button>
        </div>
        <details className="training-options">
          <summary>Evaluation options</summary>
          <p>
            Selected numeric predictors:{" "}
            {dataset.external_features?.join(", ") || "None"}. Regression and
            tree models use these inputs; future values stay at the last
            observed value. Randomized tree settings use the same chronological
            folds.
          </p>
          <div className="advanced-controls">
            <label>
              <span>Tree search trials</span>
              <input
                aria-label="Tree search trials"
                type="number"
                min={1}
                max={10}
                value={tuningTrials}
                disabled={!tune}
                onChange={(e) => {
                  setTuningTrials(Number(e.target.value));
                  clear();
                }}
              />
            </label>
            <label>
              <span>Tree search seed</span>
              <input
                aria-label="Tree search seed"
                type="number"
                min={0}
                max={4294967295}
                value={tuningSeed}
                disabled={!tune}
                onChange={(e) => {
                  setTuningSeed(Number(e.target.value));
                  clear();
                }}
              />
            </label>
            <label>
              <span>Backtest folds</span>
              <input
                aria-label="Backtest folds"
                type="number"
                min={2}
                max={5}
                value={folds}
                onChange={(e) => {
                  setFolds(Number(e.target.value));
                  clear();
                }}
              />
            </label>
            <label>
              <span>Training window</span>
              <select
                aria-label="Training window"
                value={window}
                onChange={(e) => {
                  setWindow(e.target.value);
                  clear();
                }}
              >
                <option value="expanding">Expanding history</option>
                <option value="rolling">Rolling window</option>
              </select>
            </label>
            {window === "rolling" && (
              <label>
                <span>Window length (periods)</span>
                <input
                  type="number"
                  min={60}
                  max={5000}
                  value={windowSize}
                  onChange={(e) => {
                    setWindowSize(Number(e.target.value));
                    clear();
                  }}
                />
              </label>
            )}
          </div>
          <div className="option-checks">
            <label>
              <input
                type="checkbox"
                checked={tune}
                onChange={(e) => {
                  setTune(e.target.checked);
                  clear();
                }}
              />
              Randomized search on chronological folds
            </label>
            <label>
              <input
                type="checkbox"
                checked={neural}
                onChange={(e) => {
                  setNeural(e.target.checked);
                  clear();
                }}
              />
              Include N-BEATS when enough history is available
            </label>
          </div>
          <p>
            At least {60 + (folds + 1) * horizon + Math.max(20, 2 * horizon)}{" "}
            periods are needed for this evaluation. Calibration and the final
            test period remain separate from model selection.
          </p>
        </details>
        {(dataset.missing_date_count > 0 ||
          dataset.missing_value_summary.units_sold > 0) && (
          <label className="zero-consent">
            <input
              type="checkbox"
              checked={zero}
              onChange={(e) => {
                setZero(e.target.checked);
                clear();
              }}
            />
            I confirm missing observations mean zero sales for this series.
          </label>
        )}
      </fieldset>
      {error && (
        <div role="alert" className="alert error">
          {error}
        </div>
      )}
      {busy && (
        <Loading text="Running chronological backtests, calibrating uncertainty, and saving fitted models. Other dashboard pages remain available." />
      )}
      {!busy && !run && (
        <div className="forecast-empty">
          <Sparkles size={36} />
          <h2>A stronger forecast starts with a fair comparison</h2>
          <p>
            Baselines, statistical models, tree models, and an eligible neural
            candidate.
            <br />
            Every score is calculated from held-out observations.
          </p>
        </div>
      )}
      {!busy && run && (
        <>
          <div className="forecast-hero">
            <div>
              <span className="eyebrow">
                CHAMPION MODEL · {run.store_id} / {run.product_id}
              </span>
              <h2 className="champion-name">{names[run.champion_model]}</h2>
              <p>
                {run.forecast_horizon} future periods · {run.frequency}{" "}
                frequency · {number(run.training_duration_seconds, 2)} s
                training
              </p>
            </div>
            <div className="hero-divider" />
            <div className="forecast-hero-side">
              <span>SUM OF PERIOD MEDIANS</span>
              <strong>
                {number(
                  run.forecast.reduce((sum, p) => sum + p.p50, 0),
                  1,
                )}{" "}
                units
              </strong>
              <p>This sum is not a calibrated quantile of total demand.</p>
            </div>
          </div>
          <Panel
            title="Demand, with uncertainty"
            subtitle="Observed history, P50 forecast, and a marginal P10–P90 interval"
            action={
              <a
                className="button secondary"
                href={`/api/forecast/export/${run.run_id}`}
                download
              >
                <Download size={14} />
                Export forecast CSV
              </a>
            }
          >
            <div className="chart-legend advanced-legend">
              <span>
                <i />
                Actual demand
              </span>
              <span>
                <i className="dashed" />
                P50 forecast
              </span>
              <span>
                <i className="interval-swatch" />
                P10–P90
              </span>
            </div>
            <div
              className="chart forecast-chart"
              role="img"
              aria-label="P50 forecast and P10 to P90 uncertainty band"
            >
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart
                  data={chart}
                  margin={{ top: 15, right: 22, bottom: 10, left: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 5" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tickFormatter={shortDate}
                    minTickGap={55}
                  />
                  <YAxis width={55} />
                  <Tooltip
                    labelFormatter={(v) => date(String(v))}
                    formatter={(v, label) => [
                      Array.isArray(v)
                        ? v.map((value) => number(Number(value), 1)).join(" – ")
                        : number(Number(v), 1),
                      label,
                    ]}
                  />
                  <Area
                    dataKey="interval"
                    name="P10–P90"
                    stroke="none"
                    fill="#90b7a1"
                    fillOpacity={0.3}
                    isAnimationActive={false}
                  />
                  <Line
                    dataKey="actual"
                    name="Actual"
                    stroke="#28766d"
                    dot={false}
                    strokeWidth={2}
                    isAnimationActive={false}
                  />
                  <Line
                    dataKey="p50"
                    name="P50"
                    stroke="#c58b41"
                    strokeDasharray="6 4"
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <p className="panel-footnote">
              {run.calibration.method}. {run.calibration.residual_count}{" "}
              held-out residuals. Nominal coverage is 80%; actual coverage is
              measured below and is not guaranteed.
            </p>
          </Panel>
          <div className="section-title">
            <h2>Final test · accuracy and calibration</h2>
            <span>
              {date(run.partitions.test.start)} –{" "}
              {date(run.partitions.test.end)}
            </span>
          </div>
          <div className="stats-grid">
            <Stat
              label="P50 test WAPE"
              value={metricValue("wape", run.test_metrics.wape)}
              note="Accuracy after calibration"
            />
            <Stat
              label="P10–P90 coverage"
              value={`${number(run.probabilistic_metrics.coverage * 100, 1)}%`}
              note="Observed coverage · nominal 80%"
              accent
            />
            <Stat
              label="Mean interval width"
              value={number(run.probabilistic_metrics.mean_interval_width, 2)}
              note="Demand units"
            />
            <Stat
              label="P50 test MASE"
              value={metricValue("mase", run.test_metrics.mase)}
              note="Seasonal naive training scale"
            />
          </div>
          <Panel
            title="Probabilistic evaluation"
            subtitle="All values below are measured on the final test period"
          >
            <div className="metric-grid">
              {(["p10", "p50", "p90"] as const).map((level) => (
                <div key={level}>
                  <span>{level.toUpperCase()} PINBALL LOSS</span>
                  <strong>
                    {number(run.probabilistic_metrics[`pinball_${level}`], 3)}
                  </strong>
                </div>
              ))}
              <div>
                <span>MAE / RMSE</span>
                <strong>
                  {number(run.test_metrics.mae, 2)} /{" "}
                  {number(run.test_metrics.rmse, 2)}
                </strong>
              </div>
              <div>
                <span>sMAPE</span>
                <strong>{metricValue("smape", run.test_metrics.smape)}</strong>
              </div>
            </div>
            <p className="panel-footnote">
              Coverage uses inclusive P10/P90 bounds. Pinball loss rewards
              accurate quantiles; smaller intervals are useful only when
              coverage remains adequate.
            </p>
          </Panel>
          <Panel
            title="Rolling model comparison"
            subtitle={run.selection_reason}
            action={
              <select
                aria-label="Comparison statistic"
                value={statistic}
                onChange={(e) =>
                  setStatistic(e.target.value as typeof statistic)
                }
              >
                <option value="mean">Mean across folds</option>
                <option value="median">Median across folds</option>
                <option value="std">Standard deviation</option>
              </select>
            }
          >
            <div className="table-wrap">
              <table className="advanced-comparison">
                <thead>
                  <tr>
                    <th>Rank / model</th>
                    <th>Family</th>
                    {(["wape", "smape", "mase", "rmse", "mae"] as Metric[]).map(
                      (metric) => (
                        <th key={metric}>{metric.toUpperCase()}</th>
                      ),
                    )}
                    <th>Fold consistency</th>
                  </tr>
                </thead>
                <tbody>
                  {[...run.comparison]
                    .sort((a, b) => (a.rank ?? 999) - (b.rank ?? 999))
                    .map((row) => (
                      <tr
                        key={row.model}
                        className={
                          row.model === run.champion_model ? "champion-row" : ""
                        }
                      >
                        <td>
                          <strong>
                            {row.rank ?? "—"} · {names[row.model]}
                          </strong>
                          {row.model === run.champion_model && (
                            <span className="selected-label">Champion</span>
                          )}
                          <small>
                            {row.status === "ok"
                              ? `${row.folds?.length} complete folds`
                              : `${row.status}: ${row.reason}`}
                          </small>
                        </td>
                        <td>{row.family.replaceAll("_", " ")}</td>
                        {(
                          ["wape", "smape", "mase", "rmse", "mae"] as Metric[]
                        ).map((metric) => (
                          <td key={metric}>
                            {metricValue(
                              metric,
                              row.summary?.[metric][statistic] ?? null,
                            )}
                          </td>
                        ))}
                        <td>
                          {row.summary ? (
                            <>
                              WAPE σ {metricValue("wape", row.summary.wape.std)}
                              <small>
                                Best fold {row.summary.wape.best_fold ?? "—"} /
                                worst {row.summary.wape.worst_fold ?? "—"}
                              </small>
                            </>
                          ) : (
                            "—"
                          )}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
            <p className="panel-footnote">
              Only candidates that complete every fold can be ranked. Baselines
              remain candidates. Failed fits and data-size fallbacks are
              reported; they are not replaced with made-up scores.
            </p>
          </Panel>
          <Panel
            title="Walk-forward backtesting"
            subtitle="Each forecast uses only the observations before its origin"
            action={
              <div className="inline-controls">
                <select
                  aria-label="Backtest model"
                  value={backtestModel}
                  onChange={(e) => {
                    setBacktestModel(e.target.value);
                    setFold(0);
                  }}
                >
                  {run.comparison
                    .filter((row) => row.status === "ok")
                    .map((row) => (
                      <option key={row.model} value={row.model}>
                        {names[row.model]}
                      </option>
                    ))}
                </select>
                <select
                  aria-label="Backtest fold"
                  value={fold}
                  onChange={(e) => setFold(Number(e.target.value))}
                >
                  {selected?.folds?.map((row, i) => (
                    <option key={row.fold} value={i}>
                      Fold {row.fold}
                    </option>
                  ))}
                </select>
              </div>
            }
          >
            {selectedFold && (
              <>
                <div className="period-caption in-panel">
                  Train: {date(selectedFold.train.start)} –{" "}
                  {date(selectedFold.train.end)}
                  <span>
                    Validate: {date(selectedFold.validation.start)} –{" "}
                    {date(selectedFold.validation.end)}
                  </span>
                </div>
                <div
                  className="chart"
                  role="img"
                  aria-label="Backtest actual and predicted demand"
                >
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      data={selectedFold.predictions}
                      margin={{ right: 22, top: 10, bottom: 10 }}
                    >
                      <CartesianGrid vertical={false} strokeDasharray="3 5" />
                      <XAxis dataKey="date" tickFormatter={shortDate} />
                      <YAxis width={55} />
                      <Tooltip />
                      <Line
                        dataKey="actual"
                        name="Actual"
                        stroke="#28766d"
                        dot={false}
                        isAnimationActive={false}
                      />
                      <Line
                        dataKey="predicted"
                        name="Predicted"
                        stroke="#c58b41"
                        strokeDasharray="5 4"
                        dot={false}
                        isAnimationActive={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <div className="metric-grid">
                  {(["wape", "smape", "mase", "rmse", "mae"] as Metric[]).map(
                    (metric) => (
                      <div key={metric}>
                        <span>{metric.toUpperCase()}</span>
                        <strong>
                          {metricValue(metric, selectedFold.metrics[metric])}
                        </strong>
                      </div>
                    ),
                  )}
                </div>
                <p className="panel-footnote">
                  Forecast stability: {number(selected?.forecast_stability, 3)}{" "}
                  (mean absolute step change / training mean demand). Parameter
                  search: {selected?.trials.length} settings;{" "}
                  {number(selected?.tuning_duration_seconds, 2)} seconds.
                </p>
              </>
            )}
          </Panel>
          <Panel
            title="What drives the tree forecast?"
            subtitle="SHAP contributions from fitted LightGBM and XGBoost models"
            action={
              Object.keys(run.explainability).length > 0 && (
                <select
                  aria-label="Explainability model"
                  value={tree}
                  onChange={(e) => {
                    setTree(e.target.value);
                    setDriverDate(0);
                  }}
                >
                  {Object.keys(run.explainability).map((name) => (
                    <option key={name} value={name}>
                      {names[name]}
                      {name === run.champion_model
                        ? " · champion"
                        : " · candidate"}
                    </option>
                  ))}
                </select>
              )
            }
          >
            {!explanation ? (
              <p className="panel-footnote">
                No successfully trained tree model is available for explanation
                in this run.
              </p>
            ) : (
              <>
                <p className="explanation-scope">
                  {names[tree]} is{" "}
                  {tree === run.champion_model
                    ? "the champion"
                    : "a candidate, not the champion"}{" "}
                  in this run. Contributions explain its raw point forecast,
                  before residual calibration.
                </p>
                <div className="two-columns padded">
                  <div>
                    <h3>Global feature importance</h3>
                    <p className="subtle">
                      Mean absolute SHAP · {explanation.reference_rows} recent
                      training observations
                    </p>
                    <div className="importance-list">
                      {explanation.global_importance
                        .slice(0, 10)
                        .map((item) => (
                          <div key={item.feature}>
                            <span>{item.feature}</span>
                            <div className="rank-track">
                              <span
                                style={{
                                  width: `${(item.mean_absolute_shap / Math.max(explanation.global_importance[0].mean_absolute_shap, 0.000001)) * 100}%`,
                                }}
                              />
                            </div>
                            <strong>
                              {number(item.mean_absolute_shap, 3)}
                            </strong>
                          </div>
                        ))}
                    </div>
                  </div>
                  <div>
                    <h3>Forecast-driving features</h3>
                    <select
                      aria-label="Explain forecast date"
                      value={driverDate}
                      onChange={(e) => setDriverDate(Number(e.target.value))}
                    >
                      {explanation.forecast_drivers.map((item, i) => (
                        <option key={item.date} value={i}>
                          {date(item.date)}
                        </option>
                      ))}
                    </select>
                    {driver && (
                      <>
                        <p className="subtle">
                          Expected value {number(driver.base_value, 2)} → raw
                          forecast {number(driver.raw_prediction, 2)} units
                        </p>
                        <div className="driver-list">
                          {driver.drivers.slice(0, 7).map((item) => (
                            <div key={item.feature}>
                              <span>
                                {item.feature}
                                <small>Value: {number(item.value, 3)}</small>
                              </span>
                              <strong
                                className={
                                  item.shap_value < 0 ? "negative" : ""
                                }
                              >
                                {item.shap_value > 0 ? "+" : ""}
                                {number(item.shap_value, 3)}
                              </strong>
                            </div>
                          ))}
                        </div>
                      </>
                    )}
                  </div>
                </div>
                <div className="shap-summary">
                  <label>
                    <span>SHAP dependence summary</span>
                    <select
                      aria-label="SHAP summary feature"
                      value={feature}
                      onChange={(e) => setFeature(e.target.value)}
                    >
                      {explanation.global_importance.map((item) => (
                        <option key={item.feature} value={item.feature}>
                          {item.feature}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="chart compact">
                    <ResponsiveContainer width="100%" height="100%">
                      <ScatterChart
                        margin={{ top: 20, right: 25, bottom: 20, left: 15 }}
                      >
                        <CartesianGrid strokeDasharray="3 5" />
                        <XAxis
                          type="number"
                          dataKey="value"
                          name="Feature value"
                        />
                        <YAxis
                          type="number"
                          dataKey="shap_value"
                          name="SHAP contribution"
                        />
                        <Tooltip cursor={{ strokeDasharray: "3 3" }} />
                        <Scatter
                          data={explanation.summary_samples.filter(
                            (item) => item.feature === feature,
                          )}
                          fill="#528d72"
                          isAnimationActive={false}
                        />
                      </ScatterChart>
                    </ResponsiveContainer>
                  </div>
                  <p className="subtle">
                    X: feature value · Y: SHAP contribution in units.
                    Positive/negative effects are relative to the model’s
                    expected value, not causal claims.
                  </p>
                </div>
              </>
            )}
          </Panel>
          <Panel
            title="Time-series diagnostics"
            subtitle="Calculated on the selection history, excluding calibration and final test"
          >
            <div className="stats-grid diagnostic-stats">
              <Stat
                label="Trend"
                value={run.diagnostics.trend}
                note={`${number(run.diagnostics.trend_slope_per_period, 4)} units / period`}
              />
              <Stat
                label="Seasonality evidence"
                value={
                  run.diagnostics.seasonality_detected
                    ? "Detected"
                    : "Weak / unavailable"
                }
                note={`Candidate cycle: ${run.diagnostics.seasonal_period} periods`}
              />
              <Stat
                label="Missing periods"
                value={number(run.diagnostics.missing_periods)}
                note="Explicit zero policy applies if selected"
              />
              <Stat
                label="Potential outliers"
                value={number(run.diagnostics.outlier_count)}
                note="MAD heuristic · observations retained"
              />
            </div>
            {autocorrelations.length > 0 && (
              <div className="chart compact">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={autocorrelations}
                    margin={{ right: 25, bottom: 10 }}
                  >
                    <CartesianGrid vertical={false} strokeDasharray="3 5" />
                    <XAxis dataKey="lag" />
                    <YAxis domain={[-1, 1]} width={50} />
                    <Tooltip />
                    <Line
                      dataKey="acf"
                      name="ACF"
                      stroke="#28766d"
                      dot={false}
                      isAnimationActive={false}
                    />
                    <Line
                      dataKey="pacf"
                      name="PACF"
                      stroke="#c58b41"
                      dot={false}
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
            <p className="panel-footnote">
              ACF and PACF are descriptive lag correlations. Constant or very
              short histories omit them. Trend and seasonality heuristics are
              not significance tests.
            </p>
          </Panel>
          <Panel
            title="Forecast table"
            subtitle={`${run.forecast_horizon} periods · ordered, nonnegative demand quantiles`}
          >
            <div className="table-wrap forecast-table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>P10</th>
                    <th>P50</th>
                    <th>P90</th>
                  </tr>
                </thead>
                <tbody>
                  {run.forecast.map((point) => (
                    <tr key={point.date}>
                      <td>{date(point.date)}</td>
                      <td>{number(point.p10, 2)}</td>
                      <td>{number(point.p50, 2)}</td>
                      <td>{number(point.p90, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
          <Panel
            title="Compare independent series"
            subtitle="Compare the latest saved runs for two store/product series"
          >
            <div className="inline-controls padded">
              <span>
                {run.store_id} / {run.product_id}
              </span>
              <select
                aria-label="Series to compare"
                value={otherSeries}
                onChange={(e) => {
                  setOtherSeries(e.target.value);
                  clearComparison();
                  setError("");
                }}
              >
                <option value="">Choose another series…</option>
                {options.stores.flatMap((s) =>
                  options.store_products[s]
                    .filter((p) => s !== run.store_id || p !== run.product_id)
                    .map((p) => (
                      <option key={`${s}-${p}`} value={JSON.stringify([s, p])}>
                        {s} / {p}
                      </option>
                    )),
                )}
              </select>
              <button
                className="button secondary"
                disabled={!otherSeries}
                onClick={() => void compareSeries()}
              >
                Compare series
              </button>
            </div>
            {seriesComparison.length > 0 && (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Series</th>
                      <th>Champion</th>
                      <th>Horizon</th>
                      <th>Final test period</th>
                      <th>Test WAPE</th>
                      <th>Coverage</th>
                      <th>Sum of forecast medians</th>
                    </tr>
                  </thead>
                  <tbody>
                    {seriesComparison.map((row) => (
                      <tr key={`${row.store_id}-${row.product_id}`}>
                        <td>
                          {row.store_id} / {row.product_id}
                        </td>
                        <td>
                          {row.status === "ok"
                            ? names[row.champion_model!]
                            : "Train this series first"}
                        </td>
                        <td>
                          {row.horizon ?? "—"} {row.frequency}
                        </td>
                        <td>
                          {row.test_period
                            ? `${date(row.test_period.start)} – ${date(row.test_period.end)}`
                            : "—"}
                        </td>
                        <td>
                          {metricValue("wape", row.test_metrics?.wape ?? null)}
                        </td>
                        <td>
                          {row.probabilistic_metrics
                            ? `${number(row.probabilistic_metrics.coverage * 100, 1)}%`
                            : "—"}
                        </td>
                        <td>{number(row.median_total, 1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="panel-footnote">
              Series are trained independently on demand. Different periods and
              demand scales limit direct score comparisons; horizons and
              frequency are shown explicitly.
            </p>
          </Panel>
          {run.warnings.map((warning) => (
            <div key={warning} className="alert warning">
              {warning}
            </div>
          ))}
          <details className="methodology">
            <summary>
              Evaluation boundaries, assumptions &amp; saved artifacts
            </summary>
            <div className="split-details">
              {Object.entries(run.partitions).map(([name, bound]) => (
                <div key={name}>
                  <strong>{name}</strong>
                  <p>
                    {date(bound.start)} – {date(bound.end)}
                  </p>
                  <small>{bound.periods} periods</small>
                </div>
              ))}
            </div>
            <ul>
              {run.assumptions.map((assumption) => (
                <li key={assumption}>{assumption}</li>
              ))}
            </ul>
            <p>
              Saved models:{" "}
              {Object.keys(run.artifacts)
                .map((name) => names[name])
                .join(", ")}
              .
            </p>
            <p>
              Run {run.run_id} · {run.created_at}
            </p>
            <pre>
              {JSON.stringify(
                Object.fromEntries(
                  Object.entries(run.artifacts).map(([name, artifact]) => [
                    name,
                    artifact.hyperparameters,
                  ]),
                ),
                null,
                2,
              )}
            </pre>
          </details>
        </>
      )}
    </>
  );
}
