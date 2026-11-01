import random
from itertools import product

from A.solution import Ledger
from B.solution import optimise


def test_ledger_example():
    ledger = Ledger(10)
    lines = [
        "RESERVE e1 o100 4",
        "RESERVE e2 o200 7",
        "SHIP e3 o100 2",
        "RELEASE e4 o100 2",
        "RESTOCK e5 3",
        "RESERVE e2 o999 1",
    ]
    assert [ledger.process(x) for x in lines] == [
        ("OK", 10, 4),
        ("REJECTED", 10, 4),
        ("OK", 8, 2),
        ("OK", 8, 0),
        ("OK", 11, 0),
        ("DUPLICATE", 11, 0),
    ]
    assert ledger.orders == {}


def test_malformed_is_atomic():
    ledger = Ledger(4)
    for line in [
        "RESERVE bad o 0",
        "RESERVE bad o -2",
        "RESERVE bad o 1 extra",
        "BOGUS bad o 1",
        "RESERVE bad o １",
    ]:
        assert ledger.process(line) == ("REJECTED", 4, 0)
    assert ledger.process("RESERVE bad o 4") == ("OK", 4, 4)
    assert ledger.process("SHIP s o 5") == ("REJECTED", 4, 4)
    assert ledger.process("SHIP s o 1")[0] == "DUPLICATE"
    assert ledger.process("SHIP new o 4") == ("OK", 0, 0)


def brute(rows, q):
    results = []
    for allocation in product(*(range(s + 1) for _, s, _, _ in rows)):
        if sum(allocation) == q:
            plan = tuple(sorted((rows[i][0], n) for i, n in enumerate(allocation) if n))
            cost = sum(
                rows[i][2] + rows[i][3] * n for i, n in enumerate(allocation) if n
            )
            results.append((len(plan), cost, plan))
    return min(results, default=None)


def test_dp_against_exhaustive():
    rng = random.Random(42)
    for _ in range(300):
        rows = [
            (chr(65 + i), rng.randrange(4), rng.randrange(4), rng.randrange(4))
            for i in range(rng.randrange(1, 6))
        ]
        rng.shuffle(rows)
        q = rng.randrange(1, 9)
        assert optimise(rows, q) == brute(rows, q)


def test_dp_maximum_and_ties():
    assert optimise([("AU", 5, 8, 2), ("CN", 7, 20, 1), ("US", 4, 3, 4)], 7) == (
        1,
        27,
        (("CN", 7),),
    )
    assert optimise([("A", 0, 0, 0)], 1) is None
    result = optimise([(f"W{i:02}", 2000, 0, 0) for i in range(30)], 2000)
    assert result == (1, 0, (("W00", 2000),))
    assert optimise([("A", 2, 0, 0), ("B", 2, 0, 0)], 3) == (2, 0, (("A", 1), ("B", 2)))


def test_ledger_large_malformed_and_invariants():
    ledger = Ledger(100)
    assert ledger.process("RESERVE huge o " + "9" * 5000) == ("REJECTED", 100, 0)
    rng = random.Random(17)
    for i in range(1000):
        op = rng.choice(["RESERVE", "RELEASE", "SHIP", "RESTOCK"])
        order = "o" + str(rng.randrange(10))
        qty = rng.randrange(1, 12)
        line = f"{op} {i} {qty}" if op == "RESTOCK" else f"{op} {i} {order} {qty}"
        ledger.process(line)
        assert 0 <= ledger.reserved <= ledger.on_hand
        assert ledger.reserved == sum(ledger.orders.values())
        assert all(q > 0 for q in ledger.orders.values())
