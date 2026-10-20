# Rules

## Proposed rules (5)

### R1: Card-testing burst (implemented)
- **Pattern:** A stolen card is checked with a burst of tiny charges before bigger fraud.
- **Why it matters:** It's an early warning; blocking the card now prevents the larger loss that follows.
- **False positives:** Legit small purchases close together. A minimum of 3 charges flagged ~670 normal bursts, so it's set to 5.

### R2: Large charge on a new device (implemented)
- **Pattern:** Account takeover: someone logs in from a device the user has never used and spends big.
- **Why it matters:** Takeover losses are large, and the fintech usually absorbs them.
- **Cutoffs:** "Large" means $300 or more. That's above 99% of all charges in the data (the 99th percentile is ~$252), while confirmed takeover charges ran $330–$1,750. "New" means the user first used the device less than 24 hours earlier, after 10+ transactions on other devices, so a user's first-ever device doesn't count.
- **False positives:** A real customer buying something big on a new phone they just set up.

### R3: High-value spree (implemented)
- **Pattern:** Several large purchases within hours, i.e. cashing out a taken-over account.
- **Why it matters:** The most dollars at risk per incident. The 85 sprees here total $1,000–$8,000 each, median ~$3,000.
- **False positives:** Genuine big shopping days (holidays, moving house).

### R4: Shared-device fraud ring (implemented)
- **Pattern:** One device used by many different customers to buy gift cards, prepaid cards, and resale goods.
- **Why it matters:** Fraud rings and mule networks rarely get disputed, so labels never surface them.
- **False positives:** Shared family devices. Requiring a high-risk merchant category excludes them.

### R5: High-risk merchant + unusual amount (deferred)
- **Pattern:** A charge at a cash-out merchant far above the user's normal spending.
- **Why it matters:** Gift cards and prepaid cards are easy to cash out and hard to recover.
- **Why deferred:** Overlaps heavily with R2/R3 in this data.

### Considered and dropped: transactions minutes apart
1,735 of 2,000 users have charges within 5 minutes of each other at normal merchants (gas + snacks, fare + bag fee), so on its own it's noise. Speed is used inside R1 and R3 instead.

## Implemented rules

| Rule | Fires when | Targets |
|---|---|---|
| R1 card-testing burst | 5+ charges under $5 by one user, each within 30 min of the previous. One flag per burst. | Stolen card being tested with tiny charges |
| R2 new device, large charge | Charge of $300+ on a device this user first used less than 24h earlier, and the user had 10+ earlier transactions on other devices | Account takeover |
| R3 high-value spree | 2+ charges of $500+ by one user, each within 3h of the previous | Account takeover cash-out |
| R4 shared-device ring | Charge at a gift card / prepaid / jewelry / resale / electronics-outlet merchant on a device used by 5+ different customers | Fraud ring or mule network |

Thresholds are constants at the top of `monitor.py`.

## Output columns

| Column | Meaning |
|---|---|
| `txn_id` | The flagged transaction. For a card-testing burst, the first charge in the burst. |
| `rules` | Rule(s) that fired, `;`-separated when more than one fired on the same transaction. |
| `reason` | Plain-English explanation for a fraud-ops analyst. |
| `related_txn_ids` | Every transaction the flag covers, space-separated: the whole burst for R1, otherwise just `txn_id`. |

Rows are ordered by review priority: account takeover first, then device rings, then card testing.

## Flag rate and review budget

```
RULES FIRED
  R2_new_device_large        313
  R3_high_value_spree        285
  R4_shared_device_ring      466
  R1_card_testing_burst      102
  (a transaction hit by several rules is one output row)

REVIEW BUDGET
  Flags before budget:        869 (budget of 1,000)
  Flags written:              869 (0 cut by budget)
  Flag rate:               0.087%
```

**Flag rate: 869 flags / 999,955 transactions = 0.087%**, under the ~0.1% budget.

If a run goes over budget, flags are kept in priority order: account takeover (R2/R3), then rings (R4), then card testing (R1). Card testing ranks last because each charge is ~$3, while a takeover spree runs ~$3,000 (median). The summary then shows how many of each rule's flags were kept after the budget.

## Fraud knowingly let through

- **Short card-testing runs (3–4 charges).** Lowering R1 to 3 added ~620 bursts that were almost all normal small purchases. Every confirmed testing burst here was 12+ charges, and each test charge costs ~$3.
- **Takeovers that stay small or use a known device.** R2 needs $300+ on a new device; R3 needs 2+ charges of $500+. A thief making a few $100 purchases, or using the victim's own phone, isn't caught.
- **Small rings or rings buying ordinary goods.** R4 needs 5+ customers on one device *and* a gift card/prepaid/resale merchant, because shared family devices with normal purchases look the same otherwise.

**Why this is the right tradeoff:** the budget is ~1,000 reviews. Analyst time goes to the highest dollar losses first (takeover sprees, median ~$3,000, and rings), not to low-value patterns that would bury analysts in false alarms.

## Data cleaning

All cleaning happens in `load()` in `monitor.py`, with a comment on each step.

| Issue | Count | Handling |
|---|---|---|
| Malformed rows (`not_a_timestamp`, empty amount) | 35 | Skipped. Guessing a timestamp or amount could create or hide a burst. |
| Duplicate `txn_id` (all exact copies) | 1,000 | First copy kept. Duplicates would double-count charges in the burst and spree rules. |
| Amount ≤ 0 (refunds/credits) | 10 | Excluded. The spec defines positive = debit, and every rule is about money leaving the account. |
| Unsorted timestamps | - | Each user's transactions are sorted by time before rules run. |
| Inconsistent merchant names (`SHELL #1005`, `SQ *UBER`) | - | Left as-is on purpose. No rule matches exact merchant identity; R4's category check is a case-insensitive regex. |

## What was cut

- **R5 (high-risk merchant + amount far above the user's normal):** proposed, not built. It overlaps heavily with R2/R3 on the takeover sessions in this data.
- **Merchant-name normalization:** no implemented rule needs it.
- **One flag per takeover session:** R2/R3 flag each purchase separately (a session can be 3–6 rows). Collapsing them like R1 would save ~200 slots, but there's no need while under budget, and analysts may want each charge as its own reversal item.
- **Tests:** none beyond the end-to-end run and `evaluate.py`.
- Out of scope per the spec: ML, streaming, UI, deployment.
