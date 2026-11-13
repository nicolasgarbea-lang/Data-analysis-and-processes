# Business Model (preliminary)

**Status:** second draft. Anything marked *(to define)* is still open. The open items are collected at the end.

## 1. The idea in one sentence

A decision-support tool that predicts which hotel bookings will be cancelled, so the manager can protect revenue in two ways: by offering the right booking conditions when a booking comes in, and by safely overbooking the right number of rooms 7 days before arrival.

## 2. The problem

- In our data, about **42% of city hotel bookings** and **28% of resort hotel bookings** are cancelled.
- A late cancellation or no-show leaves a room empty that could have been sold. The hotel loses that night's revenue.
- Hotels already overbook to make up for this, but usually by gut feeling or a flat percentage. Overbook too little and rooms stay empty. Overbook too much and a guest has to be moved to another hotel, which costs money and goodwill.
- Booking conditions (refundable or not, deposit or not) are usually the same for everyone, whatever the risk of that particular booking.

## 3. The customer

| | |
|---|---|
| **Who uses it** | The hotel's revenue manager or front-office manager |
| **Who pays** | The hotel, or the hotel group for several properties *(to define)* |
| **Where we start** | Mid-sized independent hotels, like the two in our data (one city hotel in Lisbon, one resort in the Algarve). Big chains often already have expensive revenue-management systems. |

## 4. What goes in (inputs)

### A. Data about the booking, known at booking time (Model A)

- Hotel type (city or resort). We use **one model for both hotels**, with the hotel type as an input, so the model can still learn that the city hotel cancels more often.
- Lead time: days between booking and arrival
- Arrival date: season, weekday, whether the stay includes a weekend, nearby holidays
- Length of stay, number of adults, children and babies
- Price (ADR), price per person, and price compared with the normal price for that month and room type
- Deposit type, meal plan, room type booked
- Booking channel (travel agent, online, direct, corporate) and market segment
- Guest history: repeat guest, earlier cancellations, earlier completed stays
- Special requests, parking request
- How full the hotel already is for that arrival date

**Deliberately left out:** nationality (`country`), for fairness. Also left out are columns that are only filled in after the outcome is known.

### B. Data about bookings still active 7 days before arrival (Model B)

- All bookings still on the books for the target date, with the same features as above

### C. Settings the manager enters

- Number of rooms in the hotel
- Cost of an empty room and cost of moving a guest (see section 6)

## 5. What comes out (outputs)

| Screen | When | What the manager sees | Suggested action |
|---|---|---|---|
| **New booking** (Model A) | When a booking comes in | Cancellation risk as a percentage and a level (low / medium / high), with the main reasons | Depends on the risk level (see section 7) |
| **Next week** (Model B) | 7 days before arrival | Expected number of cancellations and no-shows, **as a range** (for example 8 to 14 rooms) | How many extra rooms to sell (see section 6) |

The tool only **recommends**. No guest is ever refused, and the manager always makes the final decision.

## 6. Costs and the overbooking rule

### Cost of an empty room

The money lost when a room stays empty: **the price of that night (ADR)**. We look at one night at a time, because overbooking is decided night by night.

Simplifications we accept and mention in the limits:
- An empty room also saves a little money (no cleaning, no breakfast), so the true loss is slightly lower than the price.
- If the guest paid a deposit that the hotel keeps, the loss is lower too.

### Cost of moving a guest to another hotel

When the hotel is overbooked and everyone shows up, one guest has to be sent elsewhere. The hotel then pays:
- the room at the other hotel, which is often more expensive because it's a busy night
- transport to the other hotel (a taxi)
- often a small compensation (a voucher, a free night later)
- the risk that this guest never comes back and writes a bad review

**Our assumption:** moving a guest costs **2 times the price of the night**. The dataset doesn't contain this number, so it's an assumption. In the app it is a slider (from 1× to 4×), and in the evaluation we show how the recommendation changes with it. *(We'd like a source for the 2×. A revenue-management textbook or a hotel's walking policy would do.)*

### The overbooking rule

With these two costs, the rule for each extra room is:

> Sell one more extra room only if we are at least **X% sure** that a room will free up for it.
>
> X = cost of moving a guest ÷ (cost of moving a guest + cost of an empty room)

With our assumption (moving = 2 × price, empty = 1 × price): X = 2 ÷ 3 = **67%**.

Example: Model B says that for next Saturday there's a 90% chance at least 5 rooms free up, a 70% chance at least 8 free up, and a 50% chance at least 11 free up. The tool recommends selling **8 extra rooms**, the highest number we are still at least 67% sure about.

Because moving a guest costs more than an empty room, the tool is careful: it overbooks less than the average number of cancellations.

## 7. Risk levels for new bookings

### The three levels (starting values)

The whole dataset has a cancellation rate of about 37%. We start with these cut-offs and adjust them as described below.

| Level | Predicted risk | What the tool suggests | Why |
|---|---|---|---|
| **Low** | below 25% | Nothing. Keep flexible conditions. | Most of these guests come. Don't bother them. |
| **Medium** | 25% to 60% | A friendly reminder email 7 days before arrival, asking the guest to confirm. Optionally a small extra for confirming (free breakfast, late check-out). | Cheap, and it doesn't annoy the guests who will come. If someone cancels after the reminder, the room is freed early enough to sell again. |
| **High** | above 60% | Offer a non-refundable rate with a discount (for example 10%), or ask for a deposit for the first night. | Here most guests cancel, so it's worth asking for commitment. The guest still chooses, and nobody is refused. |

