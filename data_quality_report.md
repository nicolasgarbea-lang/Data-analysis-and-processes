# Data quality report: hotels.csv
Generated 2026-11-12 · 119,390 rows × 32 columns · Dictionary: none found in the project

This is an audit only. `data/hotels.csv` was read, never changed. Fixes below are suggestions.

## Assumptions
- **File:** `data/hotels.csv`, one header line, read with `pd.read_csv` and its default settings.
- **Row numbers** are line numbers in the CSV file: the header is line 1 and the first booking is line 2 (pandas index + 2).
- **Missing values:** the file writes missing values as the text `NULL` (country, agent, company) and `NA` (children). pandas reads both as missing.
- **No data dictionary** for this file exists in the project. (`FeatureDescription.pdf` and `semantic_layer.md` in the Lecture 4 folder describe the TV data, so they weren't used.) Column meanings are taken from the column names. Where the meaning decides whether something is a problem, it is marked "Possible issue" and listed under open questions.
- **No booking ID** exists, so the check for duplicate keys isn't possible. Only fully identical rows were checked.
- **Period:** arrivals are assumed to run from 1 July 2015 to 31 August 2017, which is the range found in the data.
- **Thresholds:** text similarity of 0.80 or more for near-duplicate spellings; outliers are values more than 3 × IQR above the upper quartile (prices per hotel). Head counts, parking spaces and previous cancellations use hand-picked limits, because most values in those columns are identical and IQR doesn't work there.

## Summary
| Check | Issues found |
|---|---|
| 1 Duplicates | 1 |
| 2 Spelling and fuzzy duplicates | 1 |
| 3 Type mismatches | 2 |
| 4 Missing data and placeholder codes | 6 |
| 5 Time-order violations | 1 |
| 6 Logical inconsistencies | 5 |
| 7 Implausible values and outliers | 4 |

Checked and clean:
- **Spelling:** no values differ only by upper/lower case or spaces, and no near-duplicate spellings in the category columns.
- **Dates:** every arrival date and status date is a valid date (0 unreadable) and 0 arrivals fall outside the period.
- **Cancellation timing:** 0 cancellations are dated after arrival and 0 before the booking was made.
- **Cancellation flag:** `is_canceled` and `reservation_status` agree in every row (0 mismatches).
- **Waiting list:** 0 bookings waited longer than their lead time.
- **Week numbers:** `arrival_date_week_number` matches the arrival date in every row (0 mismatches) when weeks start on Sunday and week 1 contains 1 January.

## Issues
Sorted by how much they could distort the analysis, most important first.

| # | Check | Column | Rows affected | Example rows (file row: value) | Why it may be a problem | Suggested fix |
|---|---|---|---|---|---|---|
| 1 | Duplicates | `all columns` | 40,165 (33.6%) | 6: Resort Hotel, 1 Jul 2015, lead time 14; 7: Resort Hotel, 1 Jul 2015, lead time 14 | Possible issue. There is no booking ID, so we can't tell real separate bookings (a group booked room by room) from copies. These rows cancel at 58% vs. 26% for the rest, so keeping or dropping them changes every cancellation rate and the model. | Don't drop them blindly. Decide with the team (see question 1), then either keep all, or keep one row per group plus a new column with the group size. |
| 2 | Logical inconsistencies | `deposit_type, is_canceled` | 14,494 (12.1%) | 2135: Non Refund, cancelled, Groups, PRT; 2136: Non Refund, cancelled, Groups, PRT; 2137: Non Refund, cancelled, Groups, PRT | Possible issue. 99.4% of bookings with a non-refundable deposit are cancelled, the opposite of what a deposit should do. 97% come from Portugal and 98% are identical rows (issue 1). A model will learn "deposit = cancels", which is misleading for the deposit decision. | Treat `deposit_type` with caution: test the models with and without it, and don't read its effect as cause and effect. |
| 3 | Missing data and placeholders | `adr` | 1,959 (1.6%) | 2: adr 0, Direct; 3: adr 0, Direct; 127: adr 0, Complementary | Possible issue. A zero price may mean a free stay (680 are "Complementary") or a price that was never recorded. Zeros pull down average prices and distort price features and lost-revenue figures. | Keep zeros for Complementary bookings; for the other 1,279 rows decide whether 0 is real or missing (question 3). |
| 4 | Logical inconsistencies | `stays_in_weekend_nights, stays_in_week_nights` | 715 (0.6%) | 2: 0 + 0 nights, adr 0, Check-Out; 3: 0 + 0 nights, adr 0, Check-Out; 169: 0 + 0 nights, adr 0, Check-Out | A booking with no nights isn't a normal hotel stay; all of them have a price of 0, and 680 are marked as checked out. They add noise to both models. | Exclude them from modelling unless the hotel confirms they are real (for example day use). |
| 5 | Logical inconsistencies | `adults, children, babies` | 180 (0.2%) | 2226: 0 adults, 0 children, 0 babies, adr 0; 2411: 0 adults, 0 children, 0 babies, adr 0; 3183: 0 adults, 0 children, 0 babies, adr 0 | A booking for nobody is not a real stay; per-person features (such as price per person) would divide by zero. | Exclude these rows from modelling. |
| 6 | Missing data and placeholders | `company` | 112,593 (94.3%) | 2: NULL; 3: NULL; 4: NULL | 94% empty. "NULL" most likely means "not booked through a company", not "unknown", but the file doesn't say. As a number column it is useless for a model. | Replace with a yes/no column "booked through a company". |
| 7 | Missing data and placeholders | `agent` | 16,340 (13.7%) | 2: NULL, Direct; 3: NULL, Direct; 4: NULL, Direct | Missing values are concentrated in Corporate, Complementary, Aviation and Direct bookings (48% to 89% empty) and almost never in travel-agency bookings, so "NULL" probably means "no agent". | Treat "NULL" as its own category ("no agent") instead of dropping or filling it. |
| 8 | Type mismatches | `agent, company` | 109,630 (91.8%) | 5: agent 304.0, company NULL; 6: agent 240.0, company NULL; 7: agent 240.0, company NULL | These are ID codes, not quantities. Read as numbers (9.0, 240.0), a model would treat agent 240 as "more" than agent 9. | Convert both to text categories; group rare IDs into "other". |
| 9 | Logical inconsistencies | `is_repeated_guest, previous_bookings_not_canceled, previous_cancellations` | 1,372 (1.1%) | 13805: repeated 0, earlier stays 1, earlier cancellations 0; 13806: repeated 0, earlier stays 2, earlier cancellations 0; 13807: repeated 0, earlier stays 3, earlier cancellations 1 | Possible issue. 782 guests are "not repeated" but have earlier completed bookings; 590 are "repeated" with no earlier bookings at all. The three columns may be filled in at different times. | Don't correct the values; keep all three columns and mention the inconsistency. |
| 10 | Spelling and fuzzy duplicates | `country` | 1,279 (1.1%) | 145: CN; 165: CN; 309: CN | Possible issue. Every other country uses a 3-letter code. "CN" is probably China, which also appears as "CHN", so one country may be split in two. | If question 7 confirms it, recode "CN" to "CHN". (We leave `country` out of the models anyway.) |
| 11 | Missing data and placeholders | `meal` | 1,169 (1.0%) | 3108: Undefined, Resort Hotel; 3109: Undefined, Resort Hotel; 3110: Undefined, Resort Hotel | Possible issue. All of these are in the Resort Hotel, which almost never uses "SC" (86 rows) while the City Hotel uses it 10,564 times. "Undefined" may be the resort's way of writing "no meal". | If question 8 confirms it, merge "Undefined" into "SC". |
| 12 | Missing data and placeholders | `country` | 488 (0.4%) | 32: NULL, Resort Hotel; 4129: NULL, Resort Hotel; 7094: NULL, Resort Hotel | Small share, but 95% of the gaps are in the Resort Hotel. Only matters for descriptive charts by country. | Show as "unknown" in charts; no action needed for the models. |
| 13 | Logical inconsistencies | `adults, children, babies` | 223 (0.2%) | 40986: 0 adults, 3 children, 0 babies; 41050: 0 adults, 2 children, 0 babies; 41448: 0 adults, 2 children, 0 babies | Possible issue. Children can't book alone, but these may be extra rooms for the children of a family booked in a second room. | Keep them; build features on total guests instead of adults alone. |
| 14 | Implausible values and outliers | `adr` | 232 (0.2%) | 14971: adr -6.38 (Resort Hotel); 48517: adr 5400 (City Hotel); 111405: adr 510 (City Hotel) | A price of -6.38 is impossible and 5,400 per night (next highest: 510) is almost certainly a typing error. The other 230 are high but believable peak-season prices. | Remove or correct the two clear errors; keep the rest. |
| 15 | Implausible values and outliers | `adults, children, babies, required_car_parking_spaces` | 21 (<0.1%) | 2175: 55 adults, 0 children, 0 babies, 0 parking; 46621: 2 adults, 0 children, 10 babies, 0 parking; 29047: 2 adults, 0 children, 0 babies, 8 parking | 13 bookings have 10 to 55 adults in one room (all cancelled, probably group placeholders); 3 have 9 or 10 children or babies; 5 ask for 3 to 8 parking spaces for 2 adults. | Exclude or cap these 21 rows before modelling. |
| 16 | Implausible values and outliers | `previous_cancellations` | 180 (0.2%) | 14781: 26 previous cancellations; 14782: 26 previous cancellations; 14783: 26 previous cancellations | Possible issue. The counts follow a pattern (26 rows with 26 previous cancellations, 25 rows with 25), which looks like the group's size was counted, not one guest's own history. | Cap the column (for example at 5) or turn it into yes/no. |
| 17 | Time-order violations | `reservation_status_date` | 28 (<0.1%) | 26: Check-Out, arrival 1 Jul 2015, 7 nights, status date 2015-07-01; 315: Check-Out, arrival 12 Jul 2015, 7 nights, status date 2015-07-12; 7037: No-Show, arrival 17 Jul 2016, 7 nights, status date 2016-03-28 | 27 checked-out bookings have a check-out date 1 to 14 days earlier than arrival plus nights (guest left early, or the nights weren't updated). One no-show is dated 111 days before arrival. Matters for Model B, whose target is built from this date. | Tiny share: exclude these 28 rows when building Model B's target. |
| 18 | Type mismatches | `reservation_status_date, arrival_date_*` | 119,390 (100.0%) | 2: "2015-07-01"; arrival = 2015 / "July" / 1; 3: "2015-07-01"; arrival = 2015 / "July" / 1; 4: "2015-07-02"; arrival = 2015 / "July" / 1 | The status date is text and the arrival date is split over three columns with the month as a word. Date maths and sorting by month don't work until they are converted. All values convert cleanly. | Build one real arrival-date column and convert the status date when loading. |
| 19 | Implausible values and outliers | `stays_in_*_nights, lead_time` | 205 (0.2%) | 14040: 69 nights, lead time 126 days; 3: 0 nights, lead time 737 days; 3822: 42 nights, lead time 122 days | 24 stays are longer than 30 nights (up to 69) and 181 bookings were made more than 586 days ahead (up to 737). These look like real extremes (long-stay and contract guests), not errors. | Keep them; tree-based models handle them, for logistic regression consider capping. |
| 20 | Missing data and placeholders | `children, market_segment, distribution_channel` | 5 (<0.1%) | 14596: children 1, segment Direct, channel Undefined; 40602: children NA, segment Undefined, channel Undefined; 40669: children NA, segment Direct, channel Undefined | 5 bookings have an "Undefined" segment or channel, and 4 of those 5 also have no value for children (which makes pandas read the whole column as decimals). | Drop these 5 rows, or set the 4 missing children to 0; either way store `children` as whole numbers. |

## Code to verify each issue
Run each block from the `grouproject` folder. Each one stands alone.

### Issue 1: Identical rows
```python
import pandas as pd
df = pd.read_csv("data/hotels.csv")
mask = df.duplicated(keep=False)          # every row that has an identical twin
print(df.duplicated().sum())               # -> 31994 extra copies beyond the first of each group
print(mask.sum())   # -> 40165
print(df[mask].head(3))
```

### Issue 2: Non-refundable bookings are almost all cancelled
```python
import pandas as pd
df = pd.read_csv("data/hotels.csv")
mask = (df["deposit_type"] == "Non Refund") & (df["is_canceled"] == 1)
print((df["deposit_type"] == "Non Refund").sum())   # -> 14587 Non Refund bookings in total
print(mask.sum())   # -> 14494
print(df[mask].head(3))
```

### Issue 3: Price of zero
```python
import pandas as pd
df = pd.read_csv("data/hotels.csv")
mask = df["adr"] == 0
print(df.loc[mask, "market_segment"].value_counts())   # 680 are Complementary (free stays)
print(mask.sum())   # -> 1959
print(df[mask].head(3))
```

### Issue 4: Stays of zero nights
```python
import pandas as pd
df = pd.read_csv("data/hotels.csv")
nights = df["stays_in_weekend_nights"] + df["stays_in_week_nights"]
mask = nights == 0
print(df.loc[mask, "reservation_status"].value_counts())   # 680 of them are Check-Out
print(mask.sum())   # -> 715
print(df[mask].head(3))
```

### Issue 5: Bookings with no guests
```python
import pandas as pd
df = pd.read_csv("data/hotels.csv")
mask = (df["adults"] + df["children"].fillna(0) + df["babies"]) == 0
print(mask.sum())   # -> 180
print(df[mask].head(3))
```

### Issue 6: Company is almost always empty
```python
import pandas as pd
df = pd.read_csv("data/hotels.csv")
mask = df["company"].isna()     # the file says "NULL"; pandas reads it as missing
print(mask.sum())   # -> 112593
print(df[mask].head(3))
```

### Issue 7: Agent is often empty
```python
import pandas as pd
df = pd.read_csv("data/hotels.csv")
mask = df["agent"].isna()       # the file says "NULL"; pandas reads it as missing
print(df[mask]["market_segment"].value_counts())
print(mask.sum())   # -> 16340
print(df[mask].head(3))
```

### Issue 8: Agent and company IDs are read as decimal numbers
```python
import pandas as pd
df = pd.read_csv("data/hotels.csv")
mask = df["agent"].notna() | df["company"].notna()   # rows that carry at least one ID
print(df[["agent", "company"]].dtypes)                # -> float64, float64
print(mask.sum())   # -> 109630
print(df[mask].head(3))
```

### Issue 9: Repeated-guest flag disagrees with booking history
```python
import pandas as pd
df = pd.read_csv("data/hotels.csv")
not_repeated_but_history = (df["is_repeated_guest"] == 0) & (df["previous_bookings_not_canceled"] > 0)   # 782
repeated_but_no_history = ((df["is_repeated_guest"] == 1) & (df["previous_bookings_not_canceled"] == 0)
                           & (df["previous_cancellations"] == 0))                                          # 590
mask = not_repeated_but_history | repeated_but_no_history
print(mask.sum())   # -> 1372
print(df[mask].head(3))
```

### Issue 10: Country code "CN" next to "CHN"
```python
import pandas as pd
df = pd.read_csv("data/hotels.csv")
mask = df["country"] == "CN"
print((df["country"] == "CHN").sum())   # -> 999 rows use the 3-letter code CHN
print(mask.sum())   # -> 1279
print(df[mask].head(3))
```

### Issue 11: Meal "Undefined"
```python
import pandas as pd
df = pd.read_csv("data/hotels.csv")
mask = df["meal"] == "Undefined"
print(df[mask]["hotel"].value_counts())   # all Resort Hotel
print(mask.sum())   # -> 1169
print(df[mask].head(3))
```

### Issue 12: Missing country
```python
import pandas as pd
df = pd.read_csv("data/hotels.csv")
mask = df["country"].isna()     # the file says "NULL"
print(df[mask]["hotel"].value_counts())   # 464 Resort Hotel, 24 City Hotel
print(mask.sum())   # -> 488
print(df[mask].head(3))
```

### Issue 13: Children or babies without an adult
```python
import pandas as pd
df = pd.read_csv("data/hotels.csv")
mask = (df["adults"] == 0) & ((df["children"] > 0) | (df["babies"] > 0))
print(mask.sum())   # -> 223
print(df[mask].head(3))
```

### Issue 14: Negative and extreme prices
```python
import pandas as pd
df = pd.read_csv("data/hotels.csv")
q1 = df.groupby("hotel")["adr"].transform(lambda s: s.quantile(0.25))
q3 = df.groupby("hotel")["adr"].transform(lambda s: s.quantile(0.75))
mask = (df["adr"] < 0) | (df["adr"] > q3 + 3 * (q3 - q1))   # per hotel: above 266.40 (City), 350.00 (Resort)
print(df["adr"].min(), df["adr"].max())                     # -> -6.38 5400.0
print(mask.sum())   # -> 232
print(df[mask].head(3))
```

### Issue 15: Impossible head counts and parking spaces
```python
import pandas as pd
df = pd.read_csv("data/hotels.csv")
mask = ((df["adults"] >= 10) | (df["children"] >= 10) | (df["babies"] >= 9)
        | (df["required_car_parking_spaces"] >= 3))
print(mask.sum())   # -> 21
print(df[mask].head(3))
```

### Issue 16: Very many previous cancellations
```python
import pandas as pd
df = pd.read_csv("data/hotels.csv")
mask = df["previous_cancellations"] >= 10
print(df[mask]["previous_cancellations"].value_counts().sort_index())
print(mask.sum())   # -> 180
print(df[mask].head(3))
```

### Issue 17: Status date doesn't fit the stay
```python
import pandas as pd
df = pd.read_csv("data/hotels.csv")
arrival = pd.to_datetime(df["arrival_date_year"].astype(str) + "-" + df["arrival_date_month"] + "-"
                         + df["arrival_date_day_of_month"].astype(str), format="%Y-%B-%d")
nights = df["stays_in_weekend_nights"] + df["stays_in_week_nights"]
status = pd.to_datetime(df["reservation_status_date"])
left_early = (df["reservation_status"] == "Check-Out") & (status != arrival + pd.to_timedelta(nights, unit="D"))   # 27
no_show_wrong_day = (df["reservation_status"] == "No-Show") & (status != arrival)                                  # 1
mask = left_early | no_show_wrong_day
print(mask.sum())   # -> 28
print(df[mask].head(3))
```

### Issue 18: Dates are stored as text and in pieces
```python
import pandas as pd
df = pd.read_csv("data/hotels.csv")
mask = df["reservation_status_date"].notna()
print(df[["reservation_status_date", "arrival_date_month"]].dtypes)   # -> text, text
print(mask.sum())   # -> 119390
print(df[mask].head(3))
```

### Issue 19: Very long stays and very early bookings
```python
import pandas as pd
df = pd.read_csv("data/hotels.csv")
nights = df["stays_in_weekend_nights"] + df["stays_in_week_nights"]
q1, q3 = df["lead_time"].quantile([0.25, 0.75])
mask = (nights > 30) | (df["lead_time"] > q3 + 3 * (q3 - q1))   # lead_time above 586 days
print(nights.max(), df["lead_time"].max())                      # -> 69 737
print(mask.sum())   # -> 205
print(df[mask].head(3))
```

### Issue 20: A few missing or "Undefined" values
```python
import pandas as pd
df = pd.read_csv("data/hotels.csv")
mask = (df["children"].isna() | (df["market_segment"] == "Undefined")
        | (df["distribution_channel"] == "Undefined"))
print(mask.sum())   # -> 5
print(df[mask].head(3))
```

## Open questions for the data owner
1. Issue 1: are identical rows separate bookings (for example a group booked one room at a time) or accidental copies? This decides whether we keep them.
2. Issue 2: what does "Non Refund" mean in the hotels' system? Are these real guests who paid a deposit, or room blocks held by tour operators?
3. Issue 3: is a price of 0 outside "Complementary" a free stay, or a price that was never recorded?
4. Issues 4 and 5: are bookings with zero nights or zero guests real (day use, placeholder bookings), or should they be removed?
5. Issues 6 and 7: does `NULL` in `agent` and `company` mean "booked without an agent or company"?
6. Issue 9: how is `is_repeated_guest` defined, and when are the two "previous bookings" columns filled in?
7. Issue 10: is "CN" the same country as "CHN" (China)?
8. Issue 11: is meal "Undefined" the same as "SC" (no meal)?
9. Issue 15: are rows with 10 or more adults whole groups stored in one row?
10. Issue 16: does `previous_cancellations` count the guest's own history, or the size of a cancelled group?
11. Issue 17: for checked-out guests, is `reservation_status_date` the actual departure day, and are the nights columns the booked nights or the nights actually stayed?
