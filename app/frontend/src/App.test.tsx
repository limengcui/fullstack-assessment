import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import App from "./App";
import { api, ApiError } from "./api";
import { resolveSKU, type Product } from "./domain";
vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, api: { product: vi.fn(), cart: vi.fn(), add: vi.fn() } };
});
const product: Product = {
  id: "1",
  name: "The Everyday Tee",
  description: "Cotton",
  currency: "USD",
  options: { color: ["Ocean", "Sand"], size: ["S", "M"] },
  skus: [
    {
      id: "ocean-s",
      color: "Ocean",
      size: "S",
      price: 4900,
      stock: 3,
      image: "/o.svg",
    },
    {
      id: "ocean-m",
      color: "Ocean",
      size: "M",
      price: 5900,
      stock: 1,
      image: "/m.svg",
    },
    {
      id: "sand-s",
      color: "Sand",
      size: "S",
      price: 4900,
      stock: 0,
      image: "/s.svg",
    },
  ],
};
const cart = {
  items: [],
  total_item_count: 0,
  total_price: 0,
  currency: "USD",
};
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.product).mockResolvedValue(structuredClone(product));
  vi.mocked(api.cart).mockResolvedValue(cart);
});
async function choose() {
  render(<App />);
  await screen.findByText("The Everyday Tee", { selector: "h1" });
  fireEvent.click(screen.getByRole("button", { name: "Ocean" }));
  fireEvent.click(screen.getByRole("button", { name: /^S$/ }));
}
test("resolves SKU and distinguishes absent combination", () => {
  expect(resolveSKU(product.skus, "Ocean", "M")?.id).toBe("ocean-m");
  expect(resolveSKU(product.skus, "Sand", "M")).toBeUndefined();
});
test("variant changes price and clamps quantity", async () => {
  await choose();
  fireEvent.change(screen.getByLabelText("Quantity"), {
    target: { value: "3" },
  });
  fireEvent.click(screen.getByRole("button", { name: /^M$/ }));
  expect(screen.getByText("$59.00")).toBeInTheDocument();
  expect(screen.getByLabelText("Quantity")).toHaveValue(1);
  expect(screen.getByRole("button", { name: "Sand" })).toBeDisabled();
});
test("rapid duplicate click submits once", async () => {
  let finish!: (value: Awaited<ReturnType<typeof api.add>>) => void;
  vi.mocked(api.add).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  await choose();
  const button = screen.getByRole("button", { name: /Add to bag/ });
  fireEvent.click(button);
  fireEvent.click(button);
  expect(api.add).toHaveBeenCalledTimes(1);
  finish({
    cart: { ...cart, total_item_count: 1 },
    sku_id: "ocean-s",
    available_quantity: 2,
  });
  await screen.findByText("Added to your bag.");
});
test("network retry preserves key and input", async () => {
  vi.mocked(api.add)
    .mockRejectedValueOnce(new ApiError("Network interrupted", "NETWORK_ERROR"))
    .mockResolvedValueOnce({ cart, sku_id: "ocean-s", available_quantity: 2 });
  await choose();
  fireEvent.click(screen.getByRole("button", { name: /Add to bag/ }));
  await screen.findByText("Network interrupted");
  fireEvent.click(screen.getByRole("button", { name: /Retry safely/ }));
  await screen.findByText("Added to your bag.");
  expect(vi.mocked(api.add).mock.calls[0]).toEqual(
    vi.mocked(api.add).mock.calls[1],
  );
});
test("product loading failure is retryable", async () => {
  vi.mocked(api.product)
    .mockRejectedValueOnce(new Error("Offline"))
    .mockResolvedValueOnce(product);
  render(<App />);
  await screen.findByText("Offline");
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  await screen.findByText("The Everyday Tee", { selector: "h1" });
});

test("late initial cart response cannot overwrite successful add", async () => {
  let finish!: (value: typeof cart) => void;
  vi.mocked(api.cart).mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  vi.mocked(api.add).mockResolvedValue({
    cart: { ...cart, total_item_count: 1 },
    sku_id: "ocean-s",
    available_quantity: 2,
  });
  await choose();
  fireEvent.click(screen.getByRole("button", { name: /Add to bag/ }));
  await screen.findByText("Added to your bag.");
  finish(cart);
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Refresh shopping bag" }),
    ).toHaveTextContent("BAG (1)"),
  );
});
