"""Rule-based transaction monitoring.

Usage: python3 monitor.py [transactions.csv] [output/flagged_transactions.csv]

Standard library only. Loads the CSV once, indexes by user and device, runs four
rules, then trims the combined flags to the analyst review budget by priority.
"""
import csv
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

# Review budget: ~1,000 flags per 1M transactions.
FLAGS_PER_MILLION = 1000

# R1 card testing: a burst of tiny charges chained by short gaps.
R1_MAX_AMOUNT = 5.00
R1_MAX_GAP = timedelta(minutes=30)
R1_MIN_BURST = 5  # at 3, ~670 bursts were ordinary small purchases (Subway, Etsy...); real testing runs 12-25

# R2 new-device takeover: large charge on a device the user only just started using.
R2_MIN_AMOUNT = 300.00
R2_DEVICE_AGE = timedelta(hours=24)
R2_MIN_PRIOR_TXNS = 10  # user must have an established history on other devices

# R3 high-value spree: several large charges in a short window.
R3_MIN_AMOUNT = 500.00
R3_MAX_GAP = timedelta(hours=3)
R3_MIN_COUNT = 2

# R4 device ring: one device shared by many users, buying cash-out goods.
R4_MIN_USERS = 5
HIGH_RISK_MERCHANT = re.compile(r"gift\s*card|prepaid|jewel|resell|electronics outlet", re.I)

# Lower tier = reviewed first. Account takeover (R2/R3) loses thousands per session,
# rings (R4) similar but labels can't confirm them, card testing (R1) loses ~$3/charge.
TIER = {"R2_new_device_large": 0, "R3_high_value_spree": 0, "R4_shared_device_ring": 1, "R1_card_testing_burst": 2}


@dataclass
class Txn:
    txn_id: str
    user_id: str
    ts: datetime
    merchant: str
    amount: float
    device_id: str


@dataclass
class Flag:
    txn_id: str
    rule: str
    reason: str
    severity: float  # dollars at risk, used to order flags within a tier
    members: list = field(default_factory=list)  # all txn_ids the flag covers


