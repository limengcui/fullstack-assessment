export interface SKU {
  id: string;
  color: string;
  size: string;
  price: number;
  stock: number;
  image: string;
}
export interface Product {
  id: string;
  name: string;
  description: string;
  currency: string;
  options: { color: string[]; size: string[] };
  skus: SKU[];
}
export interface Cart {
  total_item_count: number;
  total_price: number;
  currency: string;
  items: { sku_id: string; quantity: number }[];
}
export const resolveSKU = (skus: SKU[], color: string, size: string) =>
  skus.find((s) => s.color === color && s.size === size);
export const money = (cents: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(
    cents / 100,
  );
