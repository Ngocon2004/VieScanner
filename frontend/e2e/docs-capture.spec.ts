import fs from "node:fs/promises";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { exportExcel, uploadMockImages, waitForBatchResults, waitForExtractedForm } from "./helpers";

const SCREENSHOT_DIR = path.resolve(
  process.env.DOCS_SCREENSHOT_DIR ??
    path.join(process.cwd(), "test-results/docs-screenshots"),
);

test("capture documentation screenshots", async ({ page }) => {
  const networkCalls: Array<{ method: string; path: string; status: number }> = [];
  page.on("response", async (response) => {
    const url = response.url();
    if (!url.includes("/api/")) return;
    const parsed = new URL(url);
    if (!parsed.pathname.endsWith("/jobs") && !parsed.pathname.endsWith("/export-list")) return;
    const req = response.request();
    networkCalls.push({
      method: req.method(),
      path: parsed.pathname,
      status: response.status(),
    });
  });

  await fs.mkdir(SCREENSHOT_DIR, { recursive: true });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Trích xuất thông tin CCCD" })).toBeVisible();
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, "upload-page.png"),
    fullPage: true,
  });

  await uploadMockImages(page, 2);
  await waitForBatchResults(page);
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, "batch-results.png"),
    fullPage: true,
  });

  await waitForExtractedForm(page);
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, "form-after-ocr.png"),
    fullPage: true,
  });

  const suggestedFilename = await exportExcel(page);
  expect(suggestedFilename.toLowerCase()).toContain(".xlsx");
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, "after-export.png"),
    fullPage: true,
  });

  await fs.writeFile(
    path.join(SCREENSHOT_DIR, "api-calls.json"),
    `${JSON.stringify({ calls: networkCalls }, null, 2)}\n`,
    "utf-8",
  );
});
