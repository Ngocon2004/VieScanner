import { expect, type Page } from "@playwright/test";
import path from "node:path";

const SAMPLE_IMAGE_PATH = path.resolve(__dirname, "./fixtures/mock-cccd.png");

export async function uploadMockImage(page: Page): Promise<void> {
  const fileInput = page.locator('input[type="file"]').first();
  const previewImage = page.getByAltText("CCCD Preview");

  await expect(fileInput).toBeAttached();
  await page.waitForLoadState("networkidle");
  await fileInput.setInputFiles(SAMPLE_IMAGE_PATH);

  if (!(await previewImage.isVisible().catch(() => false))) {
    // In production build hydration may finish after first setInputFiles.
    await page.waitForTimeout(300);
    await fileInput.setInputFiles(SAMPLE_IMAGE_PATH);
  }
  await expect(previewImage).toBeVisible();
}

export async function waitForExtractedForm(page: Page): Promise<void> {
  await expect(page.locator('input[name="id_number"]')).toHaveValue("001202000123", {
    timeout: 30_000,
  });
  await expect(page.locator('input[name="full_name"]')).not.toHaveValue("", {
    timeout: 30_000,
  });
}

export async function exportExcel(page: Page): Promise<string> {
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: /excel/i }).click();
  const download = await downloadPromise;
  return download.suggestedFilename();
}
