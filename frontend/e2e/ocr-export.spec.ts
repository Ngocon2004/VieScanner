import { expect, test } from "@playwright/test";

import { exportExcel, uploadMockImages, waitForExtractedForm } from "./helpers";

test("upload -> OCR -> export Excel", async ({ page }) => {
  const apiCalls: Array<{ path: string; status: number }> = [];
  page.on("response", (response) => {
    const url = response.url();
    if (!url.includes("/api/")) return;
    const path = new URL(url).pathname;
    if (path.endsWith("/jobs") || path.endsWith("/export-list")) {
      apiCalls.push({ path, status: response.status() });
    }
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Trích xuất thông tin CCCD" })).toBeVisible();

  await uploadMockImages(page, 2);
  await waitForExtractedForm(page);

  const suggestedFilename = await exportExcel(page);
  expect(suggestedFilename.toLowerCase()).toContain(".xlsx");

  expect(apiCalls.some((c) => c.path.endsWith("/jobs") && c.status === 202)).toBeTruthy();
  expect(apiCalls.some((c) => c.path.endsWith("/export-list") && c.status === 200)).toBeTruthy();
});
