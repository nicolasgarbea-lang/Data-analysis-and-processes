# Events not in `events_zurich.csv` (date not confirmed with a source)

These events are **left out** of `data/manual/events_zurich.csv` because I could not confirm the exact date with a
source page (searched 19 Nov 2026). Add them later only with a source URL.

| event | year(s) | what is known / why left out |
|---|---|---|
| Zürich Marathon | 2019 | race held in April 2019 (hdsports says 2022 was the first race "since 2019"), but no page with the exact date found |
| Zürich Marathon | 2020, 2021 | not held as a normal race (COVID); no confirmed cancellation page fetched |
| Zurich Pride (demo/festival) | 2019 | an SRF article mentions the Saturday parade in 2019, no exact date found |
| Zurich Pride | 2022 | a search listing says 17–18 June 2022; the page (festivalticker.de) could not be fetched to check |
| Zurich Pride | 2024 | a search result says 14–15 June 2024 (30th edition); source page not confirmed |
| Zürcher Silvesterlauf | 2022 | running.COACH listing says 11 Dec 2022; listing only, not checked |
| Zürcher Silvesterlauf | 2023 | no date found |
| Zürcher Silvesterlauf | 2020 | cancelled (COVID), only a virtual race (11 Dec 2020) – not an event in the city |
| Silvesterzauber | 2020, 2021 | not held: nau.ch reports the 2022/23 fireworks were the first since the pandemic |
| Caliente! Latin Music Festival | 2019, 2022, 2023, 2024, 2025 | usually first weekend of July; only 2026 (3–5 July) was confirmed on zuerich.com. 2024 (5–7 July) appears in a search result but the page now shows 2026 |
| Zürich Openair (Rümlang/Glattbrugg, outside the city) | 2019–2026 | not researched in depth; venue is outside the city of Zurich, so little effect on city load |
| Apache 207 at Letzigrund | 2026 (27 May) | only a German concert listing (giga.de), no venue page |
| Other Letzigrund concerts | 2019, 2022, 2023 | no complete concert list found; only concerts with a venue/SRF page are in the CSV |
| 1 May demonstration (Tag der Arbeit) | every year | 1 May is already a public holiday in ZH (`is_holiday`); 2020 demo cancelled (lockdown), 2021 unauthorised demos. No per-year source fetched, so not added as an event |
| Züri Fäscht | 2026 | **did not take place**: the organisers ended the contract with the city; a new city festival is planned from 2029 ([bluewin](https://www.bluewin.ch/en/news/the-zuri-fascht-is-set-to-take-place-again-starting-in-2029-li.3600630)) |
| Weltklasse Zürich | 2020 | replaced by the "Inspiration Games" on 9 Jul 2020 without spectators – not an event day |
| Sechseläuten | 2020, 2021 | cancelled as public festivals (COVID); see `docs/assumptions_calendar.md` for the half-holiday flag |
| Knabenschiessen | 2020, 2021 | 2020 cancelled, 2021 only a small shoot-off without the fair |
| Street Parade | 2020, 2021 | cancelled (COVID) – planned for 8 Aug 2020 and 14 Aug 2021 |
