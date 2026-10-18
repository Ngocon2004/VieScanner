import { expect, type Page } from "@playwright/test";
import path from "node:path";

const SAMPLE_IMAGE_PATH = path.resolve(__dirname, "./fixtures/mock-cccd.png");

export async function uploadMockImages(page: Page, count = 1): Promise<void> {
  const fileInput = page.locator('input[type="file"]').first();
  const selectedText = page.getByText(new RegExp(`Đã chọn ${count} ảnh`, "i"));
  const files = Array.from({ length: count }, () => SAMPLE_IMAGE_PATH);

  await expect(fileInput).toBeAttached();
  await page.waitForLoadState("networkidle");
  await fileInput.setInputFiles(files);

  try {
    await expect(selectedText).toBeVisible({ timeout: 1_500 });
  } catch {
    // In production build hydration may finish after first setInputFiles.
    await fileInput.setInputFiles(files);
    await expect(selectedText).toBeVisible();
  }
}

export async function uploadMockImage(page: Page): Promise<void> {
  await uploadMockImages(page, 1);
}

export async function waitForBatchResults(page: Page): Promise<void> {
  await expect(page.getByRole("heading", { name: "Bước 2: Kết quả phân loại" })).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByText(/^Đang xử lý \d+\/\d+ ảnh$/)).toHaveCount(0, {
    timeout: 30_000,
  });
  await expect(page.getByText(/^\d+ đã trích xuất$/i)).toBeVisible({
    timeout: 30_000,
  });
}

export async function waitForExtractedForm(page: Page): Promise<void> {
  await waitForBatchResults(page);
  await expect(
    page.getByRole("heading", { name: /Bước 3: Danh sách đã quét/ }),
  ).toBeVisible({ timeout: 30_000 });
  await expect(page.getByLabel("Số CCCD dòng 1")).toHaveValue("001202000123", {
    timeout: 30_000,
  });
  await expect(page.getByLabel("Họ và tên dòng 1")).not.toHaveValue("", {
    timeout: 30_000,
  });
}

export async function exportExcel(page: Page): Promise<string> {
  const downloadPromise = page.waitForEvent("download");
  const button = page.getByRole("button", { name: /Xuất Excel \(\d+ người\)/ });
  await button.click();
  // Còn ô OCR chưa chắc chắn: nút chuyển sang "Vẫn xuất Excel" và cần bấm xác nhận lần 2.
  const confirm = page.getByRole("button", { name: /Vẫn xuất Excel/ });
  if (await confirm.isVisible().catch(() => false)) await confirm.click();
  const download = await downloadPromise;
  await download.path();
  return download.suggestedFilename();
}
