# Cross-check: ewz Bruttolastgang (local time) vs ewz Netzebenen NE5+NE7 (UTC)

Netzebenen metadata (data.stadt-zuerich.ch, field `Timestamp`): *"Die Werte der Bruttoenergie beziehen sich auf die 15 Minuten vor dieser Zeitangabe"* → its timestamps mark the END of the interval.

Below, Bruttolastgang was converted with our rule (local label = END, → UTC, −15 min = START) and compared with Netzebenen (UTC END label −15 min = START), shifting Netzebenen by k × 15 min.

| shift of Netzebenen | correlation | mean abs. diff (kWh/15 min) | n |
|---|---|---|---|
| -60 min | 0.957787 | 3483.1 | 275900 |
| -45 min | 0.975048 | 2717.9 | 275901 |
| -30 min | 0.988101 | 1920.4 | 275902 |
| -15 min | 0.996589 | 1022.0 | 275903 |
| +0 min | 0.999993 | 17.2 | 275904 |
| +15 min | 0.996584 | 1023.8 | 275905 |
| +30 min | 0.988091 | 1922.7 | 275906 |
| +45 min | 0.975034 | 2720.5 | 275907 |
| +60 min | 0.957770 | 3485.8 | 275908 |

Shift 0 is best by far → both files use the same convention, i.e. the ewz local timestamps are END labels too.
Further evidence: every ewz year file starts at 00:15 or ends with the 00:00 row of the next day (2019 starts 00:15; 2020–2026 start with the 00:00 row = last interval of the previous year; the 2026 file ends with a single 00:00 row of the next day; the missing 2021 days span exactly 00:15 → 00:00 of the next day).

- matched intervals: 275904
- abs. difference: median 1.86 kWh, mean 17.21 kWh, max 714.6 kWh (typical value ~60,000 kWh)
- intervals with > 1 % difference: 13 (days: 2026-07-19, 2026-08-02, 2026-08-23; likely later revisions of one file)
- Netzebenen covers 2016-12-31 23:00:00+00:00 → 2026-11-15 22:45:00+00:00 (interval starts, UTC)

## Autumn DST duplicates (local labels 02:00–02:45 appear twice)

`file_order_chronological` = True means the first of the two rows in the file is the summer-time (earlier) interval. The order is not consistent, so sorting by file order would be wrong in 27 of 32 pairs.

| local label | row 1 kWh | row 2 kWh | NE summer-time | NE winter-time | file order chronological | method |
|---|---|---|---|---|---|---|
| 2019-10-27 02:00:00 | 53795 | 54261 | 54264 | 53798 | False | matched to Netzebenen |
| 2019-10-27 02:15:00 | 56644 | 53118 | 56647 | 53121 | True | matched to Netzebenen |
| 2019-10-27 02:30:00 | 55956 | 52512 | 55958 | 52515 | True | matched to Netzebenen |
| 2019-10-27 02:45:00 | 54839 | 51621 | 54842 | 51624 | True | matched to Netzebenen |
| 2020-10-25 02:00:00 | 54999 | 54079 | 54999 | 54079 | True | matched to Netzebenen |
| 2020-10-25 02:15:00 | 53428 | 56880 | 56880 | 53428 | False | matched to Netzebenen |
| 2020-10-25 02:30:00 | 52974 | 56079 | 56079 | 52974 | False | matched to Netzebenen |
| 2020-10-25 02:45:00 | 51968 | 55137 | 55137 | 51968 | False | matched to Netzebenen |
| 2021-10-31 02:00:00 | 55986 | 56033 | 56033 | 55986 | False | matched to Netzebenen |
| 2021-10-31 02:15:00 | 55051 | 58562 | 58562 | 55051 | False | matched to Netzebenen |
| 2021-10-31 02:30:00 | 54495 | 57852 | 57852 | 54495 | False | matched to Netzebenen |
| 2021-10-31 02:45:00 | 53738 | 56837 | 56837 | 53738 | False | matched to Netzebenen |
| 2022-10-30 02:00:00 | 51852 | 52410 | 52410 | 51852 | False | matched to Netzebenen |
| 2022-10-30 02:15:00 | 50870 | 54478 | 54478 | 50870 | False | matched to Netzebenen |
| 2022-10-30 02:30:00 | 53689 | 50255 | 53690 | 50255 | True | matched to Netzebenen |
| 2022-10-30 02:45:00 | 49853 | 52670 | 52670 | 49853 | False | matched to Netzebenen |
| 2023-10-29 02:00:00 | 52376 | 53169 | 53184 | 52381 | False | matched to Netzebenen |
| 2023-10-29 02:15:00 | 51459 | 55343 | 55355 | 51463 | False | matched to Netzebenen |
| 2023-10-29 02:30:00 | 50936 | 54892 | 54903 | 50939 | False | matched to Netzebenen |
| 2023-10-29 02:45:00 | 50585 | 53756 | 53764 | 50587 | False | matched to Netzebenen |
| 2024-10-27 02:00:00 | 52344 | 53049 | 53049 | 52344 | False | matched to Netzebenen |
| 2024-10-27 02:15:00 | 51592 | 55603 | 55602 | 51592 | False | matched to Netzebenen |
| 2024-10-27 02:30:00 | 50761 | 54715 | 54715 | 50761 | False | matched to Netzebenen |
| 2024-10-27 02:45:00 | 49952 | 53544 | 53544 | 49952 | False | matched to Netzebenen |
| 2025-10-26 02:00:00 | 54251 | 55563 | 55560 | 54248 | False | matched to Netzebenen |
| 2025-10-26 02:15:00 | 53576 | 57365 | 57363 | 53573 | False | matched to Netzebenen |
| 2025-10-26 02:30:00 | 52625 | 56515 | 56513 | 52623 | False | matched to Netzebenen |
| 2025-10-26 02:45:00 | 51930 | 55172 | 55170 | 51928 | False | matched to Netzebenen |
| 2026-10-25 02:00:00 | 54843 | 55064 | 55064 | 54843 | False | matched to Netzebenen |
| 2026-10-25 02:15:00 | 53871 | 56924 | 56924 | 53871 | False | matched to Netzebenen |
| 2026-10-25 02:30:00 | 52996 | 56646 | 56646 | 52996 | False | matched to Netzebenen |
| 2026-10-25 02:45:00 | 52326 | 55677 | 55677 | 52326 | False | matched to Netzebenen |
