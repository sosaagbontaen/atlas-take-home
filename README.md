# Atlas Take-Home: Transaction Monitoring Subsystem

Rule-based monitoring that reads `transactions.csv` (~1M rows), flags suspicious transactions, and trims the result to a fraud-ops review budget of ~1,000 flags per 1M transactions.

## Run it

Requires Python 3.9+. Standard library only, nothing to install.

1. Put the two provided files in the repo root (they are gitignored, not committed):
   - `transactions.csv`
   - `confirmed_fraud.csv`
2. Generate the flags (~12 seconds on a laptop):
   ```bash
   python3 monitor.py
   ```
   Writes `output/flagged_transactions.csv` and prints a run summary.
3. Optional: score the rules against the confirmed-fraud list:
   ```bash
   python3 evaluate.py
   ```

Both scripts take file paths as optional arguments: `python3 monitor.py <transactions.csv> <output.csv>` and `python3 evaluate.py <transactions.csv> <confirmed_fraud.csv>`.

## Files

| File | Purpose |
|---|---|
| `monitor.py` | Loads and cleans the data, runs the rules, ranks flags, trims to budget, writes the output. |
| `evaluate.py` | Reruns the rules in memory and compares them with `confirmed_fraud.csv`. Acts as a rough sanity check of whether the rules catch the fraud we already know about. Understandably, some fraudulent transactions may not have been disputed, so it's not an authoritative check |
| `output/flagged_transactions.csv` | The flagged-output deliverable. |
| `RULES.md` | Rules doc: proposed rules, what was built, flag rate and budget tuning, data cleaning, what was cut. |
| `CONFIRMED_FRAUD_NOTE.md` | How `confirmed_fraud.csv` was used and what it does and doesn't tell us. |
