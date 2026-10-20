"""Score rules against confirmed_fraud.csv.

Usage: python3 evaluate.py [transactions.csv] [confirmed_fraud.csv]

Labels are incomplete and biased (see CONFIRMED_FRAUD_NOTE.md), so "unlabeled" is NOT "false positive".
Precision here is a lower bound; recall only describes fraud customers noticed.
"""
import csv
import sys
from collections import Counter

from monitor import FLAGS_PER_MILLION, TIER, load, run


def main():
    tx_path = sys.argv[1] if len(sys.argv) > 1 else "transactions.csv"
    lbl_path = sys.argv[2] if len(sys.argv) > 2 else "confirmed_fraud.csv"
    labels = {r["txn_id"].strip() for r in csv.DictReader(open(lbl_path))}

    txns, _ = load(tx_path)
    flags, ranked = run(txns)
    kept = ranked[:round(len(txns) * FLAGS_PER_MILLION / 1_000_000)]

    print(f"\nCONFIRMED FRAUD: {len(labels)} txn_ids in {lbl_path}")

    print("\nPER RULE (before budget trim)")
    print(f"  {'rule':24} {'flag rows':>10} {'rows w/ confirmed fraud':>24} {'confirmed-fraud txns in them':>29}")
    for rule in TIER:
        fs = [f for f in flags if f.rule == rule]
        caught = {m for f in fs for m in f.members} & labels
        hit = sum(bool(set(f.members) & labels) for f in fs)
        print(f"  {rule:24} {len(fs):>10} {hit:>24} {len(caught):>29}")
    print("  (an R1 row is a whole burst, so one row can hold several confirmed-fraud txns)")

    covered = {m for _, v in kept for m in v["members"]}
    hit_rows = sum(bool(v["members"].keys() & labels) for _, v in kept)
    found = len(covered & labels)
    print("\nFINAL OUTPUT (after budget trim)")
    missed = Counter("under $10" if t.amount < 10 else "$10+" for t in txns if t.txn_id in labels - covered)
    for label, value, note in [
        ("Flags", f"{len(kept)}", ""),
        ("Flags covering confirmed fraud", f"{hit_rows}", f"{hit_rows / len(kept):.1%} of flags; the real share is at least this"),
        ("Confirmed fraud covered", f"{found} / {len(labels)}", f"{found / len(labels):.1%} recall"),
        ("Confirmed fraud missed", f"{len(labels) - found}", ", ".join(f"{n} {k}" for k, n in missed.items())),
    ]:
        print(f"  {label + ':':32} {value:>9}" + (f"   ({note})" if note else ""))
    print("\n  Note: confirmed_fraud.csv only lists fraud that customers disputed. A flag that")
    print("  doesn't match it isn't necessarily a false alarm, so the real share of flags that")
    print("  are fraud is likely higher than shown. See CONFIRMED_FRAUD_NOTE.md.\n")


if __name__ == "__main__":
    main()
