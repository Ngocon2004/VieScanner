/**
 * Single source of truth: types được infer từ Zod schemas trong `@/lib/schemas`.
 * File này giữ lại để các module cũ vẫn import được từ `@/types`.
 */
export type {
  CCCDData,
  CCCDExtractResponse,
  ErrorResponse,
  FieldConfidences,
} from "@/lib/schemas";
