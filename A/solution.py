"""Single-SKU ledger. Malformed events do not consume their IDs."""

import sys


class Ledger:
    def __init__(self, stock):
        if type(stock) is not int or not 0 <= stock <= 10**12:
            raise ValueError("invalid stock")
        self.on_hand, self.reserved = stock, 0
        self.orders, self.events = {}, set()

    def process(self, line):
        parts = line.split()
        status = "REJECTED"
        if not parts or parts[0] not in {"RESERVE", "RELEASE", "SHIP", "RESTOCK"}:
            return status, self.on_hand, self.reserved
        op = parts[0]
        if len(parts) != (3 if op == "RESTOCK" else 4):
            return status, self.on_hand, self.reserved
        if not all(x.isascii() and x.isprintable() for x in parts):
            return status, self.on_hand, self.reserved
        if not parts[-1].isascii() or not parts[-1].isdigit():
            return status, self.on_hand, self.reserved
        digits = parts[-1].lstrip("0")
        if len(digits) > 13:
            return status, self.on_hand, self.reserved
        qty = int(digits or "0")
        if not 1 <= qty <= 10**12:
            return status, self.on_hand, self.reserved
        event = parts[1]
        if event in self.events:
            return "DUPLICATE", self.on_hand, self.reserved
        self.events.add(event)
        order = parts[2] if op != "RESTOCK" else None
        current = self.orders.get(order, 0)
        if op == "RESTOCK":
            self.on_hand += qty
            status = "OK"
        elif op == "RESERVE" and qty <= self.on_hand - self.reserved:
            self.orders[order] = current + qty
            self.reserved += qty
            status = "OK"
        elif op in {"RELEASE", "SHIP"} and qty <= current:
            self.reserved -= qty
            if current == qty:
                del self.orders[order]
            else:
                self.orders[order] = current - qty
            if op == "SHIP":
                self.on_hand -= qty
            status = "OK"
        return status, self.on_hand, self.reserved


def main():
    try:
        s, n = map(int, sys.stdin.readline().split())
        if not 1 <= n <= 200_000:
            raise ValueError("invalid command count")
        ledger = Ledger(s)
        for _ in range(n):
            print(*ledger.process(sys.stdin.readline()))
        print("OPEN", len(ledger.orders))
        for order, qty in sorted(ledger.orders.items()):
            print(order, qty)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
