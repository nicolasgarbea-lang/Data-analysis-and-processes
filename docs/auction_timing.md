# Day-ahead auction timing (checked 19 Nov 2026, agent D4)

## Findings

| Market | Order book closes (gate closure) | Results published | Source |
|---|---|---|---|
| **Switzerland (CH), EPEX SPOT local auction** | **11:00 CET/CEST on D−1** | from **~11:10 CET** | EPEX SPOT trading brochures 2020, 2021, July 2024, Dec 2024 ("CH: the order book closes one day before delivery at 11:00"; "Results are published as soon as possible from 11:10"); EEX Transparency glossary ("closes daily at 11 am (CET/CEST)") |
| DE-LU, FR, AT, IT-North (SDAC, EU coupled auction) | **12:00 CET/CEST on D−1** | preliminary from **12:45**, final ~**12:57–13:01 CET** | EPEX "Day-Ahead MRC Processes (02.07.2019)" (publication never before 12:45, final 12:57); Nord Pool / GME notes on new operational timings from 17 Jun 2021 (12:42 → 12:45); ENTSO-E MESC Feb 2024 slide (final results 12:58–13:01); SDAC 15-min MTU go-live kept GCT 12:00 (from 1 Oct 2025) |

- Switzerland is **not** part of SDAC (no EU electricity agreement); it runs a separate local auction at EPEX SPOT
  that closes one hour before the coupled auction. This was already the set-up in 2011 (a Nord Pool exchange
  message from Oct 2011 mentions the Swiss auction normally at 11:10), and every EPEX brochure we found for
  2020–2024 states 11:00. We found **no evidence of a change during 2019–2026**, so we treat 11:00 as valid for
  the whole data period. Incidents (e.g. delayed/decoupled sessions such as 25 Jun 2024 partial decoupling)
  can shift times on single days; we ignore these.
- `config.yaml` already uses `gate_closure_local: "11:00"` and `forecast_time_local: "10:00"` – consistent.

## Consequence for our features (forecast at 10:00 Europe/Zurich on day D, delivery D+1)

- **CH price for D+1**: not known (auction closes 11:00 on D) – it is the target.
- **DE-LU / FR / AT / IT-North prices for D+1**: **NOT known** (their auction closes 12:00 on D and results come at
  ~12:45–13:00 on D, i.e. after our forecast time and even after the Swiss gate closure).
- **Neighbour prices for delivery day D (all 24 h)**: known – they were published ~12:45–13:00 on D−1.
- So the feature builder may use neighbour prices with `timestamp_utc` < start of local day D+1 only; the
  safe rule is: hourly price for delivery hour t is known from (local date of t − 1 day) 13:00 Europe/Zurich.

## Other publication times used by D4 tables (column `available_from_utc`)

| Table | Value known from (Europe/Zurich) | Basis |
|---|---|---|
| price_neighbours_hourly | delivery day − 1, 13:00 | SDAC final results ~12:57–13:01 |
| gas_ttf_daily | trading day 18:00 | ICE Endex settlement ~16:30–17:30 CET; Yahoo close |
| co2_eua_daily | auction day 12:00 | EEX auction window closes 11:00, results within 15 min |
| eurchf_daily | date 16:00 | ECB reference rate published ~16:00 CET |
| reservoir_weekly | Monday date + 3 days, 23:59 (Thursday end of day) | federal energy dashboard states Thursday publication; file Last-Modified Tue 17 Nov 2026 15:22 CET for the Sunday-15-Nov value |
| de_forecasts_hourly | **unverified** (flag column); legal deadlines: load D−1 10:00 CET, wind/solar D−1 18:00 CET | EU Transparency Regulation 543/2013 Art. 6, 14 (https://eur-lex.europa.eu/eli/reg/2013/543/oj) |

## Sources
- EPEX SPOT trading brochure Dec 2024: https://epexspot.com/sites/default/files/2024-12/_Trading%20brochure%202024%20December%20%281%29.pdf
- EPEX SPOT trading brochure Jul 2024: https://www.epexspot.com/sites/default/files/2024-07/Trading%20brochure%20July%202024.pdf
- EPEX SPOT trading brochure Mar 2021: https://www.epexspot.com/sites/default/files/download_center_files/21-03-09_Trading%20Brochure.pdf
- EPEX SPOT trading brochure Jan 2020: https://www.epexspot.com/sites/default/files/download_center_files/20-01-24_TradingBrochure.pdf
- EPEX SPOT Day-Ahead MRC processes (2019): https://www.epexspot.com/sites/default/files/download_center_files/Day-Ahead%20MRC%20Processes%20(02.07.2019).pdf
- EEX Transparency glossary (prices): https://eex-transparency.com/service/glossary/prices
- Nord Pool exchange message 26 May 2021 (new operational timings from 17 Jun 2021): https://www.nordpoolgroup.com/en/message-center-container/newsroom/exchange-message-list/2021/q2/26-may-2021-starting-with-17-june-2021-new-operational-timings-to-be-applied-for-daily--market-coupling-process
- GME communication on new operational timings: https://gme.mercatoelettrico.org/Portals/0/Documents/en-US/20210526_Comsnotenewoperationaltimings.pdf
- ENTSO-E MESC 28 Feb 2024, update on SDAC/SIDC: https://eepublicdownloads.blob.core.windows.net/public-cdn-container/clean-documents/Network%20codes%20documents/MESC/2024/240228_MESC_TOP_3.3_Update_on_SDAC___SIDC.pdf
- Nord Pool 15-min MTU go-live (GCT stays 12:00): https://support.nordpoolgroup.com/support/solutions/articles/8000121859-about-sdac-15-minute-member-test
- Nord Pool message No 58/2011 (Swiss auction 11:10): https://nordpoolgroup.com/en/message-center-container/newsroom/exchange-message-list/2011/Q4/No-582011---
- EPEX partial decoupling statement 26 Jun 2024: https://www.epexspot.com/sites/default/files/download_center_files/2024-06-26_EPEXSPOT_Statement%20on%20partial%20decoupling_Final_0.pdf
- BFE dataset (Sunday 24h): https://ckan.opendata.swiss/perma/ogd17@bundesamt-fur-energie-bfe