### How we set the final cut-offs

1. **The model must be calibrated first.** A "60%" from the model must really mean that about 60 out of 100 of those bookings cancel. Otherwise the levels mean nothing.
2. **Set the cut-offs on 2016 data, never on 2017.** 2017 is our test year. If we tune on it, our results look better than they are. We use the last months of 2016 as a validation set.
3. **Check the size of each group.** The "high" group must not be too big (around 15% to 25% of bookings, *to define*). Otherwise we put stricter conditions on too many guests.
4. **Check the cost logic.** A non-refundable offer with a 10% discount pays off when the risk is well above 10%. We set the cut-off much higher (60%) on purpose, so we don't give away discounts or annoy guests who would have come anyway.

### Something to check in the data

In this dataset, bookings that were already non-refundable are said to cancel very often, which seems strange. We need to look at this in step 1. If it's true, "offer a non-refundable rate" may not work as an action, and we may prefer a deposit.

## 8. Value proposition

- **More revenue from the same rooms:** fewer rooms stay empty because of cancellations.
- **Fewer moved guests:** overbooking is based on measured risk instead of guesswork.
- **Fairer conditions:** low-risk guests keep flexible terms, and only higher-risk bookings get stricter ones.
- **Explainable:** every risk score comes with its reasons, so the manager can trust it or overrule it.
- **Honest about uncertainty:** ranges instead of single numbers, because cancellations happen together (groups, strikes, weather, currency shocks).

## 9. How we show the value in euros

A hotel manager doesn't care about "precision" or "recall". They want to know how much money the tool saves. So we replay the year 2017, which the model has never seen, night by night, three times:

| Scenario | What the hotel does |
|---|---|
| **No overbooking** | Sells exactly as many rooms as it has |
| **Simple rule** | Always overbooks by the same percentage (for example 10%) |
| **Our tool** | Overbooks by the number Model B recommends |

For each scenario we add up:
- **lost money from empty rooms** = number of empty rooms × price of the night
- **cost of moved guests** = number of moved guests × 2 × price of the night

The difference between the scenarios is the headline of the presentation, for example: *"In 2017, our tool would have saved the city hotel about € X compared with no overbooking."*

**Things we must assume for this simulation:**
- The dataset doesn't say how many rooms each hotel has. We can estimate it from the busiest night in the data *(to define)*.
- We assume the extra rooms could actually have been sold, which is realistic in busy periods but less so in quiet ones.

Model A is harder to put in euros, because we don't know how many guests would accept a non-refundable offer. For Model A we show what share of all 2017 cancellations falls into the "high" group.

## 10. How we measure success

| Metric | What it shows |
|---|---|
| Precision and recall against the baseline ("booked far in advance = high risk") | The model is better than a simple rule of thumb |
| Calibration | A predicted 30% risk really means about 30% cancel |
| Money saved in 2017 (section 9) | The business value, in the manager's own terms |
| Number of guests who would have been moved in 2017 | The cost side of overbooking |

## 11. How it is delivered

- A Streamlit web app with two screens ("New booking" and "Next week")
- Models trained on 2015 and 2016 and tested on 2017, saved and loaded by the app
- In a real product: a connection to the hotel's booking system (PMS) and regular retraining *(out of scope for the course, but worth mentioning)*

## 12. Business model canvas (summary for the visual)

| Block | Content |
|---|---|
| **Customer segment** | Revenue managers of independent mid-sized hotels |
| **Problem** | High cancellation rates cause empty rooms and lost revenue; overbooking is done by gut feeling |
| **Value proposition** | Predict cancellations, protect revenue, overbook safely |
| **Inputs** | Booking details, hotel occupancy, calendar data, manager's cost settings |
| **Solution / outputs** | Risk level with reasons and a suggested booking condition; recommended number of extra rooms with a range |
| **Channel** | Web app; later, integration with the booking system |
| **Revenue model** | Monthly subscription per hotel or per room *(to define, assumption only)* |
| **Key metrics** | Money saved, rooms left empty, guests moved, model calibration |
| **Costs** | Data integration, model maintenance and retraining, hosting |
| **Limits and ethics** | No nationality, no refusals, the manager decides, ranges shown instead of single numbers |

## 13. Decisions and open questions

### Decided

| Decision | Reason |
|---|---|
| Cost of an empty room = price of the night | It's the money lost, and it's in the data |
| Cost of moving a guest = 2 × price of the night (assumption, adjustable) | Covers the other hotel, transport and compensation |
| Model B predicts 7 days before arrival | Matches the "last week" figure in the proposal |
| One model for both hotels, with hotel type as an input | More data for training; the input lets the model treat the hotels differently |
| Three risk levels: below 25%, 25% to 60%, above 60% (starting values) | Tuned later on 2016 data |

### Still open

1. **A source for the "2 × price" cost of moving a guest**, or we keep it as a stated assumption.
2. **The number of rooms per hotel**, needed for the 2017 simulation.
3. **Do non-refundable bookings really cancel so often in the data?** This decides whether "offer non-refundable" is a good action.
4. **How big the "high" group may be** (15% to 25% of bookings?).
5. **Which extra data we add:** holidays, events, exchange rates, or none.
6. **Revenue model**, if the presentation needs one.
7. **Who the main user is:** the revenue manager, the front desk, or both.
