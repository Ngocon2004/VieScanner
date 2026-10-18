import { z } from "zod";

/**
 * Zod schemas đồng bộ 1-1 với Pydantic schema ở backend
 * (`backend/app/models/cccd.py`). Là single source of truth:
 *  - Inferred TypeScript types được export ngay dưới.
 *  - API client dùng `safeParse` để validate runtime, tránh dữ liệu bẩn lọt vào UI.
 */

const dateDDMMYYYY = z
  .string()
  .regex(/^\d{2}\/\d{2}\/\d{4}$/, "Định dạng phải là DD/MM/YYYY");

export const cccdDataSchema = z.object({
  id_number: z
    .string()
    .regex(/^\d{12}$/, "Số CCCD phải gồm đúng 12 chữ số"),
  full_name: z.string().min(1, "Họ và tên không được để trống").max(100),
  dob: dateDDMMYYYY,
  gender: z.enum(["Nam", "Nữ"], {
    message: "Giới tính phải là 'Nam' hoặc 'Nữ'",
  }),
  nationality: z.string().min(1).max(50),
  origin: z.string().min(1).max(200),
  residence: z.string().min(1).max(200),
  expiry_date: z.union([dateDDMMYYYY, z.literal("")]).optional().nullable(),
});

export type CCCDData = z.infer<typeof cccdDataSchema>;

export const fieldConfidencesSchema = z.record(
  z.string(),
  z.number().min(0).max(1),
);

// ----- Image quality gate -----

export const qualityIssueSchema = z.object({
  code: z.string(),
  severity: z.enum(["hard", "soft"]),
  message: z.string(),
  metric: z.number().nullable().optional(),
  threshold: z.number().nullable().optional(),
});

export type QualityIssue = z.infer<typeof qualityIssueSchema>;

export const qualityReportSchema = z.object({
  accepted: z.boolean(),
  score: z.number().min(0).max(1).default(1),
  issues: z.array(qualityIssueSchema).default([]),
  metrics: z.record(z.string(), z.number()).default({}),
});

export type QualityReport = z.infer<typeof qualityReportSchema>;

export const cccdExtractResponseSchema = z.object({
  data: cccdDataSchema,
  scan_id: z.string().optional().nullable(),
  confidences: fieldConfidencesSchema.optional().default({}),
  quality: qualityReportSchema.optional().nullable(),
});

export type FieldConfidences = Partial<Record<keyof CCCDData, number>>;
export type CCCDExtractResponse = z.infer<typeof cccdExtractResponseSchema>;

// ----- Batch extract -----

export const batchItemResultSchema = z.object({
  index: z.number(),
  filename: z.string().nullable(),
  accepted: z.boolean(),
  status: z.string(), // extracted | rejected | ocr_failed
  quality: qualityReportSchema.optional().nullable(),
  data: cccdDataSchema.optional().nullable(),
  confidences: fieldConfidencesSchema.optional().default({}),
  scan_id: z.string().optional().nullable(),
  error_code: z.string().optional().nullable(),
  error_message: z.string().optional().nullable(),
});

export type BatchItemResult = z.infer<typeof batchItemResultSchema>;

export const batchExtractResponseSchema = z.object({
  total: z.number(),
  accepted_count: z.number(),
  rejected_count: z.number(),
  results: z.array(batchItemResultSchema),
});

export type BatchExtractResponse = z.infer<typeof batchExtractResponseSchema>;

// ----- Jobs (xử lý bất đồng bộ) -----

export const JOB_TERMINAL_STATUSES = ["completed", "partial", "failed", "cancelled"] as const;

export const jobItemSchema = z.object({
  id: z.string(),
  seq: z.number(),
  upload_index: z.number(),
  filename: z.string().nullable(),
  container_filename: z.string().nullable().optional(),
  page_number: z.number().nullable().optional(),
  status: z.string(), // queued | processing | done | rejected | failed | cancelled
  scan_id: z.string().nullable().optional(),
  result: batchItemResultSchema.nullable().optional(),
});

export type JobItem = z.infer<typeof jobItemSchema>;

export const jobSchema = z.object({
  id: z.string(),
  source: z.string(),
  status: z.string(),
  total_items: z.number(),
  processed_items: z.number(),
  succeeded_items: z.number(),
  failed_items: z.number(),
  created_at: z.string(),
  started_at: z.string().nullable().optional(),
  finished_at: z.string().nullable().optional(),
  items: z.array(jobItemSchema),
});

export type Job = z.infer<typeof jobSchema>;

export const errorResponseSchema = z.object({
  code: z.string(),
  message: z.string(),
  request_id: z.string(),
  details: z.array(z.unknown()).optional().nullable(),
});

export type ErrorResponse = z.infer<typeof errorResponseSchema>;

// ----- Auth -----

export const userReadSchema = z.object({
  id: z.string(),
  email: z.string().email(),
  full_name: z.string().nullable(),
  role: z.string(),
  is_active: z.boolean(),
  created_at: z.string(), // ISO date
  updated_at: z.string(), // ISO date
});

export type UserRead = z.infer<typeof userReadSchema>;

export const tokenSchema = z.object({
  access_token: z.string(),
  token_type: z.literal("bearer"),
});

export type Token = z.infer<typeof tokenSchema>;

export const userCreateSchema = z.object({
  email: z.string().email("Email không hợp lệ"),
  password: z.string().min(6, "Mật khẩu phải từ 6 ký tự"),
  full_name: z.string().optional(),
});

export type UserCreate = z.infer<typeof userCreateSchema>;

export const userLoginSchema = z.object({
  email: z.string().email("Email không hợp lệ"),
  password: z.string().min(1, "Mật khẩu không được để trống"),
});

export type UserLogin = z.infer<typeof userLoginSchema>;

// ----- Scans -----

export const scanListItemSchema = z.object({
  id: z.string(),
  request_id: z.string().nullable(),
  filename: z.string().nullable(),
  ocr_engine: z.string(),
  status: z.string(),
  duration_ms: z.number().nullable(),
  created_at: z.string(),
});

export type ScanListItem = z.infer<typeof scanListItemSchema>;

export const scanReadSchema = scanListItemSchema.extend({
  user_id: z.string().nullable(),
  mime_type: z.string().nullable(),
  size_bytes: z.number().nullable(),
  image_hash: z.string().nullable(),
  raw_data: z.record(z.string(), z.unknown()).nullable(),
  confidences: z.record(z.string(), z.number()).nullable(),
  error_code: z.string().nullable(),
  error_message: z.string().nullable(),
});

export type ScanRead = z.infer<typeof scanReadSchema>;

// ----- Records -----

export const cccdRecordReadSchema = z.object({
  id: z.string(),
  scan_id: z.string().nullable(),
  user_id: z.string().nullable(),
  id_number: z.string(),
  full_name: z.string(),
  dob: z.string(), // Formatted DD/MM/YYYY
  gender: z.string(),
  nationality: z.string(),
  origin: z.string(),
  residence: z.string(),
  expiry_date: z.string().nullable(), // Formatted DD/MM/YYYY
  exported_at: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});

export type CCCDRecordRead = z.infer<typeof cccdRecordReadSchema>;

export const cccdRecordCreateSchema = cccdDataSchema.extend({
  scan_id: z.string().optional(),
});

export type CCCDRecordCreate = z.infer<typeof cccdRecordCreateSchema>;

export const cccdRecordUpdateSchema = cccdDataSchema.partial();

export type CCCDRecordUpdate = z.infer<typeof cccdRecordUpdateSchema>;
