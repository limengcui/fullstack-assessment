import { test, expect } from "@playwright/test";
for (const width of [1280, 375]) {
  test(`product and cart at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "The Everyday Tee" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Ocean", exact: true }).click();
    await page.getByRole("button", { name: "S", exact: true }).click();
    await expect(page.getByText("$49.00", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: /Add to bag/ }).click();
    await expect(page.getByText("Added to your bag.")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Refresh shopping bag" }),
    ).toContainText("BAG (1)");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: `test-results/product-${width}.png`,
      fullPage: true,
    });
    expect(errors).toEqual([]);
  });
}
test("stock conflict recovers without refresh", async ({ page, request }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Ocean", exact: true }).click();
  await page.getByRole("button", { name: "M", exact: true }).click();
  const response = await request.post("/api/cart/items", {
    headers: { "X-Cart-ID": "external", "Idempotency-Key": "last-unit" },
    data: { sku_id: "ocean-m", quantity: 1 },
  });
  expect(response.ok()).toBe(true);
  await page.getByRole("button", { name: /Add to bag/ }).click();
  await expect(page.getByText("Out of stock.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "S", exact: true }).click();
  await expect(page.getByRole("button", { name: /Add to bag/ })).toBeEnabled();
});
