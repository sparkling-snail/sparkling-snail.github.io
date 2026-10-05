"""
Balls-into-bins simulation for "The Power of Two Choices".

Throw n requests at n servers. For each request, sample d servers uniformly
at random and send it to the least-loaded one (d = 1 is plain random routing).
Report the load on the busiest server, and the fraction of servers carrying
at least i requests.

Usage:  python3 simulate.py          (writes results.json)
Needs:  numpy
"""
import json
import random

import numpy as np

SIZES = [1_000, 10_000, 100_000, 1_000_000]
CHOICES = [1, 2, 3]
TRIALS = 5
SEED = 42


def throw(n: int, d: int, rng: random.Random) -> list[int]:
    """Place n requests on n servers using the d-choice rule."""
    loads = [0] * n
    rand = rng.randrange
    if d == 1:
        for _ in range(n):
            loads[rand(n)] += 1
    elif d == 2:
        for _ in range(n):
            a, b = rand(n), rand(n)
            loads[a if loads[a] <= loads[b] else b] += 1
    else:
        for _ in range(n):
            best = rand(n)
            for _ in range(d - 1):
                c = rand(n)
                if loads[c] < loads[best]:
                    best = c
            loads[best] += 1
    return loads


def tail(loads: list[int]) -> list[float]:
    """tail[i] = fraction of servers with load >= i."""
    counts = np.bincount(loads)
    at_least = counts[::-1].cumsum()[::-1]
    return (at_least / len(loads)).tolist()


def main() -> None:
    rng = random.Random(SEED)
    max_load = {d: [] for d in CHOICES}
    for n in SIZES:
        for d in CHOICES:
            runs = [max(throw(n, d, rng)) for _ in range(TRIALS)]
            max_load[d].append({"n": n, "mean": float(np.mean(runs)), "runs": runs})
            print(f"n={n:>9,}  d={d}  max load per run: {runs}")

    big = SIZES[-1]
    tails = {d: tail(throw(big, d, rng)) for d in (1, 2)}

    with open("results.json", "w") as f:
        json.dump({"max_load": max_load, "tail_n": big, "tails": tails}, f, indent=2)


if __name__ == "__main__":
    main()
