import { expect, test } from "@playwright/test";

import { exportExcel, uploadMockImage, waitForExtractedForm } from "./helpers";

test("upload -> OCR -> export Excel", async ({ page }) => {
  const apiCalls: Array<{ path: string; status: number }> = [];
  page.on("response", (response) => {
    const url = response.url();
    if (!url.includes("/api/")) return;
    const path = new URL(url).pathname;
    if (path.endsWith("/extract") || path.endsWith("/export")) {
      apiCalls.push({ path, status: response.status() });
    }
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Trích xuất thông tin CCCD" })).toBeVisible();

  await uploadMockImage(page);
  await waitForExtractedForm(page);

  const suggestedFilename = await exportExcel(page);
  expect(suggestedFilename.toLowerCase()).toContain(".xlsx");

  expect(apiCalls.some((c) => c.path.endsWith("/extract") && c.status === 200)).toBeTruthy();
  expect(apiCalls.some((c) => c.path.endsWith("/export") && c.status === 200)).toBeTruthy();
});
