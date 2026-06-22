"""
Crucible CLI — judge a population of candidates from a CSV.

  crucible scan <file.csv>           rank every candidate's decision
  crucible explain <file.csv> <name> full reasoning for one candidate

CSV format (long form): one row per outcome
    candidate,return
    momentum_v1,0.012
    momentum_v1,-0.004
    breakout_v2,0.031
    ...
'return' is the per-trial result (already net of cost), any numeric column.
No database, no config — point it at a CSV and go.
"""
import sys
import csv
import argparse
from collections import defaultdict

from crucible.gate.decision import decide

ICON = {"LEAVE": "keep", "WATCH": "watch", "LEAN_AWAY": "reduce", "RETIRE": "retire"}


def _load(path):
    rows = defaultdict(list)
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []
        name_col = cols[0]
        val_col = cols[1] if len(cols) > 1 else cols[0]
        for r in reader:
            try:
                rows[r[name_col]].append(float(r[val_col]))
            except (ValueError, KeyError):
                continue
    return rows


def cmd_scan(args):
    data = _load(args.csv)
    if not data:
        print("No candidates found. Expected CSV columns: candidate,return")
        return
    results = [(name, decide(vals, regime=args.regime)) for name, vals in data.items()]
    results.sort(key=lambda x: x[1].health, reverse=True)
    print(f"\n  {'CANDIDATE':18} {'DECISION':9} {'CONF':>5} {'HEALTH':>7} {'N':>5}")
    print("  " + "-" * 50)
    for name, d in results:
        print(f"  {name:18} {ICON.get(d.action, d.action):9} {d.confidence:5.2f} {d.health:7.2f} {d.n:5d}")
    print(f"\n  regime={args.regime}  (pass --regime to change gate strictness)\n")


def cmd_explain(args):
    data = _load(args.csv)
    vals = data.get(args.name)
    if not vals:
        print(f"\n  '{args.name}' not found in {args.csv}\n")
        return
    d = decide(vals, regime=args.regime)
    print(f"\n  CRUCIBLE CERTIFICATE — {args.name}")
    print(f"    decision    {d.action}")
    print(f"    confidence  {d.confidence:.2f}    health {d.health:.2f}")
    print(f"    evidence    {d.n} outcomes")
    if d.p_value is not None:
        print(f"    p-value     {d.p_value}   (regime {d.regime}, bar {d.sig_bar})")
    print(f"    reason      {d.reason}\n")


def main():
    p = argparse.ArgumentParser(
        prog="crucible",
        description="Tells you which candidates are real, which are overfit, "
                    "and which to retire — and why.")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("scan", help="rank all candidates in a CSV")
    s.add_argument("csv")
    s.add_argument("--regime", default="NORMAL",
                   help="market/context regime; flexes gate strictness")
    s.set_defaults(fn=cmd_scan)
    e = sub.add_parser("explain", help="reasoning for one candidate")
    e.add_argument("csv")
    e.add_argument("name")
    e.add_argument("--regime", default="NORMAL",
                   help="market/context regime; flexes gate strictness")
    e.set_defaults(fn=cmd_explain)
    args = p.parse_args()
    if not getattr(args, "fn", None):
        p.print_help(); sys.exit(0)
    args.fn(args)


if __name__ == "__main__":
    main()
