import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { money, resolveSKU, type Product, type Cart } from "./domain";
export default function App() {
  const [product, setProduct] = useState<Product>();
  const [loadError, setLoadError] = useState("");
  const [cart, setCart] = useState<Cart>();
  const [color, setColor] = useState("");
  const [size, setSize] = useState("");
  const [quantity, setQuantity] = useState(1);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [uncertain, setUncertain] = useState(false);
  const [cartError, setCartError] = useState(false);
  const cartVersion = useRef(0);
  const productVersion = useRef(0);
  const lock = useRef(false);
  const pending = useRef<{ sku: string; quantity: number; key: string } | null>(
    null,
  );
  async function load() {
    const version = ++productVersion.current;
    setLoadError("");
    try {
      const result = await api.product();
      if (version === productVersion.current) setProduct(result);
    } catch (e) {
      if (version === productVersion.current)
        setLoadError((e as Error).message);
    }
  }
  async function loadCart() {
    const version = ++cartVersion.current;
    try {
      const result = await api.cart();
      if (version === cartVersion.current) {
        setCart(result);
        setCartError(false);
      }
    } catch {
      if (version === cartVersion.current) setCartError(true);
    }
  }
  useEffect(() => {
    void load();
    void loadCart();
  }, []);
  const sku = product ? resolveSKU(product.skus, color, size) : undefined;
  useEffect(() => {
    setQuantity((q) => Math.max(1, Math.min(q, sku?.stock || 1)));
  }, [sku?.id, sku?.stock]);
  function select(kind: "color" | "size", value: string) {
    if (kind === "color") setColor(value);
    else setSize(value);
    setMessage("");
  }
  async function add() {
    if (lock.current || !sku || sku.stock < 1) return;
    lock.current = true;
    setBusy(true);
    setMessage("");
    const operation = pending.current ?? {
      sku: sku.id,
      quantity,
      key: crypto.randomUUID(),
    };
    pending.current = operation;
    try {
      const result = await api.add(
        operation.sku,
        operation.quantity,
        operation.key,
      );
      cartVersion.current++;
      productVersion.current++;
      setCart(result.cart);
      setCartError(false);
      setProduct((p) =>
        p
          ? {
              ...p,
              skus: p.skus.map((s) =>
                s.id === result.sku_id
                  ? { ...s, stock: result.available_quantity }
                  : s,
              ),
            }
          : p,
      );
      pending.current = null;
      setUncertain(false);
      setMessage("Added to your bag.");
    } catch (e) {
      const err = e as ApiError;
      setMessage(err.message);
      if (
        err.code === "NETWORK_ERROR" ||
        err.code === "INTERNAL_ERROR" ||
        err.code === "SERVER_ERROR"
      ) {
        setUncertain(true);
      } else {
        pending.current = null;
        setUncertain(false);
        if (err.available !== undefined) {
          productVersion.current++;
          setProduct((p) =>
            p
              ? {
                  ...p,
                  skus: p.skus.map((s) =>
                    s.id === operation.sku
                      ? { ...s, stock: err.available! }
                      : s,
                  ),
                }
              : p,
          );
        } else void load();
      }
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  const frozen = busy || uncertain;
  return (
    <>
      <header>
        <a className="brand" href="/">
          FORM<span> / </span>
        </a>
        <span className="header-note">ESSENTIALS, CONSIDERED.</span>
        <button
          className="bag"
          onClick={() => void loadCart()}
          aria-label="Refresh shopping bag"
        >
          BAG ({cart?.total_item_count ?? "—"})
        </button>
      </header>
      <main>
        {!product ? (
          <section className="loading" role="status">
            {loadError ? (
              <>
                <h1>We couldn’t load this piece.</h1>
                <p>{loadError}</p>
                <button onClick={() => void load()}>Try again</button>
              </>
            ) : (
              "Finding your next everyday essential…"
            )}
          </section>
        ) : (
          <>
            <nav aria-label="Breadcrumb">
              Collection / Essentials / <strong>{product.name}</strong>
            </nav>
            <div className="product-grid">
              <section className="gallery" aria-label="Product image">
                <div className="image-label">THE EVERYDAY COLLECTION · 01</div>
                <img
                  src={
                    sku?.image ??
                    `/images/${(color || "Ocean").toLowerCase()}.svg`
                  }
                  alt={`${color || "Ocean"} organic cotton tee`}
                />
                <span className="image-caption">LESS, BUT BETTER.</span>
              </section>
              <section className="details">
                <p className="eyebrow">MADE FOR THE EVERYDAY</p>
                <h1>{product.name}</h1>
                <p className="price">
                  {sku
                    ? money(sku.price)
                    : `From ${money(Math.min(...product.skus.map((s) => s.price)))}`}
                </p>
                <p className="description">{product.description}</p>
                <fieldset disabled={frozen}>
                  <legend>
                    Color <span>{color || "Choose a color"}</span>
                  </legend>
                  <div className="choices">
                    {product.options.color.map((c) => {
                      const available = product.skus.some(
                        (s) =>
                          s.color === c &&
                          (!size || s.size === size) &&
                          s.stock > 0,
                      );
                      return (
                        <button
                          key={c}
                          aria-pressed={color === c}
                          disabled={!available}
                          className={color === c ? "selected" : ""}
                          onClick={() => select("color", c)}
                        >
                          {c}
                        </button>
                      );
                    })}
                  </div>
                </fieldset>
                <fieldset disabled={frozen}>
                  <legend>
                    Size <span>{size || "Choose your size"}</span>
                  </legend>
                  <div className="choices">
                    {product.options.size.map((s) => {
                      const available = product.skus.some(
                        (v) =>
                          v.size === s &&
                          (!color || v.color === color) &&
                          v.stock > 0,
                      );
                      return (
                        <button
                          key={s}
                          aria-pressed={size === s}
                          disabled={!available}
                          className={size === s ? "selected" : ""}
                          onClick={() => select("size", s)}
                        >
                          {s}
                        </button>
                      );
                    })}
                  </div>
                </fieldset>
                <p className="stock" role="status">
                  {!color || !size
                    ? "Select color and size to see availability."
                    : !sku
                      ? "This combination is unavailable."
                      : sku.stock === 0
                        ? "Out of stock."
                        : `${sku.stock} available · Ready to ship`}
                </p>
                <div className="purchase">
                  <label>
                    Quantity
                    <input
                      aria-label="Quantity"
                      type="number"
                      min={1}
                      max={sku?.stock || 1}
                      value={quantity}
                      disabled={frozen || !sku || sku.stock === 0}
                      onChange={(e) =>
                        setQuantity(
                          Math.max(
                            1,
                            Math.min(
                              sku?.stock || 1,
                              Number(e.target.value) || 1,
                            ),
                          ),
                        )
                      }
                    />
                  </label>
                  <button
                    className="add"
                    disabled={busy || !sku || (!uncertain && sku.stock < 1)}
                    onClick={() => void add()}
                  >
                    {busy
                      ? "Adding…"
                      : uncertain
                        ? "Retry safely"
                        : "Add to bag"}
                    <span aria-hidden="true"> ↗</span>
                  </button>
                </div>
                <p className="feedback" role="status" aria-live="polite">
                  {message}
                </p>
                {uncertain && (
                  <p className="hint">
                    Your selection is held until the request is resolved. Retry
                    uses the same request key.
                  </p>
                )}
                {cartError && (
                  <p role="alert">
                    Bag could not be loaded.{" "}
                    <button onClick={() => void loadCart()}>Retry bag</button>
                  </p>
                )}
                <div className="benefits">
                  <p>↗ Complimentary shipping on orders $100+</p>
                  <p>○ 100% organic cotton · Made to last</p>
                </div>
                <details>
                  <summary>Materials & care</summary>
                  <p>
                    Wash cool with similar colors. Air dry. Designed for a
                    softer footprint.
                  </p>
                </details>
              </section>
            </div>
          </>
        )}
      </main>
      <footer>
        <span>FORM / A quieter kind of wardrobe.</span>
        <span>QUALITY OVER QUANTITY.</span>
      </footer>
    </>
  );
}
