// Data contract between the Python exporter (src/export/export_web.py, api/server.py) and the web app.
// All money in CHF unless the name says eur. Energy in MWh, power in MW, prices in EUR/MWh.
// Times: `hour` labels are Swiss local clock ("00:00" … "23:00"; on the autumn clock change
// the repeated hour is labelled "02:00" twice, told apart by `utc`).

export type Split = "val" | "test";
export type Option = "buy" | "buy_and_store" | "use_storage_and_buy" | "use_storage";

export interface BatterySettings {
  power_mw: number;
  capacity_mwh: number;
  soc_min_frac: number;
  soc_max_frac: number;
  soc_start_frac: number;
  round_trip_efficiency: number;
  max_cycles_per_day: number;
  wear_cost_eur_per_mwh: number;
  allow_sell: boolean;
}

export interface Meta {
  generated_at: string; // ISO
  company: string; // "Limmat Energie AG"
  forecast_time_local: string; // "10:00"
  gate_closure_local: string; // "11:00"
  battery: BatterySettings; // defaults from config.yaml
  imbalance: { shortage_price_factor: number; surplus_price_factor: number };
  decision: { description: string; plan_resolution: string; charge_limit_factor: number };
  demand_source: string; // "ml" | "standin"
  price_source: string;
  days: { date: string; split: Split; weekday: string; is_holiday: boolean; is_weekend: boolean; hours: number }[];
  block_labels: string[]; // ["00–04", …]
}

export interface BlockRow {
  block: number; // 0..5
  label: string; // "00–04"
  hours: number; // 3 | 4 | 5
  demand_fc_mw: number;
  demand_q10_mw: number | null;
  demand_q90_mw: number | null;
  demand_actual_mw: number;
  demand_naive_mw: number;
  price_fc: number;
  price_q10: number | null;
  price_q90: number | null;
  price_actual: number;
  price_naive: number;
  buy_mwh: number; // planned purchase at the auction (demand bid + charge bid)
  charge_mwh: number;
  discharge_mwh: number;
  sell_mwh: number;
  soc_end_mwh: number; // planned charge level at the end of the block
  option: Option;
  charge_limit_eur_mwh: number | null;
}

export interface HourRow {
  utc: string; // ISO start of hour
  hour: string; // "17:00"
  block: number;
  demand_fc_mw: number; // forecast need of the hour
  demand_actual_mw: number;
  price_fc: number | null; // hourly price forecast used for planning (block forecast + hourly shape)
  price_actual: number;
  demand_bid_mwh: number;
  charge_bid_mwh: number;
  charge_limit_eur_mwh: number | null;
  planned_discharge_mwh: number;
  // settlement with actuals
  charge_cleared_mwh: number;
  charge_actual_mwh: number;
  discharge_actual_mwh: number;
  soc_mwh: number; // actual charge level at the end of the hour
  shortage_mwh: number;
  surplus_mwh: number;
  da_cost_chf: number;
  imbalance_cost_chf: number; // full settlement of the gap
  imbalance_penalty_chf: number; // only the extra paid versus the auction price
  wear_cost_chf: number;
}

export interface BidRow {
  hour: string;
  utc: string;
  block: number;
  bid_type: "demand" | "charge";
  volume_mwh: number;
  limit_price_eur_mwh: number | null; // null = buy at any price
}

export interface DaySummary {
  soc_start_mwh: number;
  soc_end_mwh: number; // actual, after settlement
  energy_to_buy_mwh: number; // planned
  charged_mwh: number; // planned
  discharged_mwh: number; // planned
  cycles: number;
  expected_cost_chf: number; // plan valued at forecast prices
  expected_battery_saving_chf: number; // vs same forecasts without battery
  realised_cost_chf: number; // total after settlement (auction + imbalance + wear)
  realised_battery_saving_chf: number; // vs ML forecasts without battery, settled
  realised_saving_vs_baseline_chf: number; // vs naive forecast, no battery, settled
  baseline_cost_chf: number;
  imbalance_penalty_chf: number;
  imbalance_cost_chf: number;
  wear_cost_chf: number;
  share_charge_cleared: number | null; // by volume, null if no charge bid
  eurchf: number;
}

export interface DayPlan {
  date: string;
  split: Split | "custom";
  weekday: string;
  is_holiday: boolean;
  holiday_name: string | null;
  event_name: string | null;
  battery: BatterySettings;
  blocks: BlockRow[]; // always 6
  hours: HourRow[]; // 23 | 24 | 25
  bids: BidRow[];
  summary: DaySummary;
}

export interface StrategyRow {
  key: string; // e.g. "ml_battery"
  name: string; // readable
  note: string; // one plain sentence
  kind: "baseline" | "product" | "reference" | "ceiling";
  total_cost_chf: number;
  saving_vs_baseline_chf: number; // inventory-adjusted
  saving_ci_low_chf: number | null;
  saving_ci_high_chf: number | null;
  imbalance_penalty_chf: number;
  wear_cost_chf: number;
  cycles: number;
  pct_of_ceiling: number | null;
}

