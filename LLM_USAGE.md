# How I used Claude (Claude Code)

## Setup and orientation
- Had it set up a private repo, keep the spec PDF and data CSVs out of git, and remind me of my time budget.
- I haven't worked in fintech, so I asked for a primer on the relevant fraud patterns (card testing, account takeover, fraud rings), how dispute labels work, and why they're biased.

## Exploring the data: my observations, checked by Claude
- I looked through the confirmed-fraud rows myself, wrote down the patterns I saw, and asked Claude to check them against the full 1M rows and tell me if I was wrong.
- I caught my own mistake mid-analysis: I'd read `user_id` as the merchant's customer ID rather than our cardholder, which led me to compare across merchants instead of per user.
- Claude confirmed some observations and corrected others. For example, purchase bursts were minutes apart, not seconds, and large Apple charges alone aren't suspicious because Apple sells hardware.

## Designing the rules
- I proposed the rule ideas from my own reasoning about consumer behavior. Claude measured how often each pattern appears across all transactions before we built anything.
- That dropped one of my ideas. I assumed people rarely make several purchases minutes apart, but 1,735 of 2,000 users do (gas plus snacks, fare plus bag fee). It also narrowed another: devices shared by 2 users look like households, not fraud.
- I made the prioritization calls: one flag per card-testing burst, account takeover ranked above card testing when trimming to budget, and R5 deferred.

## Where Claude was wrong, and how it was caught
- **R1 threshold.** The first version (3+ tiny charges) fired 726 times, and 671 of those were ordinary purchases. This came out of checking results against `confirmed_fraud.csv`, and we raised the minimum to 5. Claude's earlier claim that the rule would catch "exactly" the card-testing charges was wrong; it had only checked the suspicious merchants.
- **Fraud rings.** Claude claimed devices with 5+ users were "clearly" fraud rings. The data showed several were normal shared family devices, so the rule now also requires a high-risk merchant.
- **Docs.** Claude merged the README, rules doc and labels note into one file. I had it split them so the README is only run instructions.
- **Unclear output.** I pushed back on jargon like "lower bound on precision" and confusing table headers until the explanations were plain enough for an analyst to read. That also turned up a stale "see README" reference.

## What I owned
I made every commit and push decision, the rule choices and priorities, and the output format, including adding `related_txn_ids` so all the fraud transactions in a burst are visible in the output. I reviewed the explanations until I could defend them myself.
