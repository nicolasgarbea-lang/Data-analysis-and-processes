# The pitch

**In one line:** every morning at 10:00 the system tells a Zurich grid operator how much electricity to buy for
tomorrow, when to charge and empty its battery, and at what price to bid. Tested on October 2026, it cut the bill by
about CHF 226,000 against a simple rule.

*Everything here is a simulation: the company and the battery are fictional, the demand and price data are real.
Full details are in [reports/report.md](reports/report.md); a 12-slide outline is in
[reports/slide_outline.md](reports/slide_outline.md).*

## The job

*Limmat Energie AG* (fictional) supplies the city of Zurich and must buy tomorrow's electricity at the Swiss
day-ahead auction, which closes at 11:00. At that moment it knows neither tomorrow's demand nor tomorrow's price. If
it buys the wrong amount, it pays a penalty. It also owns a 20 MW / 40 MWh battery that can buy cheap and use later.

The system does four things for each of tomorrow's six 4-hour blocks:

1. Forecasts Zurich demand.
2. Forecasts the Swiss price.
3. Plans the battery (buy, buy and store, use storage and buy, use storage).
4. Turns the plan into hourly auction bids.

A backtest then settles those bids against what really happened.

## The data

All data is real and public, covering 2019 to October 2026:

| What | Source |
|---|---|
| Zurich demand, every 15 minutes | ewz / Stadt Zürich open data |
| Swiss, German, French, Austrian, Italian prices | Energy-Charts |
| Weather observed, and real archived forecasts | MeteoSwiss, Open-Meteo |
| Weather forecasts for Germany, France, Italy | Open-Meteo (added for the price model) |
| Gas, CO₂, EUR/CHF, reservoir levels | Yahoo (unofficial), EEX, ECB, BFE |
| Holidays, school holidays, 183 confirmed event dates, football, EVs | Stadt Zürich, BFE, own event table |

The strict rule throughout: each forecast may only use what was known at 10:00 the day before. An automated test
checks this, and an independent reviewer recomputed 966 feature values by hand; all matched.

## The models

Both follow the required ladder, chosen on September and tested on October.

| Model | Demand error (MW) | Price error (EUR/MWh) |
|---|---|---|
| Naive (same block last week) | 9.58 | 23.47 |
| Linear regression | 4.54 | 12.77 |
| Random forest | 5.87 | 16.73 |
| Gradient boosting | 4.15 | 16.82 |
| **Best** | **3.34** (1.11 %) | **10.99** |

- **Demand, best model:** gradient boosting that predicts the *change* versus two days earlier rather than the
  level, averaged over five runs and blended with a linear model. Predicting the change was the biggest single gain.
- **Price, best model:** the same idea (change versus today's known price), with recent days weighted more, blended
  with a linear model and refitted weekly.
- **What drives demand:** past demand, weekday, holidays and weather. EVs and events added nothing measurable, and
  the report says so.

## The decision

A small optimisation model plans the battery under its limits (power, capacity, 90 % efficiency, one cycle a day,
wear cost). Demand is bid at any price, because the city must be supplied; battery charging is bid with a price
limit.

## The result (October 2026)

- **Total saving:** CHF 226,499, about 0.5 % of a CHF 45.7m monthly bill.
- **From the demand forecast:** CHF 181,033, through fewer penalties.
- **From the battery:** CHF 45,466, which is 76 % of what perfect foresight would earn.
- **Over the previous 12 months:** about CHF 2.38m. This is a robustness figure, not a clean test, because the
  decision rules were tuned on that period.

The main insight: a good demand forecast is worth roughly four times the battery.

## Improvements beyond the original plan

- **Hourly battery schedule:** a 2-hour battery is wasted on 4-hour blocks, so the battery is scheduled per hour
  using last week's price shape. This added about CHF 18,000 in October.
- **European weather forecasts** for the price model.
- **Independent reviews** by a different AI model after every phase, which caught real problems: a benchmark that
  was not a true upper limit, a solver tolerance that was too loose, and a one-day training overlap. All were fixed
  and are logged in [docs/review_log.md](docs/review_log.md).
- **Robustness evidence** beyond one month: a rolling 11-month backtest, confidence intervals and significance
  tests.

## What to say when challenged

- **The imbalance penalty is assumed** (±20 % of the price), and it drives about 80 % of the saving. At ±10 % the
  total falls to CHF 136,000; the battery part stays at about CHF 45,000.
- **One test month** gives a wide interval: CHF 130,000 to 354,000 on the cautious estimate.
- **The battery and company are fictional**, and before 2024 the models trained on observed weather because no
  forecast archive exists.
