"""Default model inputs for the demand and price models, and weather-variant maps.

Rules for the default lists:
* hybrid weather columns only (forecast from 2024-01-21, observed before - documented limitation),
* no `*_obs` (oracle weather of the delivery day), no `actual_*`, no `unverified_*`, no targets.

To switch the weather variant of a model, rename/replace columns with the maps below:
* ORACLE_WEATHER_MAP   hybrid -> observed weather of the delivery day (perfect-weather benchmark)
* FORECAST_WEATHER_MAP hybrid -> ICON forecast only (NaN before 2024-01-21)
* JMA_WEATHER_MAP      hybrid -> JMA forecast (real forecasts back to 2019; no radiation/sunshine)

`eu_*` columns (European weather forecasts) are added to PRICE_FEATURES automatically if
`features.parquet` contains them.
"""
from __future__ import annotations

from src.config import path

TARGET_DEMAND = "demand_mw"
TARGET_PRICE = "price_eur_mwh"

CALENDAR_FEATURES = [
    "block", "weekday", "month", "day_of_year", "week_of_year", "year_frac", "sin_doy", "cos_doy",
    "is_weekend", "is_holiday", "is_half_holiday", "is_bridge_day", "is_school_holiday",
    "school_holiday_type", "is_christmas_period", "days_to_next_holiday", "days_since_last_holiday",
    "is_holiday_prev_day", "is_holiday_next_day", "lag2d_was_holiday", "lag7d_was_holiday",
    "lag2d_is_weekend", "is_working_day", "is_dst_change_day", "hours_in_block", "daylight_hours",
    "event_size", "n_events", "home_game", "kickoff_hour_local", "covid_stringency",
]

DEMAND_LAG_FEATURES = [
    "demand_lag_2d_same_block", "demand_lag_3d_same_block", "demand_lag_7d_same_block",
    "demand_lag_8d_same_block", "demand_lag_14d_same_block", "demand_lag_21d_same_block",
    "demand_lag_28d_same_block", "demand_lag_364d_same_block", "demand_mean_same_block_same_weekday_4w",
    "demand_day_mean_lag_2d", "demand_day_mean_lag_7d", "demand_mean_last_7d", "demand_mean_last_28d",
    "demand_day_max_lag_2d", "demand_day_min_lag_2d",
    *[f"demand_dm1_block_{j}" for j in range(6)],
    "demand_trend_7d", "expected_demand_proxy",
]

# hybrid weather of the delivery block / day (model inputs)
WEATHER_FEATURES = [
    "temp_c", "temp_c_sq", "heating_degree", "cooling_degree", "radiation_wm2", "sunshine_min",
    "wind_ms", "precip_mm", "cloud_pct", "humidity_pct",
    "temp_day_mean", "temp_day_min", "temp_day_max", "radiation_day_mean", "sunshine_day_sum",
    "weather_is_forecast",
]
PAST_WEATHER_FEATURES = [
    "temp_obs_mean_dm1", "temp_obs_mean_last_3d", "temp_obs_mean_last_7d",
    "temp_obs_same_block_lag_2d", "radiation_obs_same_block_lag_2d", "temp_obs_last_24h_mean",
    "temp_change_fc_vs_dm1",
]
SOLAR_EV_FEATURES = [
    "solar_ch_mw_lag_2d_same_block", "solar_ch_day_mean_lag_2d",
    "ev_count_city", "charging_kw_zh", "stations_zh_count",
]

