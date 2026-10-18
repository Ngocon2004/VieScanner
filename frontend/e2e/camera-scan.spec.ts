import { expect, test } from "@playwright/test";

test("camera tab captures a frame and submits it as a camera job", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "Quét camera" }).click();
  await page.getByLabel("Tự chụp khi khung hình đạt").uncheck();

  const shutter = page.getByRole("button", { name: "Chụp", exact: true });
  await expect(shutter).toBeEnabled({ timeout: 15_000 });
  await shutter.click();

  const jobResponse = page.waitForResponse(
    (r) => r.request().method() === "POST" && new URL(r.url()).pathname.endsWith("/jobs"),
  );
  await page.getByRole("button", { name: "Xử lý 1 ảnh" }).click();
  const response = await jobResponse;
  expect(response.status()).toBe(202);
  expect((await response.json()).source).toBe("camera");

  await expect(page.getByRole("heading", { name: "Bước 2: Kết quả phân loại" })).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText(/^Đang xử lý \d+\/\d+ ảnh$/)).toHaveCount(0, { timeout: 30_000 });
});
