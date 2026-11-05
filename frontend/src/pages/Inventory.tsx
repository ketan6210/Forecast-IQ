import { useEffect, useRef, useState } from "react";
import { Boxes, Download, Play } from "lucide-react";
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, forecastRuns } from "../api";
import { Loading, Panel, Stat } from "../components";
import { number, shortDate } from "../format";
import type { Dataset } from "../types";
import type {
  InventoryFields,
  InventoryPlan,
  InventoryScenario,
  PolicyComparison,
  PolicyRow,
  Portfolio,
  Segmentation,
  Simulation,
} from "../inventoryTypes";

type Saved = {
  run_id: string;
  champion_model: string;
  created_at: string;
  configuration: { store_id: string; product_id: string; horizon: number };
};
const defaults: InventoryFields = {
  on_hand_inventory: "",
  lead_time: "",
  on_order_inventory: "0",
  backorders: "0",
  service_level: "0.95",
  lead_time_std: "0",
  minimum_order_quantity: "0",
  order_multiple: "1",
  safety_stock_method: "quantile",
  sampling_method: "residual_bootstrap",
  block_size: "1",
  uncertainty_samples: "1000",
  seed: "42",
  annualize_forecast: "false",
  incoming_orders: "[]",
};
const textFields = new Set([
  "warehouse_id",
  "supplier_id",
  "currency",
  "safety_stock_method",
  "sampling_method",
]);
function payload(fields: InventoryFields) {
  const result: Record<string, unknown> = {};
  Object.entries(fields).forEach(([key, value]) => {
    if (!value.trim()) return;
    result[key] =
      key === "incoming_orders"
        ? JSON.parse(value)
        : key === "annualize_forecast"
          ? value === "true"
          : textFields.has(key)
            ? value
            : Number(value);
  });
  return result;
}
function fieldsFrom(plan: InventoryPlan): InventoryFields {
  return Object.fromEntries(
    Object.entries(plan.inputs).map(([key, value]) => [
      key,
      value == null
        ? ""
        : typeof value === "object"
          ? JSON.stringify(value)
          : String(value),
    ]),
  );
}
const value = (n: number | null | undefined, digits = 1) =>
  n == null ? "Unavailable" : number(n, digits);
const pct = (n: number | null | undefined) =>
  n == null ? "Unavailable" : `${number(n * 100, 1)}%`;