PRICE_LAG_FEATURES = [
    "price_lag_1d_same_block", "price_lag_2d_same_block", "price_lag_7d_same_block",
    "price_lag_14d_same_block", "price_mean_day_D", "price_min_day_D", "price_max_day_D",
    "price_spread_day_D", "price_std_day_D", *[f"price_dD_block_{j}" for j in range(6)],
    "price_mean_last_7d", "price_mean_last_28d", "price_std_last_7d",
    "price_block_vs_day_ratio_last_7d", "price_neg_hours_day_D", "price_neg_hours_last_7d",
    "price_lag_7d_day_mean",
]
NEIGHBOUR_FEATURES = [
    *[f"price_{c}_day_D_same_block" for c in ("de", "fr", "at", "it")],
    *[f"price_{c}_mean_day_D" for c in ("de", "fr", "at", "it")],
    *[f"spread_ch_{c}_day_D" for c in ("de", "fr", "at", "it")],
    *[f"spread_ch_{c}_mean_7d" for c in ("de", "fr", "at", "it")],
    "price_de_lag_7d_same_block",
]
FUEL_HYDRO_FEATURES = [
    "gas_ttf_d_1", "gas_ttf_change_5d", "gas_ttf_mean_20d", "co2_eua_d_1", "co2_staleness_days",
    "eurchf_d_1", "clean_gas_cost", "reservoir_fill_pct", "reservoir_vs_median_pct",
    "reservoir_change_1w",
]
SWISS_SYSTEM_FEATURES = [
    "swiss_load_lag_2d_same_block", "swiss_load_day_mean_lag_2d", "swiss_nuclear_mw_lag_2d",
    "swiss_hydro_ror_mw_lag_2d", "swiss_hydro_storage_mw_lag_2d", "swiss_hydro_pumped_mw_lag_2d",
    "swiss_solar_mw_lag_2d_same_block", "swiss_residual_load_lag_2d_same_block",
    "swiss_net_import_mw_lag_2d",
]


def _eu_columns() -> list[str]:
    """eu_* columns present in features.parquet (empty if the file or columns are missing)."""
    f = path("features")
    if not f.exists():
        return []
    try:
        import pyarrow.parquet as pq
        return [c for c in pq.read_schema(f).names if c.startswith("eu_")]
    except Exception:  # unreadable file -> behave as if no eu columns
        return []


EU_WEATHER_FEATURES = _eu_columns()

DEMAND_FEATURES = (CALENDAR_FEATURES + DEMAND_LAG_FEATURES + WEATHER_FEATURES
                   + PAST_WEATHER_FEATURES + SOLAR_EV_FEATURES)

PRICE_FEATURES = (CALENDAR_FEATURES + PRICE_LAG_FEATURES + NEIGHBOUR_FEATURES + FUEL_HYDRO_FEATURES
                  + SWISS_SYSTEM_FEATURES + WEATHER_FEATURES + PAST_WEATHER_FEATURES
                  + ["demand_lag_2d_same_block", "demand_day_mean_lag_2d", "demand_lag_7d_same_block",
                     "expected_demand_proxy", "solar_ch_mw_lag_2d_same_block", "solar_ch_day_mean_lag_2d"]
                  + EU_WEATHER_FEATURES)

# ---- weather variant maps (hybrid name -> alternative column) ----
_DERIVED_TEMP = ["temp_c", "temp_c_sq", "heating_degree", "cooling_degree", "temp_change_fc_vs_dm1",
                 "temp_day_mean", "temp_day_min", "temp_day_max"]
_OBS_AND_ICON = _DERIVED_TEMP + ["radiation_wm2", "sunshine_min", "wind_ms", "precip_mm", "humidity_pct",
                                 "radiation_day_mean", "sunshine_day_sum"]

ORACLE_WEATHER_MAP = {h: f"{h}_obs" for h in _OBS_AND_ICON}                     # no observed cloud cover
FORECAST_WEATHER_MAP = {h: f"{h}_fc" for h in _OBS_AND_ICON + ["cloud_pct"]}
JMA_WEATHER_MAP = {h: f"{h}_fc_jma" for h in _DERIVED_TEMP + ["wind_ms", "precip_mm", "cloud_pct", "humidity_pct"]}

# columns that start late (NaN early in the table) - impute or drop rows before these dates
LATE_START_FEATURES = {
    "demand_lag_364d_same_block": "2020-01-01",
    "charging_kw_zh": "2020-12-15",
    "stations_zh_count": "2020-12-15",
}
