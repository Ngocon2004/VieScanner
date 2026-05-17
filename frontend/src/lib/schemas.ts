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

export const cccdExtractResponseSchema = z.object({
  data: cccdDataSchema,
  confidences: fieldConfidencesSchema.optional().default({}),
});

export type FieldConfidences = Partial<Record<keyof CCCDData, number>>;
export type CCCDExtractResponse = z.infer<typeof cccdExtractResponseSchema>;

export const errorResponseSchema = z.object({
  code: z.string(),
  message: z.string(),
  request_id: z.string(),
  details: z.array(z.unknown()).optional().nullable(),
});

export type ErrorResponse = z.infer<typeof errorResponseSchema>;
