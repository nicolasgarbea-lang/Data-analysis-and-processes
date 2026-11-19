# Check: swiss_power_hourly.parquet (Energy-Charts public_power, country=ch)

- rows: 69106 hourly rows
- first / last timestamp_utc: 2018-12-31 23:00:00+00:00 / 2026-11-19 08:00:00+00:00
- duplicate timestamps: 0
- source series names: Cross border electricity trading, Hydro Run-of-River, Hydro pumped storage, Hydro water reservoir, Load, Nuclear, Others, Renewable share of generation, Renewable share of load, Residual load, Solar, Wind onshore (the 'share' series are % and were dropped)
- load_bad hours: 130 (0.188%); before 2026-11-01: 48
- solar_bad hours: 1; wind_bad hours: 2 (['2021-03-31 22:00:00+00:00', '2026-11-19 08:00:00+00:00'])
- load_bad rule: missing, ≤ 0, constant ≥ 6 h, < 50 % or > 200 % of the centred 7-day median, or on/after 2026-11-16 (known Energy-Charts glitch); a local day with ≥ 6 bad hours is flagged completely

## Missing share and constant stretches per column

| column | % missing | hours with value 0 | hours in constant runs ≥ 6 h (value ≠ 0) | min | max |
|---|---|---|---|---|---|
| cross_border_trading_mw | 0.000% | 2 | 14 | -8812.9 | 6129.1 |
| nuclear_mw | 0.000% | 1 | 0 | 0.0 | 3333.1 |
| hydro_run_of_river_mw | 0.000% | 0 | 0 | 331.5 | 4682.1 |
| hydro_water_reservoir_mw | 0.000% | 0 | 0 | 55.8 | 7480.5 |
| hydro_pumped_storage_mw | 0.000% | 11 | 6 | 0.0 | 2833.1 |
| others_mw | 0.000% | 0 | 69106 | 337.5 | 487.5 |
| wind_onshore_mw | 0.001% | 1051 | 25 | 0.0 | 11000.0 |
| solar_mw | 0.001% | 31427 | 0 | 0.0 | 6630.1 |
| load_mw | 0.001% | 0 | 31 | 662.3 | 30073.3 |
| residual_load_mw | 0.001% | 0 | 0 | -4315.1 | 29942.6 |

## Load problems (runs of load_bad hours)

| first | last | hours |
|---|---|---|
| 2023-02-16 23:00:00+00:00 | 2023-02-17 22:00:00+00:00 | 24 |
| 2024-12-04 23:00:00+00:00 | 2024-12-05 22:00:00+00:00 | 24 |
| 2026-11-15 23:00:00+00:00 | 2026-11-19 08:00:00+00:00 | 82 |

## Solar problems (runs of solar_bad hours)

| first | last | hours |
|---|---|---|
| 2026-11-19 08:00:00+00:00 | 2026-11-19 08:00:00+00:00 | 1 |

## Yearly means (MW, local calendar year)

| year | cross_border_trading_mw | nuclear_mw | hydro_run_of_river_mw | hydro_water_reservoir_mw | hydro_pumped_storage_mw | others_mw | wind_onshore_mw | solar_mw | load_mw | residual_load_mw |
|---|---|---|---|---|---|---|---|---|---|---|
| 2019 | -558 | 2886 | 2021 | 2232 | 377 | 426 | 17 | 249 | 7492 | 7227 |
| 2020 | -539 | 2617 | 2009 | 2209 | 406 | 443 | 17 | 306 | 7374 | 7051 |
| 2021 | 450 | 2115 | 1936 | 2194 | 379 | 436 | 17 | 338 | 7691 | 7336 |
| 2022 | 562 | 2638 | 1768 | 1548 | 508 | 421 | 17 | 464 | 7751 | 7270 |
| 2023 | -614 | 2664 | 1997 | 2168 | 491 | 405 | 19 | 561 | 7574 | 6994 |
| 2024 | -1607 | 2616 | 2209 | 2855 | 439 | 410 | 19 | 679 | 7588 | 6890 |
| 2025 | -28 | 2098 | 1864 | 1939 | 476 | 405 | 18 | 907 | 7710 | 6785 |
| 2026 | 114 | 2241 | 1691 | 1355 | 447 | 412 | 17 | 1224 | 7934 | 6693 |

## Daily load and solar from 2026-11-01 (UTC days)

| day | load mean | load min | load max | load n | solar mean | solar max |
|---|---|---|---|---|---|---|
| 2026-11-01 | 7477 | 6826 | 7962 | 24 | 667 | 2756 |
| 2026-11-02 | 8602 | 7098 | 11160 | 24 | 542 | 2342 |
| 2026-11-03 | 8861 | 5628 | 11302 | 24 | 475 | 2055 |
| 2026-11-04 | 8871 | 6843 | 10210 | 24 | 529 | 2170 |
| 2026-11-05 | 8848 | 6968 | 10081 | 24 | 629 | 2708 |
| 2026-11-06 | 8568 | 5324 | 11532 | 24 | 237 | 1015 |
| 2026-11-07 | 7880 | 5618 | 11348 | 24 | 383 | 1754 |
| 2026-11-08 | 7531 | 6869 | 8517 | 24 | 642 | 2866 |
| 2026-11-09 | 8666 | 7001 | 10289 | 24 | 296 | 1242 |
| 2026-11-10 | 8524 | 4494 | 11175 | 24 | 479 | 2140 |
| 2026-11-11 | 8888 | 7534 | 10019 | 24 | 258 | 1036 |
| 2026-11-12 | 8623 | 5886 | 12095 | 24 | 163 | 787 |
| 2026-11-13 | 9190 | 6264 | 13072 | 24 | 550 | 2453 |
| 2026-11-14 | 8292 | 6568 | 10681 | 24 | 617 | 2660 |
| 2026-11-15 | 8286 | 7156 | 11227 | 24 | 450 | 2217 |
| 2026-11-16 | 9051 | 5088 | 25049 | 24 | 371 | 1958 |
| 2026-11-17 | 8569 | 662 | 24426 | 24 | 200 | 1106 |
| 2026-11-18 | 26862 | 23664 | 29655 | 24 | 447 | 2080 |
| 2026-11-19 | 27232 | 24631 | 30073 | 8 | 12 | 94 |