def load(path):
    """Parse and clean. Returns (txns, stats). Bad rows are counted, not fatal."""
    stats = {"rows": 0, "malformed": 0, "duplicate": 0, "non_debit": 0}
    seen, txns = set(), []
    with open(path, newline="") as f:
        reader = csv.reader(f)
        next(reader)  # header row
        for rec in reader:
            stats["rows"] += 1

            # CLEANING 1 - malformed rows: skip any row we can't parse.
            # Seen in the data: timestamp "not_a_timestamp" and empty amount fields (35 rows).
            # Also covers rows with the wrong number of columns. Skipped, not guessed at:
            # inventing a timestamp or amount could create or hide a burst.
            try:
                txn_id, user, ts, merchant, amount, device = (x.strip() for x in rec)
                t = Txn(txn_id, user, datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"), merchant, float(amount), device)
            except ValueError:
                stats["malformed"] += 1
                continue

            # CLEANING 2 - duplicates: keep the first row for each txn_id, drop repeats.
            # All 1,000 repeats in the data are exact copies of an earlier row. Left in,
            # they would double-count charges and inflate the burst/spree rules.
            if t.txn_id in seen:
                stats["duplicate"] += 1
                continue
            seen.add(t.txn_id)

            # CLEANING 3 - refunds/credits: exclude amount <= 0 (10 rows).
            # The spec defines positive = debit; every rule here is about money leaving
            # the account, so credits are out of scope.
            if t.amount <= 0:
                stats["non_debit"] += 1
                continue

            # Not cleaned on purpose: merchant_name spelling/casing. No rule matches on
            # exact merchant identity; R4's category check is a case-insensitive regex.
            txns.append(t)
    return txns, stats


def chains(txns, max_gap):
    """Split time-sorted txns into runs where each is within max_gap of the previous."""
    run = []
    for t in txns:
        if run and t.ts - run[-1].ts > max_gap:
            yield run
            run = []
        run.append(t)
    if run:
        yield run


def money(x):
    return f"${x:,.2f}"


def rule_card_testing(by_user):
    """R1: >=3 sub-$5 charges chained by <=30 min gaps. One flag per burst."""
    for user, txns in by_user.items():
        tiny = [t for t in txns if t.amount < R1_MAX_AMOUNT]
        for burst in chains(tiny, R1_MAX_GAP):
            if len(burst) < R1_MIN_BURST:
                continue
            mins = (burst[-1].ts - burst[0].ts).total_seconds() / 60
            merchants = sorted({t.merchant for t in burst})
            yield Flag(
                burst[0].txn_id, "R1_card_testing_burst",
                f"Possible card testing: {len(burst)} charges under {money(R1_MAX_AMOUNT)} in {mins:.0f} min "
                f"({money(sum(t.amount for t in burst))} total) at {len(merchants)} merchant(s): {', '.join(merchants)}. "
                f"All burst charges are in related_txn_ids.",
                severity=len(burst), members=[t.txn_id for t in burst])


def rule_new_device_large(by_user):
    """R2: >=$300 charge on a device first used by this user <24h ago, when the user
    already has an established history on other devices."""
    for user, txns in by_user.items():
        first_seen = {}
        for i, t in enumerate(txns):
            first_seen.setdefault(t.device_id, (t.ts, i))
        for t in txns:
            if t.amount < R2_MIN_AMOUNT:
                continue
            dev_ts, dev_idx = first_seen[t.device_id]
            if dev_idx < R2_MIN_PRIOR_TXNS or t.ts - dev_ts > R2_DEVICE_AGE:
                continue  # device is not new, or user has no established history before it
            prior = txns[:dev_idx]
            usual = sorted(a.amount for a in prior)
            hours = (t.ts - dev_ts).total_seconds() / 3600
            yield Flag(
                t.txn_id, "R2_new_device_large",
                f"Possible account takeover: {money(t.amount)} at {t.merchant} on device {t.device_id}, "
                f"first used by this user {hours:.1f}h earlier. Before that device appeared the user had "
                f"{len(prior)} txns on other device(s) with median {money(usual[len(usual) // 2])}.",
                severity=t.amount, members=[t.txn_id])


def rule_high_value_spree(by_user):
    """R3: >=2 charges of >=$500 chained by <=3h gaps. Each charge is flagged."""
    for user, txns in by_user.items():
        big = [t for t in txns if t.amount >= R3_MIN_AMOUNT]
        for spree in chains(big, R3_MAX_GAP):
            if len(spree) < R3_MIN_COUNT:
                continue
            hours = (spree[-1].ts - spree[0].ts).total_seconds() / 3600
            total = sum(t.amount for t in spree)
            devices = sorted({t.device_id for t in spree})
            for n, t in enumerate(spree, 1):
                yield Flag(
                    t.txn_id, "R3_high_value_spree",
                    f"High-value spree: charge {n} of {len(spree)} over {money(R3_MIN_AMOUNT)} within {hours:.1f}h "
                    f"({money(total)} total) on device(s) {', '.join(devices)}; this one {money(t.amount)} at {t.merchant}.",
                    severity=t.amount, members=[t.txn_id])


def rule_shared_device_ring(by_device):
    """R4: charge at a cash-out merchant on a device used by >=5 distinct users."""
    for device, txns in by_device.items():
        users = {t.user_id for t in txns}
        if len(users) < R4_MIN_USERS:
            continue
        for t in txns:
            if HIGH_RISK_MERCHANT.search(t.merchant):
                yield Flag(
                    t.txn_id, "R4_shared_device_ring",
                    f"Possible fraud ring: device {device} has been used by {len(users)} different customers; "
                    f"this {money(t.amount)} charge is at {t.merchant} (gift card/prepaid/resale category).",
                    severity=t.amount, members=[t.txn_id])


def run(txns):
    by_user, by_device = defaultdict(list), defaultdict(list)
    for t in txns:
        by_user[t.user_id].append(t)
        by_device[t.device_id].append(t)
    for v in by_user.values():  # input is not sorted
        v.sort(key=lambda t: t.ts)

    flags = [*rule_new_device_large(by_user), *rule_high_value_spree(by_user),
             *rule_shared_device_ring(by_device), *rule_card_testing(by_user)]

    # Merge rules that fired on the same txn into one output row.
    merged = {}
    for f in flags:
        m = merged.setdefault(f.txn_id, {"rules": [], "reasons": [], "tier": 9, "severity": 0, "members": {}})
        m["rules"].append(f.rule)
        m["reasons"].append(f.reason)
        m["tier"] = min(m["tier"], TIER[f.rule])
        m["severity"] = max(m["severity"], f.severity)
        m["members"].update(dict.fromkeys(f.members))  # dict keeps time order, drops repeats
    ranked = sorted(merged.items(), key=lambda kv: (kv[1]["tier"], -len(kv[1]["rules"]), -kv[1]["severity"]))
    return flags, ranked


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "transactions.csv"
    out = sys.argv[2] if len(sys.argv) > 2 else "output/flagged_transactions.csv"
    started = datetime.now()

    txns, stats = load(src)
    flags, ranked = run(txns)
    budget = round(len(txns) * FLAGS_PER_MILLION / 1_000_000)
    kept, cut = ranked[:budget], ranked[budget:]

    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        # related_txn_ids: every txn the flag covers (a whole R1 burst; otherwise just txn_id itself).
        w.writerow(["txn_id", "rules", "reason", "related_txn_ids"])
        for txn_id, m in kept:
            w.writerow([txn_id, ";".join(m["rules"]), " | ".join(m["reasons"]), " ".join(m["members"])])

    print("\nDATA CLEANING")
    print(f"  Rows read:            {stats['rows']:>9,}")
    print(f"  Malformed (skipped):  {stats['malformed']:>9,}")
    print(f"  Duplicates (dropped): {stats['duplicate']:>9,}")
    print(f"  Refunds (excluded):   {stats['non_debit']:>9,}")
    print(f"  Transactions scored:  {len(txns):>9,}")

    print("\nRULES FIRED")
    for rule in TIER:
        fired = sum(f.rule == rule for f in flags)
        line = f"  {rule:24} {fired:>5}"
        if cut:  # only informative when the budget trimmed something: shows which rule lost flags
            line += f"   ({sum(rule in m['rules'] for _, m in kept)} kept after budget)"
        print(line)
    print("  (a transaction hit by several rules is one output row)")

    print("\nREVIEW BUDGET")
    print(f"  Flags before budget:  {len(ranked):>9,} (budget of {budget:,})")
    print(f"  Flags written:        {len(kept):>9,} ({len(cut):,} cut by budget)")
    print(f"  Flag rate:            {len(kept) / len(txns):>9.3%}")

    print(f"\nWrote {out} in {(datetime.now() - started).total_seconds():.1f}s\n")


if __name__ == "__main__":
    main()
