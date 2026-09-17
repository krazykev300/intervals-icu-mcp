"""Diff two smoke-eval result files.

Highlights cases where one run passed and the other failed, surfacing
regressions and wins.

Usage:
    uv run python scripts/smoke_eval_diff.py baseline.json branch.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, dict[str, Any]]:
    return {r["id"]: r for r in json.loads(path.read_text())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path, help="Baseline results JSON (e.g. main)")
    parser.add_argument("branch", type=Path, help="Branch results JSON")
    args = parser.parse_args()

    baseline = load(args.baseline)
    branch = load(args.branch)

    all_ids = sorted(set(baseline) | set(branch))

    wins: list[tuple[str, str, str]] = []
    regressions: list[tuple[str, str, str]] = []
    same_pass: list[str] = []
    same_fail: list[tuple[str, str, str, str]] = []
    routing_changed: list[tuple[str, str, str]] = []

    for case_id in all_ids:
        b = baseline.get(case_id)
        n = branch.get(case_id)
        if b is None:
            print(f"[NEW]  {case_id} only in branch")
            continue
        if n is None:
            print(f"[GONE] {case_id} only in baseline")
            continue
        b_got = b.get("got") or "(none)"
        n_got = n.get("got") or "(none)"
        b_pass = b["passed"]
        n_pass = n["passed"]
        if b_pass and n_pass:
            same_pass.append(case_id)
        elif not b_pass and not n_pass:
            same_fail.append((case_id, b["expected"], b_got, n_got))
        elif n_pass and not b_pass:
            wins.append((case_id, b_got, n_got))
        elif b_pass and not n_pass:
            regressions.append((case_id, b_got, n_got))
        elif b_got != n_got:
            routing_changed.append((case_id, b_got, n_got))

    def hdr(label: str) -> None:
        print(f"\n=== {label} ===")

    if wins:
        hdr(f"WINS ({len(wins)}) — branch passes, baseline failed")
        for case_id, b_got, n_got in wins:
            print(f"  {case_id}: {b_got!r} -> {n_got!r}")

    if regressions:
        hdr(f"REGRESSIONS ({len(regressions)}) — baseline passed, branch fails")
        for case_id, b_got, n_got in regressions:
            print(f"  {case_id}: {b_got!r} -> {n_got!r}")

    if routing_changed:
        hdr(f"ROUTING CHANGED, BOTH STILL PASS ({len(routing_changed)})")
        for case_id, b_got, n_got in routing_changed:
            print(f"  {case_id}: {b_got!r} -> {n_got!r}")

    if same_fail:
        hdr(f"STILL FAILING ({len(same_fail)}) — broken on both")
        for case_id, expected, b_got, n_got in same_fail:
            print(f"  {case_id}: expected {expected!r}; baseline={b_got!r}, branch={n_got!r}")

    print()
    print(
        f"Summary: {len(wins)} wins, {len(regressions)} regressions, "
        f"{len(same_pass)} unchanged passes, {len(same_fail)} unchanged fails."
    )

    return 1 if regressions else 0


if __name__ == "__main__":
    sys.exit(main())