export interface BacktestSplit {
  split: "test" | "val" | "rolling";
  label: string; // "October 2026 (test)"
  out_of_sample: boolean;
  days: number;
  strategies: StrategyRow[];
  decomposition: {
    total_saving_chf: number;
    demand_forecast_part_chf: number;
    battery_part_chf: number;
    block_default_battery_part_chf: number;
    tuning_and_shaping_part_chf: number;
    ceiling_total_saving_chf: number;
    ceiling_battery_value_chf: number;
    pct_ceiling_captured_total: number;
    pct_ceiling_battery_value_captured: number;
    finer_dispatch_part_chf: number | null;
    interday_flexibility_part_chf: number | null;
  };
  ci: { independent_low: number; independent_high: number; block_low: number; block_high: number; lag1_autocorr: number } | null;
  // cumulative saving vs baseline per day, one series per strategy key
  cumulative: { dates: string[]; series: { key: string; name: string; values: number[] }[] };
  // daily saving of the product split in two parts
  daily: { date: string; demand_part_chf: number; battery_part_chf: number }[];
}

export interface Backtest {
  splits: BacktestSplit[];
  battery_size: { power_mw: number; capacity_mwh: number; ml_battery_value_chf: number; ceiling_battery_value_chf: number }[];
  price_error: {
    points: { mae_eur_mwh: number; lost_chf: number }[]; // noise experiment, mean per noise level
    slope_chf_per_eur: number;
    ml: { mae_eur_mwh: number; lost_chf: number };
    naive: { mae_eur_mwh: number; lost_chf: number };
  };
  imbalance: { shortage_factor: number; surplus_factor: number; total_saving_chf: number; demand_part_chf: number; battery_part_chf: number }[];
}

export interface LadderRow {
  model: "naive" | "linear" | "rf" | "gbm" | "best";
  name: string;
  val_mae: number;
  test_mae: number;
  test_ci_low: number;
  test_ci_high: number;
  test_pct: number; // MAPE (demand) or sMAPE (price), %
  rolling_mae: number | null;
}

export interface ModelInfo {
  target: "demand" | "price";
  unit: string; // "MW" | "EUR/MWh"
  pct_metric: "MAPE" | "sMAPE";
  best_description: string; // one or two plain sentences
  ladder: LadderRow[];
  by_block: { block: number; label: string; best_mae: number; naive_mae: number }[]; // test month
  importance: { feature: string; label: string; value: number }[]; // top 15, plain-language label
  groups: { group: string; value: number }[];
  test_series: { date: string; block: number; actual: number; best: number; naive: number; q10: number | null; q90: number | null }[]; // 186 rows
}

export interface Drivers {
  temp_demand: { block: number; label: string; points: { temp_c: number; demand_mw: number; n: number }[] }[]; // working days, binned by 2 °C, 2024–2026
  radiation_demand: { radiation_wm2: number; demand_mw: number; n: number }[]; // 12–16 block, working days, Apr–Sep, binned
  profile: { daytype: "Working day" | "Saturday" | "Sunday" | "Public holiday"; hours: number[]; demand_mw: number[] }[]; // mean hourly profile, last 12 months
  ev: { year: number; ev_count: number; night_demand_mw: number }[]; // 00–04 block yearly mean
  street_parade: { label: string; hours: number[]; demand_mw: number[] }[]; // parade day 2026 vs mean of nearby Saturdays
  school_holiday: { label: string; hours: number[]; demand_mw: number[] }[]; // autumn holiday weekdays vs other October weekdays (2026)
  price_heatmap: { months: string[]; blocks: string[]; values: number[][] }; // [month][block] mean price last 24 months
  wind_price: { wind_bin: string; price_vs_recent_eur: number; n: number }[]; // CH price minus its 4-week mean by German wind forecast bin
  gas_price: { month: string; gas_eur_mwh: number; price_eur_mwh: number }[]; // monthly means 2019–2026
  negative_hours: { year: number; hours: number }[]; // CH hours with price < 0
}

export interface Method {
  sources: { input: string; source: string; step: string; note: string }[];
  time_rules: { input: string; known: string }[];
  limitations: { title: string; text: string }[];
  reviews: { phase: string; finding: string; decision: string }[];
}

// Live API (api/server.py)
export interface PlanRequest { date: string; battery: BatterySettings }
export interface MonthRequest { battery: BatterySettings }
export interface MonthResult {
  days: number;
  baseline_cost_chf: number;
  product_cost_chf: number;
  no_battery_cost_chf: number;
  ceiling_cost_chf: number;
  saving_vs_baseline_chf: number;
  battery_value_chf: number;
  ceiling_battery_value_chf: number;
  cycles: number;
}
