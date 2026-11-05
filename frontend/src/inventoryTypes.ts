export type InventoryFields = Record<string, string>;
export type Distribution = {
  mean: number;
  p10: number;
  p50: number;
  p90: number;
};
export interface InventoryPlan {
  dataset_id: string;
  plan_id: string;
  forecast_run_id: string;
  sku_id: string;
  location_id: string;
  store_id: string;
  frequency: string;
  forecast_horizon: number;
  created_at: string;
  inputs: Record<string, unknown>;
  forecast: { date: string; p10: number; p50: number; p90: number }[];
  on_hand_inventory: number;
  inventory_position: number;
  forecast_p50_total: number;
  expected_lead_time_demand: number;
  p50_lead_time_demand: number;
  p90_lead_time_demand: number;
  safety_stock: number;
  reorder_point: number;
  recommended_order_quantity: number;
  eoq: number | null;
  eoq_reason: string | null;
  service_level: number;
  risk_level: string;
  reorder_needed: boolean;
  estimated_stockout_probability: number;
  coverage_value: number | null;
  coverage_unit: string;
  constraint_note: string | null;
  shortage: { p50: number; p90: number };
  expedite_needed?: boolean;
  expedite_quantity?: number;
  supply_timing_note?: string;
  shortage_definition?: string;
  revenue_at_risk: { p50: number; p90: number } | null;
  calculation_details: string[];
  assumptions: string[];
  priority_rule: string;
  sampling: { method: string; assumptions: string; lead_time_model: string };
  latest_simulation?: Simulation | null;
  latest_comparison?: PolicyComparison | null;
}
export interface Simulation {
  shortage_mode: string;
  mode: string;
  paths: number;
  horizon: number;
  seed: number;
  duration_seconds: number;
  fill_rate: number;
  average_service_level: number;
  cycle_service_level: number | null;
  stockout_frequency: number;
  average_inventory: number;
  expected_lost_units: number;
  expected_shortage_units: number;
  expected_ending_backorders: number;
  expected_holding_cost: number | null;
  expected_ordering_cost: number | null;
  expected_stockout_cost: number | null;
  expected_total_cost: number | null;
  cost_distribution: Distribution | null;
  cost_unavailable_reason: string | null;
  inventory_turnover: number | null;
  trajectory: {
    date: string;
    inventory: Distribution;
    demand: Distribution;
    mean_replenishment_received: number;
    mean_order_quantity: number;
    inventory_position_mean: number;
  }[];
  assumptions: string[];
}
export interface PolicyRow extends Simulation {
  policy: string;
  target_service_level: number;
  safety_stock: number;
  reorder_point: number;
  feasible: boolean;
}
export interface PolicyComparison {
  objective: string;
  minimum_fill_rate: number;
  recommended_policy: string | null;
  recommendation_reason: string;
  service_level_comparison: PolicyRow[];
  policies: PolicyRow[];
  notes: string[];
}
export interface InventoryScenario {
  baseline: { recommendation: InventoryPlan; simulation: Simulation };
  scenario: { recommendation: InventoryPlan; simulation: Simulation };
  note: string;
}
export interface Portfolio {
  series_count: number;
  total_inventory_value: number | null;
  high_risk_series: number;
  below_reorder_point: number;
  expedite_needed?: number;
  plans_requiring_recalculation?: number;
  total_recommended_order_quantity: number | null;
  average_target_service_level: number | null;
  fill_rate: number | null;
  expected_holding_cost: number | null;
  expected_stockout_cost: number | null;
  expected_total_cost: number | null;
  simulated_series_count: number;
  abc_distribution: Record<string, number>;
  currency: string | null;
  notes: string[];
}
export interface Segmentation {
  items: {
    sku_id: string;
    location_id: string;
    annual_consumption_value: number | null;
    cv: number | null;
    abc_class: string | null;
    xyz_class: string | null;
    matrix: string | null;
  }[];
  abc_distribution: Record<string, number>;
  matrix_distribution: Record<string, number>;
  notes: string[];
  excluded_from_abc: number;
}
