import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Loading, Panel, Stat } from "../components";
import { number } from "../format";
import type { InventoryPlan } from "../inventoryTypes";

type AllocationItem = {
  plan_id: string;
  sku_id: string;
  store_id: string;
  location_id: string;
  requested_quantity: number;
  allocated_quantity: number;
  deferred_quantity: number;
  purchase_cost: number;
  priority_weight: number;
  status: string;
};
type Allocation = {
  allocation_id: string;
  dataset_id: string;
  created_at: string;
  location_id: string;
  solver_status: string;
  relative_gap: number | null;
  currency: string;
  purchase_cost: number;
  purchasing_budget: number | null;
  budget_remaining: number | null;
  available_capacity: number | null;
  capacity_unit: string | null;
  capacity_used: number | null;
  capacity_remaining: number | null;
  total_allocated_quantity: number;
  total_deferred_quantity: number;
  objective: string;
  items: AllocationItem[];
  notes: string[];
};
type Saved = Pick<
  Allocation,
  "allocation_id" | "created_at" | "location_id" | "currency" | "purchase_cost"
>;
type Choice = { weight: string; space: string };

export default function SharedAllocation({
  datasetId,
  refresh,
}: {
  datasetId: string;
  refresh: number;
}) {
  const [plans, setPlans] = useState<InventoryPlan[]>([]);
  const [saved, setSaved] = useState<Saved[]>([]);
  const [location, setLocation] = useState("");
  const [choices, setChoices] = useState<Record<string, Choice>>({});
  const [budget, setBudget] = useState("");
  const [capacity, setCapacity] = useState("");
  const [unit, setUnit] = useState("");
  const [result, setResult] = useState<Allocation | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const active = useRef<AbortController | null>(null);
  const listPath = `/inventory/allocations?dataset_id=${encodeURIComponent(datasetId)}`;

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    async function load() {
      const rows = new Map<string, InventoryPlan>();
      for (let offset = 0; ; offset += 1000) {
        const page = await api<{ items: InventoryPlan[]; total: number }>(
          `/inventory/recommendations?dataset_id=${encodeURIComponent(datasetId)}&limit=1000&offset=${offset}&sort=sku`,
          { signal: controller.signal },
        );
        const before = rows.size;
        page.items.forEach((row) => rows.set(row.plan_id, row));
        if (offset + page.items.length >= page.total) break;
        if (rows.size === before)
          throw new Error(
            "Inventory list changed while loading. Refresh to retry.",
          );
      }
      const allocations = await api<Saved[]>(listPath, {
        signal: controller.signal,
      });
      if (!controller.signal.aborted) {
        setPlans([...rows.values()]);
        setSaved(allocations);
        setChoices({});
      }
    }
    void load()
      .catch((e: Error) => {
        if (!controller.signal.aborted) setError(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [datasetId, refresh, listPath]);
  useEffect(() => () => active.current?.abort(), []);

  const locations = [...new Set(plans.map((p) => p.location_id))].sort();
  const selectedLocation = location || locations[0] || "";
  const visible = plans.filter((p) => p.location_id === selectedLocation);
  const selected = visible.filter((p) => choices[p.plan_id]);
  const clearResult = () => {
    setResult(null);
    setError("");
  };
  async function run(operation: (signal: AbortSignal) => Promise<void>) {
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    setBusy(true);
    setError("");
    try {
      await operation(controller.signal);
    } catch (e) {
      if (!controller.signal.aborted)
        setError(e instanceof Error ? e.message : "Allocation failed.");
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return (
    <Panel
      title="Shared budget and capacity"
      subtitle="Allocate one replenishment purchase across SKUs at the same location."
    >
      <p>
        Maximize priority-weighted allocated units, up to each saved
        recommendation. MOQ, order multiples and per-item limits still apply. A
        weight of 2 values each unit twice as much as a weight of 1.
      </p>
      {loading && <Loading text="Loading plans for allocation…" />}
      {error && <p role="alert">{error}</p>}
      <fieldset className="inventory-fieldset" disabled={loading || busy}>
        <div className="inventory-form-grid">
          <label>
            <span>Allocation location</span>
            <select
              aria-label="Allocation location"
              value={selectedLocation}
              onChange={(e) => {
                setLocation(e.target.value);
                setChoices({});
                clearResult();
              }}
            >
              {!locations.length && (
                <option value="">Create inventory plans first</option>
              )}
              {locations.map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </label>
          <label>
            <span>Purchasing budget</span>
            <input
              aria-label="Purchasing budget"
              type="number"
              min="0"
              step="any"
              placeholder="Optional"
              value={budget}
              onChange={(e) => {
                setBudget(e.target.value);
                clearResult();
              }}
            />
          </label>
          <label>
            <span>Available capacity for new orders</span>
            <input
              aria-label="Available capacity for new orders"
              type="number"
              min="0"
              step="any"
              placeholder="Optional"
              value={capacity}
              onChange={(e) => {
                setCapacity(e.target.value);
                clearResult();
              }}
            />
          </label>
          <label>
            <span>Capacity unit</span>
            <input
              aria-label="Capacity unit"
              placeholder="e.g. cubic metres"
              value={unit}
              disabled={capacity === ""}
              onChange={(e) => {
                setUnit(e.target.value);
                clearResult();
              }}
            />
          </label>
        </div>
        <p>
          Enter a budget, capacity, or both. Budget covers merchandise only, in
          the common currency recorded on the plans. Capacity must be free space
          reserved for these new orders, after existing stock and committed
          deliveries. Every selected plan needs a unit cost and currency, and
          matching forecast dates, horizon and frequency.
        </p>
        <div className="table-wrap" tabIndex={0}>
          <table>
            <thead>
              <tr>
                <th>Select</th>
                <th>SKU / store</th>
                <th>Requested units</th>
                <th>Unit cost</th>
                <th>Priority weight</th>
                <th>Space per unit</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((p) => (
                <tr key={p.plan_id}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Allocate ${p.sku_id} / ${p.store_id}`}
                      checked={!!choices[p.plan_id]}
                      onChange={(e) => {
                        const checked = e.target.checked;
                        setChoices((old) => {
                          const next = { ...old };
                          if (checked)
                            next[p.plan_id] = { weight: "1", space: "" };
                          else delete next[p.plan_id];
                          return next;
                        });
                        clearResult();
                      }}
                    />
                  </td>
                  <td>
                    {p.sku_id} / {p.store_id}
                  </td>
                  <td>{number(p.recommended_order_quantity, 2)}</td>
                  <td>
                    {p.inputs.unit_cost == null
                      ? "Missing unit cost"
                      : `${number(Number(p.inputs.unit_cost), 2)} ${p.inputs.currency || "(currency required)"}`}
                  </td>
                  <td>
                    <input
                      type="number"
                      min="0.001"
                      max="1000"
                      step="any"
                      aria-label={`Priority ${p.sku_id} / ${p.store_id}`}
                      disabled={!choices[p.plan_id]}
                      value={choices[p.plan_id]?.weight ?? "1"}
                      onChange={(e) => {
                        setChoices((old) => ({
                          ...old,
                          [p.plan_id]: {
                            ...old[p.plan_id],
                            weight: e.target.value,
                          },
                        }));
                        clearResult();
                      }}
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      min="0.000001"
                      step="any"
                      aria-label={`Space ${p.sku_id} / ${p.store_id}`}
                      disabled={!choices[p.plan_id] || capacity === ""}
                      value={choices[p.plan_id]?.space ?? ""}
                      onChange={(e) => {
                        setChoices((old) => ({
                          ...old,
                          [p.plan_id]: {
                            ...old[p.plan_id],
                            space: e.target.value,
                          },
                        }));
                        clearResult();
                      }}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!visible.length && (
          <p>Create or import inventory plans to allocate shared resources.</p>
        )}
        <div className="inventory-actions">
          <button
            className="button primary"
            disabled={
              !selected.length ||
              selected.length > 200 ||
              (budget === "" && capacity === "")
            }
            onClick={() =>
              void run(async (signal) => {
                const body = {
                  dataset_id: datasetId,
                  purchasing_budget: budget === "" ? null : Number(budget),
                  available_capacity: capacity === "" ? null : Number(capacity),
                  capacity_unit: capacity === "" ? null : unit,
                  items: selected.map((p) => ({
                    plan_id: p.plan_id,
                    priority_weight: Number(choices[p.plan_id].weight),
                    capacity_per_unit:
                      capacity === "" ? null : Number(choices[p.plan_id].space),
                  })),
                };
                const next = await api<Allocation>("/inventory/allocate", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify(body),
                  signal,
                });
                if (!signal.aborted) setResult(next);
                const history = await api<Saved[]>(listPath, { signal });
                if (!signal.aborted) setSaved(history);
              })
            }
          >
            {busy ? "Working…" : "Allocate selected plans"}
          </button>
          <span>{selected.length} selected · maximum 200</span>
        </div>
        <label>
          <span>Saved allocation</span>
          <select
            aria-label="Saved allocation"
            value={result?.allocation_id ?? ""}
            onChange={(e) => {
              const id = e.target.value;
              if (!id) {
                setResult(null);
                return;
              }
              void run(async (signal) => {
                const next = await api<Allocation>(
                  `/inventory/allocations/${id}`,
                  { signal },
                );
                if (!signal.aborted && next.dataset_id === datasetId)
                  setResult(next);
              });
            }}
          >
            <option value="">Select a saved allocation</option>
            {saved.map((r) => (
              <option key={r.allocation_id} value={r.allocation_id}>
                {r.location_id} · {r.created_at} · {number(r.purchase_cost, 2)}{" "}
                {r.currency}
              </option>
            ))}
          </select>
        </label>
      </fieldset>
      {result && (
        <section aria-label="Allocation result">
          <h3>Saved allocation · {result.location_id}</h3>
          <p>
            {result.solver_status === "optimal"
              ? "Optimal under the stated objective and constraints."
              : "Feasible allocation; time limit reached before proving optimality."}
            {result.solver_status !== "optimal" &&
              result.relative_gap != null &&
              ` Remaining objective gap: ${number(result.relative_gap * 100, 2)}%.`}
          </p>
          <p>
            Saved limits: budget{" "}
            {result.purchasing_budget == null
              ? "unconstrained"
              : `${number(result.purchasing_budget, 2)} ${result.currency}`}
            ; capacity{" "}
            {result.available_capacity == null
              ? "unconstrained"
              : `${number(result.available_capacity, 2)} ${result.capacity_unit}`}
            .
          </p>
          <div className="stats-grid">
            <Stat
              label="Allocated units"
              value={number(result.total_allocated_quantity, 2)}
            />
            <Stat
              label="Deferred units"
              value={number(result.total_deferred_quantity, 2)}
            />
            <Stat
              label="Purchase cost"
              value={`${number(result.purchase_cost, 2)} ${result.currency}`}
              note={
                result.budget_remaining == null
                  ? "No budget limit"
                  : `${number(result.budget_remaining, 2)} budget remaining`
              }
            />
            <Stat
              label="Capacity used"
              value={
                result.capacity_used == null
                  ? "Not constrained"
                  : `${number(result.capacity_used, 2)} ${result.capacity_unit}`
              }
            />
          </div>
          <div className="table-wrap" tabIndex={0}>
            <table>
              <thead>
                <tr>
                  <th>SKU / store</th>
                  <th>Requested</th>
                  <th>Allocated</th>
                  <th>Deferred</th>
                  <th>Purchase cost</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {result.items.map((r) => (
                  <tr key={r.plan_id}>
                    <td>
                      {r.sku_id} / {r.store_id}
                    </td>
                    <td>{number(r.requested_quantity, 2)}</td>
                    <td>{number(r.allocated_quantity, 2)}</td>
                    <td>{number(r.deferred_quantity, 2)}</td>
                    <td>{number(r.purchase_cost, 2)}</td>
                    <td>{r.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <a
            className="button secondary"
            href={`/api/inventory/allocations/${result.allocation_id}/export`}
            download
          >
            Export allocation CSV
          </a>
          <details>
            <summary>Allocation scope and assumptions</summary>
            <p>{result.objective}</p>
            {result.notes.map((note) => (
              <p key={note}>{note}</p>
            ))}
          </details>
        </section>
      )}
    </Panel>
  );
}
