import path from "node:path";

import { expect, test, type Worker } from "@playwright/test";

const LARGE_PNG = path.resolve(__dirname, "./fixtures/large-gradient.png");

test("large images are resized to JPEG inside a Web Worker before upload", async ({ page }) => {
  const workers: Worker[] = [];
  page.on("worker", (w) => workers.push(w));

  const jobResponse = page.waitForResponse(
    (r) => r.request().method() === "POST" && new URL(r.url()).pathname.endsWith("/jobs"),
  );

  await page.goto("/");
  await page.waitForLoadState("networkidle");
  await page.locator('input[type="file"]').first().setInputFiles(LARGE_PNG);

  const job = await (await jobResponse).json();
  expect(job.items[0].filename).toBe("large-gradient.jpg");

  expect(workers.length).toBeGreaterThan(0);
  const outputType = await workers[0]!.evaluate(async () => {
    // `run`/`plan` là khai báo const ở top-level của script worker (global lexical scope).
    const [run, plan] = new Function("return [run, plan]")() as [
      (req: unknown, plan: unknown) => Promise<{ blob?: Blob; error?: string }>,
      unknown,
    ];
    const canvas = new OffscreenCanvas(3000, 10);
    canvas.getContext("2d")?.fillRect(0, 0, 3000, 10);
    const source = await canvas.convertToBlob();
    const out = await run(
      { id: 1, file: source, maxSidePx: 2000, minCompressBytes: 0, jpegQuality: 0.9 },
      plan,
    );
    return out.blob?.type ?? out.error;
  });
  expect(outputType).toBe("image/jpeg");
});
