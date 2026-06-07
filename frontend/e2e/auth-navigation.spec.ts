import { test, expect } from "@playwright/test";

test.describe("Auth and History navigation", () => {
  test("should redirect to login when accessing history unauthenticated", async ({ page }) => {
    await page.goto("/history");
    await expect(page).toHaveURL(/.*login/);
  });

  test("should redirect to login when accessing records unauthenticated", async ({ page }) => {
    await page.goto("/records");
    await expect(page).toHaveURL(/.*login/);
  });

  test("should show guest message on home page", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Đăng nhập để lưu lịch sử scan")).toBeVisible();
  });
});
