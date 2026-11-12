# Ideas

## Enriching the data

Ways to add information to `data/hotels.csv` beyond its original columns. According to the dataset paper, the city hotel is in Lisbon and the resort hotel is in the Algarve, so holidays, events and weather should be for Portugal.

The ideas are ordered from easiest to hardest.

### 1. Features built from the dataset itself

No outside data needed.

- **Season**, from the arrival month.
- **Day of the week of arrival**, and whether the stay includes a weekend.
- **Total length of stay:** weekend nights plus weeknights.
- **Price per person.**
- **Price compared with normal for that time.** For example, "this room costs 30% more than the average for the same room type in the same month." A guest who paid a lot might find a cheaper deal later and cancel.
- **Weekday when the booking was made.**

### 2. Holidays

- **Portuguese public holidays:** the Python package `holidays` provides them.
- **Portuguese school holidays:** from the Portuguese Ministry of Education's website.
- **Bridge days:** when a holiday falls on a Tuesday or Thursday, many people take the Monday or Friday off.

Possible features: "arrival on or near a holiday" and "days until the next holiday".

### 3. Events in Lisbon and the Algarve

Big events fill the city. When hotels are in high demand, guests may book several hotels "just in case" and cancel the rest.

Examples from 2015 to 2017 (check the exact dates before using them):

- Santo António festivals (Lisbon, mid-June)
- NOS Alive music festival (July)
- Rock in Rio Lisboa (May 2016)
- Web Summit (moved to Lisbon in November 2016)
- Home football matches of Benfica and Sporting, especially in the Champions League

Each event happens only once or twice in the data, so the model can't learn much from any single one. Combine them into one feature: "major event in the city during the stay: yes/no".

### 4. Weather

- Historical daily weather for Lisbon and Faro is free from Open-Meteo (historical weather API) or Meteostat.
- **Limit:** at booking time, nobody knows the weather 200 days ahead. Weather only makes sense for Model B, a few days before arrival, and should be treated as a forecast. Using the actual weather is a small cheat, and we would have to mention it.

### 5. Economic factors

- **Exchange rates:** many guests come from the UK. The Brexit vote in June 2016 made the pound drop sharply, which made Portugal more expensive for British travellers. We can test whether cancellations changed after that.
- Historical rates are free from the European Central Bank.
- This is an example of a shock that hits many guests at once, which is why cancellations are not independent.

### 6. How full the hotel is ("demand pressure")

- For each booking, count how many other bookings already exist for the same arrival date.
- A nearly full hotel might mean more guests booking several hotels just in case.
- **Limit:** only count bookings that were made before this booking. Otherwise we use information from the future.

### Rules to keep it honest

1. **Only use what was known at prediction time.** Holidays and planned events are fine because they are known in advance. Real weather and future bookings are not.
2. **Test whether each addition helps.** Train the model with and without the new features and compare them on 2017. If something adds nothing, we say so.

### Suggested priority

| Priority | Idea | Why |
|----------|------|-----|
| Do for sure | 1, 2 and 6 | Cheap and likely to help |
| Creative extra | 3 or 5 | The Brexit and exchange-rate story is memorable in a presentation |
| Only if time is left | 4 | Hard to use honestly |
