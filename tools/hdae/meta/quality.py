# ruff: noqa: I001
from __future__ import annotations

from typing import Dict, Iterable, Tuple

import argparse


Quality = Tuple[int, int, int, int]


def compute_quality(stats: Dict[str, int]) -> Quality:
    """Compute the quality tuple.

    Dimensions (higher is better, lexicographic order):
    (-L1_violations, -L2_misses, -lint_type_fails, +perf_async_wins)
    """
    return (
        -int(stats.get("l1_violations", 0)),
        -int(stats.get("l2_misses", 0)),
        -int(stats.get("lint_type_fails", 0)),
        int(stats.get("perf_async_wins", 0)),
    )


def dominates(q1: Quality, q2: Quality) -> bool:
    """Return True iff q1 >= q2 under lexicographic ordering."""
    return q1 >= q2


def strictly_better(q1: Quality, q2: Quality) -> bool:
    """Return True iff q1 > q2 under lexicographic ordering."""
    return q1 > q2


def _monotonicity_cases() -> Iterable[bool]:
    # Case 1: fewer L1 violations strictly improves
    a = compute_quality({"l1_violations": 2})
    b = compute_quality({"l1_violations": 1})
    yield dominates(b, a) and strictly_better(b, a)

    # Case 2: tie on L1, compare L2
    c = compute_quality({"l1_violations": 1, "l2_misses": 3})
    d = compute_quality({"l1_violations": 1, "l2_misses": 2})
    yield dominates(d, c) and strictly_better(d, c)

    # Case 3: tie on L1/L2, compare lint/type failures
    e = compute_quality({"l1_violations": 0, "l2_misses": 0, "lint_type_fails": 5})
    f = compute_quality({"l1_violations": 0, "l2_misses": 0, "lint_type_fails": 4})
    yield dominates(f, e) and strictly_better(f, e)

    # Case 4: tie on first three, more perf wins is better
    g = compute_quality({})
    h = compute_quality({"perf_async_wins": 1})
    yield dominates(h, g) and strictly_better(h, g)

    # Case 5: regression should not dominate
    yield not dominates(a, b)


def _selftest() -> bool:
    return all(_monotonicity_cases())


def main() -> int:
    ap = argparse.ArgumentParser(prog="hdae-quality", description="H-DAE quality lattice utils")
    ap.add_argument("--selftest", action="store_true", help="Run built-in monotonicity tests")
    args = ap.parse_args()
    if args.selftest:
        ok = _selftest()
        print("quality selftest:", "PASS" if ok else "FAIL")
        return 0 if ok else 2
    ap.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