function PolicyTable({ rows }: { rows: PolicyRow[] }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {[
              "Policy",
              "Target",
              "Safety stock",
              "ROP",
              "Fill rate",
              "Period service",
              "Cycle service",
              "Stockout rate",
              "Avg. inventory",
              "Holding",
              "Ordering",
              "Shortage",
              "Total cost",
              "Meets fill target",
            ].map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.policy}>
              <td>{r.policy}</td>
              <td>{pct(r.target_service_level)}</td>
              <td>{value(r.safety_stock)}</td>
              <td>{value(r.reorder_point)}</td>
              <td>{pct(r.fill_rate)}</td>
              <td>{pct(r.average_service_level)}</td>
              <td>{pct(r.cycle_service_level)}</td>
              <td>{pct(r.stockout_frequency)}</td>
              <td>{value(r.average_inventory)}</td>
              <td>{value(r.expected_holding_cost)}</td>
              <td>{value(r.expected_ordering_cost)}</td>
              <td>{value(r.expected_stockout_cost)}</td>
              <td>{value(r.expected_total_cost)}</td>
              <td>{r.feasible ? "Yes" : "No"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Inventory({
  dataset,
  onForecast,
}: {
  dataset: Dataset;
  onForecast: () => void;
}) {
  const [runs, setRuns] = useState<Saved[]>([]);
  const [run, setRun] = useState("");
  const [fields, setFields] = useState<InventoryFields>({ ...defaults });
  const [plan, setPlan] = useState<InventoryPlan | null>(null);
  const [simulation, setSimulation] = useState<Simulation | null>(null);
  const [comparison, setComparison] = useState<PolicyComparison | null>(null);
  const [scenario, setScenario] = useState<InventoryScenario | null>(null);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [segmentation, setSegmentation] = useState<Segmentation | null>(null);
  const [rows, setRows] = useState<InventoryPlan[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [sort, setSort] = useState("priority");
  const [risk, setRisk] = useState("");
  const [search, setSearch] = useState("");
  const [reorderOnly, setReorderOnly] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [dirty, setDirty] = useState(false);
  const [horizon, setHorizon] = useState("");
  const [trials, setTrials] = useState(500);
  const [seed, setSeed] = useState(42);
  const [mode, setMode] = useState("monte_carlo");
  const [shortageMode, setShortageMode] = useState("lost_sales");
  const [minimumFill, setMinimumFill] = useState(0.95);
  const [thresholds, setThresholds] = useState({
    a_threshold: 0.8,
    b_threshold: 0.95,
    x_threshold: 0.5,
    y_threshold: 1,
  });
  const active = useRef<AbortController | null>(null);
  const importInput = useRef<HTMLInputElement>(null);
  const datasetQuery = `dataset_id=${encodeURIComponent(dataset.dataset_id)}`;

  useEffect(() => {
    const controller = new AbortController();
    forecastRuns<Saved>(dataset.dataset_id, controller.signal)
      .then(async (data) => {
        setRuns(data);
        const saved = localStorage.getItem(
          `forecastiq.advanced.${dataset.dataset_id}`,
        );
        setRun(
          data.find((r) => r.run_id === saved)?.run_id ?? data[0]?.run_id ?? "",
        );
        const linkedPlan = new URLSearchParams(window.location.search).get(
          "plan",
        );
        if (linkedPlan) {
          const result = await api<InventoryPlan>(
            `/inventory/plans/${encodeURIComponent(linkedPlan)}`,
            { signal: controller.signal },
          );
          if (
            !controller.signal.aborted &&
            result.dataset_id === dataset.dataset_id
          )
            selectPlan(result);
        }
      })
      .catch((e: Error) => {
        if (!controller.signal.aborted) setError(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => {
      controller.abort();
      active.current?.abort();
    };
  }, [datasetQuery, dataset.dataset_id]);

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({
      dataset_id: dataset.dataset_id,
      sort,
      search,
      reorder_only: String(reorderOnly),
      offset: String(offset),
      limit: "50",
    });
    if (risk) params.set("risk", risk);
    setRows([]);
    api<{ items: InventoryPlan[]; total: number }>(
      `/inventory/recommendations?${params}`,
      { signal: controller.signal },
    )
      .then((data) => {
        setRows(data.items);
        setTotal(data.total);
      })
      .catch((e: Error) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [dataset.dataset_id, sort, search, risk, reorderOnly, offset, refresh]);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      api<Portfolio>(`/inventory/kpis?${datasetQuery}`, {
        signal: controller.signal,
      }),
      api<Segmentation>("/inventory/abc-analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dataset_id: dataset.dataset_id, ...thresholds }),
        signal: controller.signal,
      }),
    ])
      .then(([p, s]) => {
        setPortfolio(p);
        setSegmentation(s);
      })
      .catch((e: Error) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [datasetQuery, dataset.dataset_id, refresh, thresholds]);

  function edit(key: string, next: string) {
    setFields((previous) => ({ ...previous, [key]: next }));
    setDirty(true);
    setScenario(null);
  }
  function selectPlan(next: InventoryPlan) {
    setPlan(next);
    setRun(next.forecast_run_id);
    setFields(fieldsFrom(next));
    setDirty(false);
    const savedSimulation = next.latest_simulation;
    setHorizon(String(savedSimulation?.horizon ?? next.forecast_horizon));
    setMode(savedSimulation?.mode ?? "monte_carlo");
    setTrials(
      savedSimulation && savedSimulation.paths > 1
        ? savedSimulation.paths
        : 500,
    );
    setSeed(savedSimulation?.seed ?? 42);
    setShortageMode(savedSimulation?.shortage_mode ?? "lost_sales");
    setScenario(null);
    setSimulation(next.latest_simulation ?? null);
    setComparison(next.latest_comparison ?? null);
    const query = new URLSearchParams({
      dataset: next.dataset_id,
      view: "inventory",
      plan: next.plan_id,
    });
    window.history.replaceState(
      null,
      "",
      `${window.location.pathname}?${query}`,
    );
  }
  async function action(
    label: string,
    operation: (signal: AbortSignal) => Promise<void>,
  ) {
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    setBusy(label);
    setError("");
    setNotice("");
    try {
      await operation(controller.signal);
    } catch (e) {
      if (!controller.signal.aborted)
        setError(e instanceof Error ? e.message : "Calculation failed.");
    } finally {
      if (!controller.signal.aborted) setBusy("");
    }
  }
  const post = <T,>(path: string, data: unknown, signal: AbortSignal) =>
    api<T>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
      signal,
    });
  const simulationBody = () => ({
    plan_id: plan!.plan_id,
    mode,
    shortage_mode: shortageMode,
    horizon: horizon ? Number(horizon) : null,
    trials,
    seed,
  });
  const field = (
    key: string,
    label: string,
    required = false,
    step = "any",
  ) => (
    <label key={key}>
      <span>
        {label}
        {required ? " *" : ""}
      </span>
      <input
        aria-label={label}
        required={required}
        type={textFields.has(key) ? "text" : "number"}
        min="0"
        step={step}
        value={fields[key] ?? ""}
        placeholder={required ? "Required" : "Optional"}
        onChange={(e) => edit(key, e.target.value)}
      />
    </label>
  );
  const chart =
    plan?.forecast
      .slice(0, Number(horizon) || plan.forecast_horizon)
      .map((p, i) => {
        const point = simulation?.trajectory[i];
        return {
          ...p,
          demandRange: [p.p10, p.p90],
          inventory: point?.inventory.mean,
          inventoryRange: point
            ? [point.inventory.p10, point.inventory.p90]
            : undefined,
          receipts: point?.mean_replenishment_received,
          position: point?.inventory_position_mean,
        };
      }) ?? [];

  return (
    <div className="inventory-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">FROM FORECAST TO REPLENISHMENT</span>
          <h1>Inventory optimization</h1>
          <p>
            Set your operating assumptions. See the cost and service tradeoffs.
          </p>
        </div>
        <span className="outline-badge">
          <Boxes size={16} /> Phase 3
        </span>
      </div>
      {error && (
        <div role="alert" className="alert error">
          {error}
        </div>
      )}
      {notice && (
        <div role="status" className="alert">
          {notice}
        </div>
      )}
      {busy && <Loading text={busy} />}
      {!!portfolio?.plans_requiring_recalculation && (
        <div role="status" className="alert">
          {portfolio.plans_requiring_recalculation} saved plans predate
          receipt-timing checks. Recalculate them before using portfolio risk
          counts or replenishment priority.
        </div>
      )}
      {portfolio && (
        <div className="stats-grid inventory-stats">
          <Stat
            label="Inventory value"
            value={value(portfolio.total_inventory_value)}
            note={portfolio.currency ?? "Supplied currency units"}
          />
          <Stat
            label="High-risk series"
            value={String(portfolio.high_risk_series)}
            note={`${portfolio.series_count} SKU / location pairs`}
            accent
          />
          <Stat
            label="Reorders needed"
            value={String(portfolio.below_reorder_point)}
          />
          <Stat
            label="Expediting needed"
            value={String(portfolio.expedite_needed ?? 0)}
            note="Review receipt timing before placing extra orders"
          />
          <Stat
            label="Recommended units"
            value={value(portfolio.total_recommended_order_quantity)}
          />
          <Stat
            label="Portfolio holding cost"
            value={value(portfolio.expected_holding_cost)}
          />
          <Stat
            label="Portfolio shortage cost"
            value={value(portfolio.expected_stockout_cost)}
          />
          <Stat
            label="Mean simulated fill rate"
            value={pct(portfolio.fill_rate)}
            note={`${portfolio.simulated_series_count} current plans simulated`}
          />
          <Stat
            label="Mean target service"
            value={pct(portfolio.average_target_service_level)}
            note="Configured target, not achieved service"
          />
        </div>
      )}
      {loading ? (
        <Loading text="Loading saved forecasts…" />
      ) : !runs.length ? (
        <Panel title="Start with a probabilistic forecast">
          <p>
            Train a series in Advanced forecasting, then return here to use its
            saved P10/P50/P90 outlook.
          </p>
          <button className="button primary" onClick={onForecast}>
            Open advanced forecasting
          </button>
        </Panel>
      ) : (
        <Panel
          title="1. Inventory inputs"
          subtitle="On-hand stock and lead time are required. Blank costs stay unknown. Lead time uses the forecast observation frequency."
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void action("Calculating replenishment…", async (signal) => {
                const next = await post<InventoryPlan>(
                  "/inventory/optimize",
                  { ...payload(fields), forecast_run_id: run },
                  signal,
                );
                if (!signal.aborted) {
                  selectPlan(next);
                  setRefresh((n) => n + 1);
                }
              });
            }}
          >
            <fieldset disabled={!!busy} className="inventory-fieldset">
              <label className="inventory-run">
                <span>Saved probabilistic forecast</span>
                <select
                  aria-label="Inventory forecast"
                  value={run}
                  onChange={(e) => {
                    setRun(e.target.value);
                    setPlan(null);
                    setSimulation(null);
                    setComparison(null);
                    setScenario(null);
                    setFields({ ...defaults });
                    setDirty(false);
                    setError("");
                  }}
                >
                  {runs.map((r) => (
                    <option key={r.run_id} value={r.run_id}>
                      {r.configuration.store_id} / {r.configuration.product_id}{" "}
                      · {r.configuration.horizon} periods · {r.champion_model} ·{" "}
                      {new Date(r.created_at).toLocaleString()}
                    </option>
                  ))}
                </select>
              </label>
              <div className="inventory-form-grid">
                {field("on_hand_inventory", "On-hand inventory", true)}
                {field("lead_time", "Lead time (periods)", true, "1")}
                {field("on_order_inventory", "On-order inventory")}
                {field("backorders", "Backorders")}
                <label>
                  <span>Target service level</span>
                  <select
                    aria-label="Target service level"
                    value={fields.service_level}
                    onChange={(e) => edit("service_level", e.target.value)}
                  >
                    {[
                      0.9,
                      0.95,
                      0.975,
                      0.99,
                      ...(![0.9, 0.95, 0.975, 0.99].includes(
                        Number(fields.service_level),
                      )
                        ? [Number(fields.service_level)]
                        : []),
                    ].map((v) => (
                      <option key={v} value={v}>
                        {v * 100}%
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Safety stock method</span>
                  <select
                    aria-label="Safety stock method"
                    value={fields.safety_stock_method}
                    onChange={(e) =>
                      edit("safety_stock_method", e.target.value)
                    }
                  >
                    <option value="quantile">Forecast uncertainty</option>
                    <option value="demand">
                      Demand variability, fixed lead time
                    </option>
                    <option value="demand_lead_time">
                      Demand + lead-time variability
                    </option>
                    <option value="none">No safety stock</option>
                  </select>
                </label>
                {field("lead_time_std", "Lead-time standard deviation")}
                {field(
                  "target_coverage_periods",
                  "Target coverage (periods)",
                  false,
                  "1",
                )}
                {field("minimum_order_quantity", "Minimum order quantity")}
                {field("order_multiple", "Order multiple")}
              </div>
              <details>
                <summary>
                  Costs, supply arrivals and forecast uncertainty
                </summary>
                <p>
                  Holding cost is annual cost per unit, or unit cost × annual
                  holding rate. Use one style. Total cost requires holding,
                  ordering and shortage costs.
                </p>
                <div className="inventory-form-grid">
                  {field("annual_demand", "Annual demand")}
                  {field("ordering_cost", "Cost per order")}
                  {field(
                    "holding_cost_per_unit_per_year",
                    "Annual holding cost / unit",
                  )}
                  {field(
                    "annual_holding_rate",
                    "Annual holding rate (fraction)",
                  )}
                  {field("stockout_cost", "Shortage cost / unit")}
                  {field("unit_cost", "Unit cost")}
                  {field("selling_price", "Selling price")}
                  {field("currency", "Currency")}
                  {field("warehouse_id", "Warehouse / location")}
                  {field("supplier_id", "Supplier")}
                  {field(
                    "max_inventory_position",
                    "Maximum inventory position",
                  )}
                  {field("cogs_for_horizon", "COGS for simulation horizon")}
                  {field("demand_std", "Demand standard deviation (override)")}
                  <label>
                    <span>Annual demand source</span>
                    <select
                      aria-label="Annual demand source"
                      value={fields.annualize_forecast}
                      onChange={(e) =>
                        edit("annualize_forecast", e.target.value)
                      }
                    >
                      <option value="false">
                        Supplied annual demand, or unknown
                      </option>
                      <option value="true">
                        Extrapolate forecast mean to one year
                      </option>
                    </select>
                  </label>
                  <label>
                    <span>Demand sampling</span>
                    <select
                      aria-label="Demand sampling"
                      value={fields.sampling_method}
                      onChange={(e) => edit("sampling_method", e.target.value)}
                    >
                      <option value="residual_bootstrap">
                        Saved forecast-error bootstrap
                      </option>
                      <option value="quantile_interpolation">
                        P10/P50/P90 interpolation + bounded tails
                      </option>
                    </select>
                  </label>
                  {field("block_size", "Residual block size", false, "1")}
                  {field(
                    "uncertainty_samples",
                    "Lead-time sampling paths",
                    false,
                    "1",
                  )}
                  {field("seed", "Recommendation seed", false, "1")}
                </div>
                <label>
                  <span>
                    Existing incoming orders — JSON array, 1-based arrival
                    periods
                  </span>
                  <textarea
                    aria-label="Incoming orders"
                    value={fields.incoming_orders}
                    onChange={(e) => edit("incoming_orders", e.target.value)}
                    placeholder={'[{"period": 3, "quantity": 100}]'}
                  />
                </label>
                <p>
                  Arrival quantities must sum to on-order inventory. A schedule
                  is required for simulation when on-order inventory is
                  positive.
                </p>
              </details>
              <div className="inventory-actions">
                <button type="submit" className="button primary">
                  Calculate replenishment
                </button>
                {plan && (
                  <button
                    type="button"
                    className="button secondary"
                    onClick={() =>
                      void action(
                        "Comparing what-if scenario…",
                        async (signal) => {
                          const changes = Object.fromEntries(
                            Object.keys(plan.inputs).map((k) => [k, null]),
                          );
                          const next = await post<InventoryScenario>(
                            "/inventory/scenario",
                            {
                              plan_id: plan.plan_id,
                              changes: { ...changes, ...payload(fields) },
                              horizon: horizon ? Number(horizon) : null,
                              trials,
                              seed,
                              shortage_mode: shortageMode,
                            },
                            signal,
                          );
                          if (!signal.aborted) setScenario(next);
                        },
                      )
                    }
                  >
                    Compare inputs as what-if
                  </button>
                )}
                {dirty && plan && (
                  <small>
                    Inputs changed. Calculate a new plan or compare them with
                    the saved plan.
                  </small>
                )}
              </div>
            </fieldset>
          </form>
        </Panel>
      )}

      {plan && (
        <>
          <Panel
            title={`2. Replenishment decision · ${plan.sku_id} / ${plan.location_id}`}
            subtitle={`Saved plan · ${new Date(plan.created_at).toLocaleString()} · ${plan.frequency}`}
          >
            {!plan.supply_timing_note && (
              <div className="alert warning">
                This saved plan predates receipt-timing checks. Calculate
                replenishment again to update its risk and shortage assessment.
              </div>
            )}
            <div className="inventory-decision">
              <span className={`risk-pill ${plan.risk_level}`}>
                {plan.supply_timing_note
                  ? `${plan.risk_level.toUpperCase()} RISK`
                  : "RECALCULATE RISK"}
              </span>
              <strong>
                {plan.reorder_needed
                  ? `Order ${value(plan.recommended_order_quantity)} units`
                  : "Inventory position is above the reorder point"}
              </strong>
              <small>
                Sampled lead-time stockout probability:{" "}
                {plan.supply_timing_note
                  ? pct(plan.estimated_stockout_probability)
                  : "Recalculate"}
              </small>
            </div>
            {plan.expedite_needed && (
              <div className="alert warning" role="status">
                Expedite or reschedule supply: {value(plan.expedite_quantity)}{" "}
                units needed immediately at the selected service level. This is
                a timing shortfall, not an additional purchase order.
              </div>
            )}
            {plan.supply_timing_note && <p>{plan.supply_timing_note}</p>}
            <div className="stats-grid inventory-stats">
              {[
                ["Physical on-hand", value(plan.on_hand_inventory)],
                ["Inventory position", value(plan.inventory_position)],
                ["Forecast P50 sum", value(plan.forecast_p50_total)],
                [
                  "Base lead-time demand",
                  value(plan.expected_lead_time_demand),
                ],
                ["Safety stock", value(plan.safety_stock)],
                ["Reorder point", value(plan.reorder_point)],
                ["EOQ", value(plan.eoq)],
                ["Target service", pct(plan.service_level)],
                [
                  "Supply coverage",
                  `${value(plan.coverage_value)} ${plan.coverage_unit}`,
                ],
                [
                  "P50 / P90 shortage",
                  plan.supply_timing_note
                    ? `${value(plan.shortage.p50)} / ${value(plan.shortage.p90)}`
                    : "Recalculate",
                ],
                ["P90 revenue at risk", value(plan.revenue_at_risk?.p90)],
              ].map(([label, v]) => (
                <Stat key={label} label={label} value={v} />
              ))}
            </div>
            {plan.eoq_reason && <p>{plan.eoq_reason}</p>}
            {plan.constraint_note && <p>{plan.constraint_note}</p>}
            {plan.shortage_definition && <p>{plan.shortage_definition}</p>}
            <details open>
              <summary>How this recommendation was calculated</summary>
              <ul>
                {plan.calculation_details.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </details>
            <details>
              <summary>Uncertainty and operating assumptions</summary>
              <p>
                {plan.sampling.method}. {plan.sampling.assumptions}
              </p>
              <p>
                Lead times: {plan.sampling.lead_time_model}. P90 lead-time
                demand: {value(plan.p90_lead_time_demand)} units.
              </p>
              <ul>
                {plan.assumptions.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </details>
          </Panel>
          <Panel
            title="3. Simulate inventory and compare policies"
            subtitle="Use the saved plan. Orders are reviewed after demand; zero-lead arrivals occur after demand in the same period."
          >
            <fieldset disabled={!!busy} className="inventory-fieldset">
              <div className="inventory-form-grid">
                <label>
                  <span>Simulation horizon (periods)</span>
                  <input
                    aria-label="Simulation horizon"
                    type="number"
                    min="1"
                    max={plan.forecast_horizon}
                    value={horizon}
                    onChange={(e) => {
                      setHorizon(e.target.value);
                      setSimulation(null);
                      setComparison(null);
                      setScenario(null);
                    }}
                  />
                </label>
                <label>
                  <span>Simulation mode</span>
                  <select
                    aria-label="Simulation mode"
                    value={mode}
                    onChange={(e) => setMode(e.target.value)}
                  >
                    <option value="monte_carlo">Monte Carlo</option>
                    <option value="deterministic">Deterministic P50</option>
                  </select>
                </label>
                <label>
                  <span>Monte Carlo paths</span>
                  <select
                    aria-label="Monte Carlo paths"
                    value={trials}
                    onChange={(e) => setTrials(Number(e.target.value))}
                  >
                    {[100, 500, 1000].map((n) => (
                      <option key={n}>{n}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Simulation seed</span>
                  <input
                    aria-label="Simulation seed"
                    type="number"
                    min="0"
                    value={seed}
                    onChange={(e) => setSeed(Number(e.target.value))}
                  />
                </label>
                <label>
                  <span>Unfilled demand</span>
                  <select
                    aria-label="Unfilled demand"
                    value={shortageMode}
                    onChange={(e) => setShortageMode(e.target.value)}
                  >
                    <option value="lost_sales">Lost sales</option>
                    <option value="backorders">Backorders</option>
                  </select>
                </label>
                <label>
                  <span>Minimum fill rate for policy choice</span>
                  <input
                    aria-label="Minimum fill rate"
                    type="number"
                    min="0"
                    max="1"
                    step="0.01"
                    value={minimumFill}
                    onChange={(e) => setMinimumFill(Number(e.target.value))}
                  />
                </label>
              </div>
              <div className="inventory-actions">
                <button
                  className="button primary"
                  disabled={dirty}
                  onClick={() =>
                    void action("Simulating inventory…", async (signal) => {
                      const next = await post<Simulation>(
                        "/inventory/simulate",
                        simulationBody(),
                        signal,
                      );
                      if (!signal.aborted) {
                        setSimulation(next);
                        setRefresh((n) => n + 1);
                      }
                    })
                  }
                >
                  <Play size={15} /> Run simulation
                </button>
                <button
                  className="button secondary"
                  disabled={dirty}
                  onClick={() =>
                    void action(
                      "Evaluating cost and service tradeoffs…",
                      async (signal) => {
                        const next = await post<PolicyComparison>(
                          "/inventory/policy-comparison",
                          {
                            ...simulationBody(),
                            minimum_fill_rate: minimumFill,
                          },
                          signal,
                        );
                        if (!signal.aborted) setComparison(next);
                      },
                    )
                  }
                >
                  Compare policies
                </button>
              </div>
            </fieldset>
            {simulation && (
              <>
                <p className="inventory-result-note">
                  {simulation.mode} · {simulation.paths} paths ·{" "}
                  {simulation.horizon} periods · seed {simulation.seed} ·{" "}
                  {value(simulation.duration_seconds, 3)} seconds
                </p>
                <div className="stats-grid inventory-stats">
                  <Stat
                    label="Immediate fill rate"
                    value={pct(simulation.fill_rate)}
                  />
                  <Stat
                    label="Periods without stockout"
                    value={pct(simulation.average_service_level)}
                  />
                  <Stat
                    label="Completed-cycle service"
                    value={pct(simulation.cycle_service_level)}
                  />
                  <Stat
                    label="Average inventory"
                    value={value(simulation.average_inventory)}
                  />
                  <Stat
                    label="Expected lost units"
                    value={value(simulation.expected_lost_units)}
                  />
                  <Stat
                    label="Expected total cost"
                    value={value(simulation.expected_total_cost)}
                  />
                  <Stat
                    label="Cost P10 / P50 / P90"
                    value={
                      simulation.cost_distribution
                        ? `${value(simulation.cost_distribution.p10)} / ${value(simulation.cost_distribution.p50)} / ${value(simulation.cost_distribution.p90)}`
                        : "Unavailable"
                    }
                  />
                  <Stat
                    label="Inventory turnover"
                    value={value(simulation.inventory_turnover)}
                    note="Supplied horizon COGS / average stock value"
                  />
                </div>
                {simulation.cost_unavailable_reason && (
                  <p>{simulation.cost_unavailable_reason}</p>
                )}
                <p>
                  Operating cost breakdown: holding{" "}
                  {value(simulation.expected_holding_cost)}, ordering{" "}
                  {value(simulation.expected_ordering_cost)}, shortage{" "}
                  {value(simulation.expected_stockout_cost)}. Shortage mode:{" "}
                  {simulation.shortage_mode}. Ending backorders:{" "}
                  {value(simulation.expected_ending_backorders)}.
                </p>
                <details>
                  <summary>Simulation assumptions</summary>
                  <ul>
                    {simulation.assumptions.map((s) => (
                      <li key={s}>{s}</li>
                    ))}
                  </ul>
                </details>
              </>
            )}
            <div
              className="chart inventory-chart"
              role="img"
              aria-label="Forecast demand and projected inventory with replenishment events"
            >
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart
                  data={chart}
                  margin={{ top: 20, right: 20, left: 5, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 5" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tickFormatter={shortDate}
                    minTickGap={40}
                  />
                  <YAxis width={55} />
                  <Tooltip labelFormatter={(v) => shortDate(String(v))} />
                  <Legend />
                  <Area
                    isAnimationActive={false}
                    dataKey="demandRange"
                    name="Demand P10–P90"
                    fill="#dcece6"
                    stroke="none"
                  />
                  <Line
                    isAnimationActive={false}
                    dataKey="p50"
                    name="Demand P50"
                    dot={false}
                    stroke="#238674"
                    strokeWidth={2}
                  />
                  {simulation && (
                    <>
                      <Area
                        isAnimationActive={false}
                        dataKey="inventoryRange"
                        name="Inventory P10–P90"
                        fill="#e3e8fa"
                        fillOpacity={0.5}
                        stroke="none"
                      />
                      <Line
                        isAnimationActive={false}
                        dataKey="inventory"
                        name="Mean on-hand inventory"
                        dot={false}
                        stroke="#576bc2"
                        strokeWidth={2}
                      />
                      <Line
                        isAnimationActive={false}
                        dataKey="position"
                        name="Mean inventory position"
                        dot={false}
                        stroke="#8a5da5"
                        strokeDasharray="4 3"
                      />
                      <Bar
                        isAnimationActive={false}
                        dataKey="receipts"
                        name="Mean replenishment received"
                        fill="#dbb061"
                        maxBarSize={10}
                      />
                    </>
                  )}
                  <ReferenceLine
                    y={plan.reorder_point}
                    stroke="#c87643"
                    strokeDasharray="5 3"
                    label={{
                      value: "Reorder point (position)",
                      position: "insideTopRight",
                    }}
                  />
                  <ReferenceLine
                    y={plan.safety_stock}
                    stroke="#a55772"
                    strokeDasharray="3 3"
                    label={{
                      value: "Safety stock",
                      position: "insideBottomRight",
                    }}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <p>
              Forecast bands describe marginal demand; simulated inventory bands
              come from sampled paths. The reorder threshold applies to
              inventory position.
            </p>
          </Panel>
          {comparison && (
            <Panel
              title="Policy cost / service comparison"
              subtitle={comparison.objective}
            >
              <p>
                <strong>
                  Recommended policy:{" "}
                  {comparison.recommended_policy ??
                    "None feasible with complete costs"}
                  .
                </strong>{" "}
                {comparison.recommendation_reason}
              </p>
              <PolicyTable rows={comparison.policies} />
              <h4>Service-level candidates</h4>
              <PolicyTable rows={comparison.service_level_comparison} />
              <ul>
                {comparison.notes.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </Panel>
          )}
          {scenario && (
            <Panel title="What-if comparison" subtitle={scenario.note}>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Measure</th>
                      <th>Saved inputs</th>
                      <th>Changed inputs</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(
                      [
                        ["Lead time", "lead_time"],
                        ["Safety stock", "safety_stock"],
                        ["Reorder point", "reorder_point"],
                        ["EOQ", "eoq"],
                        ["Order quantity", "recommended_order_quantity"],
                        ["Stockout risk", "risk_level"],
                      ] as const
                    ).map(([label, k]) => (
                      <tr key={k}>
                        <td>{label}</td>
                        <td>
                          {String(
                            k === "lead_time"
                              ? scenario.baseline.recommendation.inputs
                                  .lead_time
                              : (scenario.baseline.recommendation[k] ??
                                  "Unavailable"),
                          )}
                        </td>
                        <td>
                          {String(
                            k === "lead_time"
                              ? fields.lead_time
                              : (scenario.scenario.recommendation[k] ??
                                  "Unavailable"),
                          )}
                        </td>
                      </tr>
                    ))}
                    <tr>
                      <td>Expected total cost</td>
                      <td>
                        {value(
                          scenario.baseline.simulation.expected_total_cost,
                        )}
                      </td>
                      <td>
                        {value(
                          scenario.scenario.simulation.expected_total_cost,
                        )}
                      </td>
                    </tr>
                    <tr>
                      <td>Immediate fill rate</td>
                      <td>{pct(scenario.baseline.simulation.fill_rate)}</td>
                      <td>{pct(scenario.scenario.simulation.fill_rate)}</td>
                    </tr>
                    <tr>
                      <td>Forecast horizon</td>
                      <td>
                        {scenario.baseline.recommendation.forecast_horizon}
                      </td>
                      <td>
                        {scenario.scenario.recommendation.forecast_horizon}
                      </td>
                    </tr>
                    <tr>
                      <td>Forecast P50 sum</td>
                      <td>
                        {value(
                          scenario.baseline.recommendation.forecast_p50_total,
                        )}
                      </td>
                      <td>
                        {value(
                          scenario.scenario.recommendation.forecast_p50_total,
                        )}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </Panel>
          )}
        </>
      )}
      <Panel
        title="Replenishment queue"
        subtitle="Latest plan per SKU / store / location. Priority: high risk, then immediate supply shortfall, reorder-point deficit and forecast volume."
        action={
          <a
            className="button secondary"
            href={`/api/inventory/export?${datasetQuery}`}
            download
          >
            <Download size={15} /> Export CSV
          </a>
        }
      >
        <fieldset disabled={!!busy} className="inventory-fieldset">
          <div className="inventory-form-grid">
            <label>
              <span>Search SKU or location</span>
              <input
                aria-label="Search inventory"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setOffset(0);
                }}
              />
            </label>
            <label>
              <span>Risk filter</span>
              <select
                aria-label="Risk filter"
                value={risk}
                onChange={(e) => {
                  setRisk(e.target.value);
                  setOffset(0);
                }}
              >
                <option value="">All risks</option>
                {["high", "medium", "low"].map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Sort recommendations</span>
              <select
                aria-label="Sort recommendations"
                value={sort}
                onChange={(e) => {
                  setSort(e.target.value);
                  setOffset(0);
                }}
              >
                <option value="priority">Operational priority</option>
                <option value="sku">SKU</option>
                <option value="quantity">Order quantity, largest first</option>
              </select>
            </label>
            <label className="inventory-check">
              <input
                type="checkbox"
                checked={reorderOnly}
                onChange={(e) => {
                  setReorderOnly(e.target.checked);
                  setOffset(0);
                }}
              />{" "}
              Reorder needed only
            </label>
          </div>
        </fieldset>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                {[
                  "SKU / location",
                  "On-hand",
                  "Position",
                  "LT P50",
                  "LT P90",
                  "Safety stock",
                  "ROP",
                  "EOQ",
                  "Order qty",
                  "Expedite units",
                  "Risk",
                  "Reorder?",
                ].map((h) => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.plan_id}>
                  <td>
                    <button
                      className="inventory-row-link"
                      disabled={!!busy || loading}
                      onClick={() =>
                        void action(
                          "Opening inventory plan…",
                          async (signal) => {
                            const next = await api<InventoryPlan>(
                              `/inventory/plans/${r.plan_id}`,
                              { signal },
                            );
                            if (!signal.aborted) selectPlan(next);
                          },
                        )
                      }
                    >
                      {r.sku_id} / {r.location_id}
                    </button>
                  </td>
                  {[
                    r.on_hand_inventory,
                    r.inventory_position,
                    r.p50_lead_time_demand,
                    r.p90_lead_time_demand,
                    r.safety_stock,
                    r.reorder_point,
                    r.eoq,
                    r.recommended_order_quantity,
                    r.expedite_quantity,
                  ].map((v, i) => (
                    <td key={i}>{value(v)}</td>
                  ))}
                  <td>
                    <span className={`risk-pill ${r.risk_level}`}>
                      {r.supply_timing_note ? r.risk_level : "Recalculate"}
                    </span>
                  </td>
                  <td>{r.reorder_needed ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!rows.length && (
          <p>
            No matching recommendations. Calculate a plan or import inventory
            inputs.
          </p>
        )}
        <div className="inventory-actions">
          <button
            className="button secondary"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - 50))}
          >
            Previous
          </button>
          <span>
            {total} matching plans · {offset + 1}–{Math.min(offset + 50, total)}
          </span>
          <button
            className="button secondary"
            disabled={offset + 50 >= total}
            onClick={() => setOffset(offset + 50)}
          >
            Next
          </button>
          <button
            className="button secondary"
            disabled={!!busy}
            onClick={() => importInput.current?.click()}
          >
            Import inventory CSV
          </button>
          <input
            ref={importInput}
            type="file"
            accept=".csv"
            aria-label="Import inventory CSV"
            hidden
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              void action("Importing inventory inputs…", async (signal) => {
                const data = new FormData();
                data.append("file", file);
                const result = await api<{
                  successful: number;
                  failed: number;
                  errors: { row: number; error: string }[];
                }>("/inventory/import", { method: "POST", body: data, signal });
                if (!signal.aborted) {
                  setNotice(
                    `${result.successful} plans saved; ${result.failed} rows rejected. ${result.errors.map((r) => `Row ${r.row}: ${r.error}`).join(" ")}`,
                  );
                  setRefresh((n) => n + 1);
                }
              });
              e.target.value = "";
            }}
          />
        </div>
        <details>
          <summary>CSV input format and portfolio assumptions</summary>
          <p>
            Required columns: forecast_run_id, on_hand_inventory, lead_time.
            Optional columns use the input names in API documentation, including
            warehouse_id, annual_demand, unit_cost, ordering_cost and
            stockout_cost. Up to 1,000 rows / 2 MB per batch. Each row uses an
            existing Phase 2 forecast.
          </p>
          {portfolio?.notes.map((s) => (
            <p key={s}>{s}</p>
          ))}
        </details>
      </Panel>
      {segmentation && (
        <Panel
          title="ABC / XYZ segmentation"
          subtitle="Consumption value and demand variability provide context for reviewing your portfolio."
        >
          <div className="inventory-form-grid">
            {Object.entries(thresholds).map(([key, v]) => (
              <label key={key}>
                <span>
                  {key.replace("_threshold", "").toUpperCase()} threshold
                </span>
                <input
                  aria-label={`${key} threshold`}
                  type="number"
                  min="0"
                  step="0.05"
                  value={v}
                  onChange={(e) =>
                    setThresholds((previous) => ({
                      ...previous,
                      [key]: Number(e.target.value),
                    }))
                  }
                />
              </label>
            ))}
          </div>
          <div className="abc-matrix">
            {["A", "B", "C"].flatMap((a) =>
              ["X", "Y", "Z"].map((x) => (
                <div key={a + x}>
                  <strong>{a + x}</strong>
                  <span>
                    {segmentation.matrix_distribution[a + x] ?? 0} series
                  </span>
                </div>
              )),
            )}
          </div>
          <p>
            ABC distribution:{" "}
            {Object.entries(segmentation.abc_distribution)
              .map(([k, v]) => `${k}: ${v}`)
              .join(" · ") || "No plans"}
            . Missing comparable annual value: {segmentation.excluded_from_abc}.
          </p>
          <details>
            <summary>Classification details</summary>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>SKU / location</th>
                    <th>Annual consumption value</th>
                    <th>Demand CV</th>
                    <th>ABC / XYZ</th>
                  </tr>
                </thead>
                <tbody>
                  {segmentation.items.map((r, i) => (
                    <tr key={i}>
                      <td>
                        {r.sku_id} / {r.location_id}
                      </td>
                      <td>{value(r.annual_consumption_value)}</td>
                      <td>{value(r.cv, 3)}</td>
                      <td>
                        {r.matrix ??
                          `${r.abc_class ?? "?"}${r.xyz_class ?? "?"}`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul>
              {segmentation.notes.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
          </details>
        </Panel>
      )}
    </div>
  );
}
