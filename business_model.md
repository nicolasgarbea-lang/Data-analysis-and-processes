# Business Model (preliminary)

**Status:** first draft for the team to discuss. Anything marked *(to define)* is still open. The open items are collected at the end.

## 1. The idea in one sentence

A decision-support tool that predicts which hotel bookings will be cancelled, so the manager can protect revenue in two ways: by offering the right booking conditions when a booking comes in, and by safely overbooking the right number of rooms the day before arrival.

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

### B. Data about bookings still active a few days before arrival (Model B)

- All bookings still on the books for the target date, with the same features as above
- Days left until arrival *(how many is still to define, probably 7)*

### C. Settings the manager enters

- Number of rooms in the hotel
- Cost of an empty room (lost revenue for that night)
- Cost of moving a guest to another hotel (rebooking, transport, compensation, reputation)

## 5. What comes out (outputs)

| Screen | When | What the manager sees | Suggested action |
|---|---|---|---|
| **New booking** (Model A) | When a booking comes in | Cancellation risk (low / medium / high) and the main reasons for it | Low: nothing. Medium: a reminder email or an upgrade offer. High: offer a non-refundable rate with a discount, or ask for a deposit. |
| **Tomorrow** (Model B) | A few days before arrival | Expected number of no-shows and late cancellations, **as a range** (for example 8 to 14 rooms) | How many extra rooms to sell, set at the level where expected cost is lowest |

The tool only **recommends**. No guest is ever refused, and the manager always makes the final decision.

## 6. Value proposition

- **More revenue from the same rooms:** fewer rooms stay empty because of last-minute cancellations.
- **Fewer moved guests:** overbooking is based on measured risk instead of guesswork.
- **Fairer conditions:** low-risk guests keep flexible terms, and only higher-risk bookings get stricter ones.
- **Explainable:** every risk score comes with its reasons, so the manager can trust it or overrule it.
- **Honest about uncertainty:** ranges instead of single numbers, because cancellations happen together (groups, strikes, weather, currency shocks).

## 7. How we measure success

| Metric | What it shows |
|---|---|
| Precision and recall against the baseline ("booked far in advance = high risk") | The model is better than a simple rule of thumb |
| Calibration | A predicted 30% risk really means about 30% cancel |
| Revenue protected per year, in € (simulated on 2017) | The business value, in the manager's own terms |
| Number of guests who would have been moved (simulated on 2017) | The cost side of overbooking |

## 8. How it is delivered

- A Streamlit web app with two screens ("New booking" and "Tomorrow")
- Models trained on 2015 and 2016 and tested on 2017, saved and loaded by the app
- In a real product: a connection to the hotel's booking system (PMS) and regular retraining *(out of scope for the course, but worth mentioning)*

## 9. Business model canvas (summary for the visual)

| Block | Content |
|---|---|
| **Customer segment** | Revenue managers of independent mid-sized hotels |
| **Problem** | High cancellation rates cause empty rooms and lost revenue; overbooking is done by gut feeling |
| **Value proposition** | Predict cancellations, protect revenue, overbook safely |
| **Inputs** | Booking details, hotel occupancy, calendar data, manager's cost settings |
| **Solution / outputs** | Risk score with reasons and a suggested booking condition; recommended overbooking range |
| **Channel** | Web app; later, integration with the booking system |
| **Revenue model** | Monthly subscription per hotel or per room *(to define, assumption only)* |
| **Key metrics** | Revenue protected, rooms left empty, guests moved, model calibration |
| **Costs** | Data integration, model maintenance and retraining, hosting |
| **Limits and ethics** | No nationality, no refusals, the manager decides, ranges shown instead of single numbers |

## 10. What we still need to define

1. **The cost of an empty room and of moving a guest.** These numbers decide the overbooking threshold. We need sources or justified assumptions.
2. **How many days before arrival Model B predicts.** Seven days matches the proposal.
3. **One model for both hotels, or one per hotel?** Their cancellation rates differ a lot.
4. **The suggested actions per risk level.** Which conditions do we actually recommend (deposit, non-refundable discount, reminder) and where are the risk cut-offs?
5. **Which extra data we add.** Holidays, events, exchange rates, or none, depending on what the evaluation shows.
6. **How we show the value in euros.** One simulated year (2017), comparing "with our tool" and "without".
7. **Revenue model**, if the presentation needs one: subscription per hotel, per room, or a share of the revenue protected.
8. **Who the main user is:** the revenue manager, the front desk, or both. This changes how simple the screens must be.
