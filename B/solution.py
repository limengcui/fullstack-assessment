"""Bounded allocation DP with sliding minima: O(W Q) transitions."""

import sys
from collections import deque


def optimise(warehouses, quantity):
    if not 1 <= quantity <= 2000 or not 1 <= len(warehouses) <= 30:
        raise ValueError("invalid dimensions")
    ids = [w[0] for w in warehouses]
    if len(set(ids)) != len(ids) or any(
        not x or not x.isascii() or any(c.isspace() for c in x) for x in ids
    ):
        raise ValueError("invalid warehouse IDs")
    if any(
        not (0 <= s <= 2000 and 0 <= f <= 10**6 and 0 <= u <= 10**6)
        for _, s, f, u in warehouses
    ):
        raise ValueError("invalid warehouse data")
    # Descending IDs let us prepend a warehouse. For tied prior objectives,
    # larger prior quantity means smaller current allocation (lexicographically).
    dp = [None] * (quantity + 1)
    dp[0] = (0, 0, ())
    for wid, stock, fixed, unit in sorted(warehouses, reverse=True):
        next_dp = dp.copy()
        window = deque()
        for q in range(1, quantity + 1):
            t = q - 1
            if dp[t] is not None:
                key = (dp[t][0], dp[t][1] - t * unit, -t)
                while window and window[-1][1] >= key:
                    window.pop()
                window.append((t, key))
            while window and window[0][0] < q - stock:
                window.popleft()
            if window:
                t = window[0][0]
                count, cost, plan = dp[t]
                candidate = (
                    count + 1,
                    cost + fixed + (q - t) * unit,
                    ((wid, q - t),) + plan,
                )
                if next_dp[q] is None or candidate < next_dp[q]:
                    next_dp[q] = candidate
        dp = next_dp
    return dp[quantity]


def main():
    try:
        w, q = map(int, sys.stdin.readline().split())
        rows = []
        for _ in range(w):
            wid, s, f, u = sys.stdin.readline().split()
            rows.append((wid, int(s), int(f), int(u)))
        result = optimise(rows, q)
        if result is None:
            print(-1)
        else:
            count, cost, plan = result
            print(count, cost)
            for wid, qty in plan:
                print(wid, qty)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
