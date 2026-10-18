import { z } from "zod";

import { apiRequest } from "@/lib/api";

// Đồng bộ với backend `app/models/admin.py`.
export const adminOverviewSchema = z.object({
  days: z.number(),
  totals: z.object({
    scans: z.number(),
    succeeded: z.number(),
    failed: z.number(),
    median_duration_ms: z.number().nullable(),
    p90_duration_ms: z.number().nullable(),
    users: z.number(),
    new_users: z.number(),
    exported_scans: z.number(),
    corrections: z.number(),
    active_jobs: z.number(),
  }),
  daily: z.array(z.object({ date: z.string(), success: z.number(), failed: z.number() })),
  errors: z.array(z.object({ code: z.string(), count: z.number() })),
  fields: z.array(
    z.object({
      field: z.string(),
      read: z.number(),
      read_rate: z.number(),
      low_confidence: z.number(),
      corrected: z.number(),
      corrected_rate: z.number(),
    }),
  ),
  jobs: z.record(z.string(), z.number()),
});
export type AdminOverview = z.infer<typeof adminOverviewSchema>;

export const adminSystemSchema = z.object({
  ocr_engine: z.string(),
  engine_ready: z.boolean(),
  pipeline_version: z.string(),
  queue_size: z.number(),
  concurrency: z.number(),
  qr_enabled: z.boolean(),
  cache_enabled: z.boolean(),
  cache_ttl_hours: z.number(),
  scan_retention_days: z.number(),
  job_retention_days: z.number(),
  auth_required: z.boolean(),
});
export type AdminSystem = z.infer<typeof adminSystemSchema>;

export const adminUserSchema = z.object({
  id: z.string(),
  email: z.string(),
  full_name: z.string().nullable(),
  role: z.string(),
  is_active: z.boolean(),
  created_at: z.string(),
  scans: z.number(),
  exported_scans: z.number(),
  last_scan_at: z.string().nullable(),
});
export type AdminUser = z.infer<typeof adminUserSchema>;

export const adminScanSchema = z.object({
  id: z.string(),
  created_at: z.string(),
  user_email: z.string().nullable(),
  status: z.string(),
  ocr_engine: z.string(),
  duration_ms: z.number().nullable(),
  error_code: z.string().nullable(),
  id_number_masked: z.string().nullable(),
  fields_read: z.number(),
  low_confidence_fields: z.number(),
  from_job: z.boolean(),
});
export type AdminScan = z.infer<typeof adminScanSchema>;

export function getAdminOverview(days: number, signal?: AbortSignal): Promise<AdminOverview> {
  return apiRequest(`/admin/overview?days=${days}`, { signal: signal ?? null }, adminOverviewSchema);
}

export function getAdminSystem(signal?: AbortSignal): Promise<AdminSystem> {
  return apiRequest("/admin/system", { signal: signal ?? null }, adminSystemSchema);
}

export function getAdminUsers(query: string, limit: number, signal?: AbortSignal): Promise<AdminUser[]> {
  const q = query.trim() ? `&q=${encodeURIComponent(query.trim())}` : "";
  return apiRequest(`/admin/users?limit=${limit}${q}`, { signal: signal ?? null }, adminUserSchema.array());
}

export function updateAdminUser(
  id: string,
  patch: { role?: "admin" | "user"; is_active?: boolean },
): Promise<AdminUser> {
  return apiRequest(
    `/admin/users/${encodeURIComponent(id)}`,
    { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) },
    adminUserSchema,
  );
}

export function getAdminScans(status: "" | "success" | "failed", signal?: AbortSignal): Promise<AdminScan[]> {
  const filter = status ? `&status=${status}` : "";
  return apiRequest(`/admin/scans?limit=50${filter}`, { signal: signal ?? null }, adminScanSchema.array());
}

// Nhãn tiếng Việt cho mã lỗi/tên trường backend trả về.
export const ERROR_LABELS: Record<string, string> = {
  image_quality_low: "Ảnh không đạt chất lượng",
  ocr_aligner_failed: "Không tìm thấy đủ 4 góc thẻ",
  ocr_detector_failed: "Không phát hiện được chữ",
  ocr_engine_crashed: "Lỗi hệ thống OCR",
  file_expired: "Ảnh tạm hết hạn",
  file_unreadable: "File hỏng hoặc có mật khẩu",
  unsupported_file: "Định dạng không hỗ trợ",
  unknown: "Không rõ",
};

const STAGE_LABELS: Record<string, string> = {
  decode: "đọc ảnh",
  cleaner: "làm sạch ảnh",
  recognizer: "nhận dạng chữ",
  extractor: "trích trường",
  orientation: "xoay ảnh",
};

/** Nhãn tiếng Việt cho mã lỗi; lỗi theo bước OCR (`ocr_<bước>_failed`) gom về 1 dạng. */
export function errorLabel(code: string | null | undefined): string {
  const key = code ?? "unknown";
  if (ERROR_LABELS[key]) return ERROR_LABELS[key];
  const stage = /^ocr_(\w+)_failed$/.exec(key)?.[1];
  return stage ? `Lỗi bước ${STAGE_LABELS[stage] ?? stage}` : key;
}

export const FIELD_LABELS: Record<string, string> = {
  full_name: "Họ và tên",
  id_number: "Số CCCD",
  dob: "Ngày sinh",
  gender: "Giới tính",
  residence: "Nơi thường trú",
  origin: "Quê quán",
  nationality: "Quốc tịch",
  expiry_date: "Ngày hết hạn",
};
