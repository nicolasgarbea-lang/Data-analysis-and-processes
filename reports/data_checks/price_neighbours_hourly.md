# Data check: price_neighbours_hourly

- file: `data/processed/price_neighbours_hourly.parquet`
- rows: 69095 (hourly, UTC, interval start)
- first: 2019-01-01 00:00:00+00:00  last: 2026-11-18 22:00:00+00:00
- duplicates removed: overlapping chunk timestamps dropped (keep last); 15-min averaged to hourly
- raw resolution: hourly until 2025-09-30 22:00 UTC, 15-min from 2025-09-30 22:00 UTC (SDAC 15-min MTU, delivery day 1 Oct 2025) → mean of 4 quarter-hours
- publication: delivery day D values known from D-1 ~13:00 Europe/Zurich (SDAC results); at forecast time D 10:00 only delivery hours up to end of local day D may be used
- price_de_eur_mwh: missing 0.000% in 2019-01-01→2026-11-01 (0 h), min -500.0, max 936.3, mean 96.9
- price_fr_eur_mwh: missing 0.000% in 2019-01-01→2026-11-01 (0 h), min -496.9, max 2987.8, mean 95.5
- price_at_eur_mwh: missing 0.000% in 2019-01-01→2026-11-01 (0 h), min -500.0, max 1965.9, mean 106.5
- price_it_north_eur_mwh: missing 0.000% in 2019-01-01→2026-11-01 (0 h), min 0.0, max 871.0, mean 128.0
