import type { CCCDData } from "@/types";

/**
 * Cấu hình các trường CCCD để render form.
 *
 * Tách ra khỏi component để:
 *  - Dùng chung giữa CCCDForm, validators, và tương lai (table view, export).
 *  - Sẵn sàng i18n: chỉ cần map `name` → labels khác ngôn ngữ.
 */
export type CCCDFieldName = keyof CCCDData;

export interface CCCDFieldConfig {
  readonly name: CCCDFieldName;
  readonly label: string;
  readonly placeholder?: string;
  /** Hint hiển thị dưới input (ví dụ: định dạng yêu cầu). */
  readonly hint?: string;
  /** Trường bắt buộc (mặc định true; expiry_date là false). */
  readonly required?: boolean;
}

export const CCCD_FIELDS: readonly CCCDFieldConfig[] = [
  {
    name: "id_number",
    label: "Số CCCD",
    placeholder: "12 chữ số",
    hint: "Đúng 12 chữ số",
  },
  { name: "full_name", label: "Họ và tên", placeholder: "Nguyễn Văn A" },
  {
    name: "dob",
    label: "Ngày sinh",
    placeholder: "DD/MM/YYYY",
    hint: "Định dạng: DD/MM/YYYY",
  },
  { name: "gender", label: "Giới tính", placeholder: "Nam hoặc Nữ" },
  { name: "nationality", label: "Quốc tịch", placeholder: "Việt Nam" },
  { name: "origin", label: "Quê quán" },
  { name: "residence", label: "Nơi thường trú" },
  {
    name: "expiry_date",
    label: "Ngày hết hạn",
    placeholder: "DD/MM/YYYY",
    hint: "Có thể để trống",
    required: false,
  },
] as const;
