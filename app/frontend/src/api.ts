import type { Cart, Product } from "./domain";
export class ApiError extends Error {
  constructor(
    message: string,
    public code: string,
    public available?: number,
  ) {
    super(message);
  }
}
const cartId = () => {
  let id = localStorage.getItem("cart-id");
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("cart-id", id);
  }
  return id;
};
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        "X-Cart-ID": cartId(),
        ...init.headers,
      },
      signal: AbortSignal.timeout(15000),
    });
  } catch {
    throw new ApiError(
      "Connection interrupted. Retry to safely check this request.",
      "NETWORK_ERROR",
    );
  }
  let data: T & {
    error?: {
      message?: string;
      code?: string;
      details?: { available?: number };
    };
  };
  try {
    data = await response.json();
  } catch {
    throw new ApiError(
      "The server response was interrupted. Retry safely.",
      "SERVER_ERROR",
    );
  }
  if (!response.ok)
    throw new ApiError(
      data.error?.message ?? "Request failed.",
      data.error?.code ?? "SERVER_ERROR",
      data.error?.details?.available,
    );
  return data as T;
}
export const api = {
  product: () => request<Product>("/api/products/1"),
  cart: () => request<Cart>("/api/cart"),
  add: (sku_id: string, quantity: number, key: string) =>
    request<{ cart: Cart; sku_id: string; available_quantity: number }>(
      "/api/cart/items",
      {
        method: "POST",
        headers: { "Idempotency-Key": key },
        body: JSON.stringify({ sku_id, quantity }),
      },
    ),
};
