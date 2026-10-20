# Using `confirmed_fraud.csv`

The 190 confirmed-fraud IDs were used to explore patterns and to sanity-check thresholds, not as ground truth. `python3 evaluate.py` gives:

```
PER RULE (before budget trim)
  rule                      flag rows  rows w/ confirmed fraud  confirmed-fraud txns in them
  R2_new_device_large             313                       29                            29
  R3_high_value_spree             285                       28                            28
  R4_shared_device_ring           466                        0                             0
  R1_card_testing_burst           102                       53                           158
  (an R1 row is a whole burst, so one row can hold several confirmed-fraud txns)

FINAL OUTPUT (after budget trim)
  Flags:                                 869
  Flags covering confirmed fraud:         85   (9.8% of flags; the real share is at least this)
  Confirmed fraud covered:         190 / 190   (100.0% recall)
  Confirmed fraud missed:                  0
```

## What it tells us

- Every confirmed-fraud transaction is covered by some flag.
- The labels caught a bad threshold. With R1 at 3+ charges, it fired 726 times but only 53 of those bursts contained confirmed fraud. The rest were ordinary small purchases (Subway, Etsy) half an hour apart. Real testing bursts were 12–25 charges, so the minimum went to 5.

## What it doesn't tell us

- **The list only contains fraud customers reported, so it undercounts.** In one takeover session, the attacker made 6 purchases but the customer disputed only 1. All 6 are flagged, yet only 1 counts as "confirmed." So 9.8% of flags being confirmed fraud is the minimum; the real share is higher.
- **R4 scores 0 and that's expected.** Fraud rings and mule accounts have no victim who files a dispute, so dispute labels can't confirm or reject this rule.
- **100% means we caught all *reported* fraud, not all fraud.** Fraud nobody disputes (like the device rings in R4) isn't in the list, so the list can't show whether we caught it. The data is also synthetic with very clean patterns, which makes a perfect score easier than with real data.
