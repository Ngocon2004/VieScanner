import type { CCCDData, FieldConfidences } from "@/lib/schemas";

export const LIST_FIELDS = ["full_name", "id_number", "dob", "gender", "residence"] as const;
export type ListField = (typeof LIST_FIELDS)[number];

export const LIST_FIELD_LABELS: Record<ListField, string> = {
  full_name: "Họ và tên",
  id_number: "Số CCCD",
  dob: "Ngày sinh",
  gender: "Giới tính",
  residence: "Nơi thường trú",
};

/** Ô có độ tin cậy dưới ngưỡng này phải được người dùng kiểm tra lại (tô vàng). */
export const REVIEW_CONFIDENCE = 0.85;

export interface ListRow {
  key: string;
  full_name: string;
  id_number: string;
  dob: string;
  gender: string;
  residence: string;
  confidences: Partial<Record<ListField, number>>;
  /** Ô người dùng đã sửa hoặc xác nhận: không còn cần kiểm tra, không bị OCR ghi đè khi ghép. */
  reviewed: Partial<Record<ListField, boolean>>;
  scanIds: string[];
  sources: string[];
  /** Ô còn trống vì ảnh thiếu mặt cần thiết: nói người dùng cần tải thêm ảnh nào. */
  hints: Partial<Record<ListField, string>>;
}

export type RowErrors = Partial<Record<ListField, string>>;

// Phải khớp backend `app/services/ocr/placeholders.py`: giá trị giữ chỗ của trường OCR không đọc được.
const UNKNOWN_TEXT = "(không nhận dạng được)";
const PLACEHOLDER_ID = "000000000000";

// Phải khớp `PROVINCE_CODES` ở backend `app/services/ocr/cccd_number.py` (63 tỉnh cũ).
const PROVINCE_CODES = new Set(
  [
    1, 2, 4, 6, 8, 10, 11, 12, 14, 15, 17, 19, 20, 22, 24, 25, 26, 27, 30, 31, 33, 34, 35, 36, 37,
    38, 40, 42, 44, 45, 46, 48, 49, 51, 52, 54, 56, 58, 60, 62, 64, 66, 67, 68, 70, 72, 74, 75, 77,
    79, 80, 82, 83, 84, 86, 87, 89, 91, 92, 93, 94, 95, 96,
  ].map((code) => String(code).padStart(3, "0")),
);

let keySeq = 0;
function newKey(): string {
  keySeq += 1;
  return `row-${Date.now().toString(36)}-${keySeq}`;
}

export function emptyRow(): ListRow {
  return {
    key: newKey(),
    full_name: "",
    id_number: "",
    dob: "",
    gender: "",
    residence: "",
    confidences: {},
    reviewed: {},
    scanIds: [],
    sources: [],
    hints: {},
  };
}

// Mã cảnh báo từ backend (`app/services/ocr/review.py`) -> gợi ý cho ô còn trống.
const ISSUE_HINTS: Record<string, Partial<Record<ListField, string>>> = {
  residence_on_back: { residence: "Thẻ mẫu 2024 in nơi cư trú ở mặt sau: tải thêm ảnh mặt sau" },
  back_side: {
    full_name: "Ảnh mặt sau không có họ tên: tải thêm ảnh mặt trước",
    residence: "Thẻ CCCD: tải thêm ảnh mặt trước; thẻ mẫu 2024: chụp lại mặt sau rõ hơn",
  },
};

function keepHintsForEmpty(row: ListRow): ListRow["hints"] {
  return Object.fromEntries(
    Object.entries(row.hints).filter(([field]) => !row[field as ListField]),
  ) as ListRow["hints"];
}

/** Dòng đọc lại từ bộ nhớ trình duyệt: bỏ dòng hỏng, bù trường thiếu để giao diện không vỡ. */
export function normalizeStoredRow(raw: unknown): ListRow | null {
  if (!raw || typeof raw !== "object") return null;
  const value = raw as Record<string, unknown>;
  if (typeof value.key !== "string") return null;
  const row = { ...emptyRow(), key: value.key };
  for (const field of LIST_FIELDS) {
    if (typeof value[field] === "string") row[field] = value[field] as string;
  }
  const record = (input: unknown) => (input && typeof input === "object" ? input : {});
  row.confidences = record(value.confidences) as ListRow["confidences"];
  row.reviewed = record(value.reviewed) as ListRow["reviewed"];
  const strings = (input: unknown) =>
    Array.isArray(input) ? input.filter((item): item is string => typeof item === "string") : [];
  row.scanIds = strings(value.scanIds);
  row.sources = strings(value.sources);
  row.hints = record(value.hints) as ListRow["hints"];
  return row;
}

/** Kết quả OCR -> 1 dòng. Trường OCR không đọc được (confidence 0) để trống, không giữ giá trị giả. */
export function rowFromResult(
  data: CCCDData,
  confidences: FieldConfidences,
  scanId: string | null,
  source: string,
  issueCodes: string[] = [],
): ListRow {
  const row = emptyRow();
  for (const field of LIST_FIELDS) {
    const confidence = confidences[field] ?? 0;
    const value = String(data[field] ?? "").trim();
    if (confidence <= 0 || value === UNKNOWN_TEXT || value === PLACEHOLDER_ID) continue;
    row[field] = value;
    row.confidences[field] = confidence;
  }
  // Giới tính mã hóa trong số CCCD: thiếu thì suy ra, trùng khớp thì hai nguồn xác nhận nhau.
  const info = decodeIdNumber(row.id_number);
  const idConfidence = row.confidences.id_number ?? 0;
  if (info && !row.gender) {
    row.gender = info.gender;
    row.confidences.gender = idConfidence;
  } else if (info && row.gender === info.gender) {
    row.confidences.gender = Math.max(row.confidences.gender ?? 0, idConfidence);
  }
  if (scanId) row.scanIds.push(scanId);
  row.sources.push(source);
  for (const code of issueCodes) Object.assign(row.hints, ISSUE_HINTS[code]);
  row.hints = keepHintsForEmpty(row);
  return row;
}

/** Người dùng sửa 1 ô. Sửa số CCCD thì giới tính đi theo, trừ khi người dùng đã tự chọn giới tính. */
export function applyEdit(row: ListRow, field: ListField, value: string): ListRow {
  const next: ListRow = {
    ...row,
    [field]: value,
    reviewed: { ...row.reviewed, [field]: true },
    confidences: { ...row.confidences },
  };
  const info = field === "id_number" ? decodeIdNumber(value.trim()) : null;
  if (info && !row.reviewed.gender) {
    next.gender = info.gender;
    next.confidences.gender = 1;
  }
  return next;
}

/** Gộp dòng `source` vào `target` (cùng 1 thẻ nhưng OCR đọc lệch số): ô trống của target lấy từ source. */
export function mergeRowInto(target: ListRow, source: ListRow): ListRow {
  const merged: ListRow = {
    ...target,
    confidences: { ...target.confidences },
    reviewed: { ...target.reviewed, id_number: true },
    scanIds: [...new Set([...target.scanIds, ...source.scanIds])],
    sources: [...new Set([...target.sources, ...source.sources])],
    hints: { ...source.hints, ...target.hints },
  };
  for (const field of LIST_FIELDS) {
    if (!merged[field] && source[field]) {
      merged[field] = source[field];
      if (source.confidences[field] !== undefined) merged.confidences[field] = source.confidences[field];
      if (source.reviewed[field]) merged.reviewed[field] = true;
    }
  }
  merged.hints = keepHintsForEmpty(merged);
  return merged;
}

function digitDistance(a: string, b: string): number {
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff += a[i] === b[i] ? 0 : 1;
  return diff;
}

/**
 * Số CCCD của 2 dòng chỉ lệch 1-2 chữ số: gần như chắc là cùng 1 thẻ bị OCR đọc lệch một bên,
 * và số lệch vẫn qua được kiểm tra cấu trúc nên phải bắt người dùng xem lại. Trả key -> STT dòng kia.
 */
export function nearDuplicateIds(rows: ListRow[]): Map<string, number> {
  const result = new Map<string, number>();
  rows.forEach((row, i) => {
    if (!/^\d{12}$/.test(row.id_number)) return;
    rows.forEach((other, j) => {
      if (i === j || result.has(row.key) || !/^\d{12}$/.test(other.id_number)) return;
      const distance = digitDistance(row.id_number, other.id_number);
      if (distance > 0 && distance <= 2) result.set(row.key, j + 1);
    });
  });
  return result;
}

interface IdInfo {
  gender: "Nam" | "Nữ";
  birthYear: number;
}

/** Cấu trúc số CCCD (TT 07/2016): 3 số mã tỉnh, 1 số thế kỷ + giới tính, 2 số cuối năm sinh. */
export function decodeIdNumber(value: string, today: Date = new Date()): IdInfo | null {
  if (!/^\d{12}$/.test(value) || !PROVINCE_CODES.has(value.slice(0, 3))) return null;
  const centuryGender = Number(value[3]);
  const birthYear = (19 + Math.floor(centuryGender / 2)) * 100 + Number(value.slice(4, 6));
  if (birthYear > today.getFullYear()) return null;
  return { gender: centuryGender % 2 ? "Nữ" : "Nam", birthYear };
}

function parseDate(value: string): Date {
  const [day, month, year] = value.split("/").map(Number);
  return new Date(year!, month! - 1, day);
}

function isValidDate(value: string): boolean {
  if (!/^\d{2}\/\d{2}\/\d{4}$/.test(value)) return false;
  const [day, month, year] = value.split("/").map(Number);
  const date = parseDate(value);
  return date.getFullYear() === year && date.getMonth() === month! - 1 && date.getDate() === day;
}

export function validateRow(row: ListRow): RowErrors {
  const errors: RowErrors = {};
  for (const field of LIST_FIELDS) {
    if (!row[field].trim()) errors[field] = row.hints[field] ?? "Chưa có dữ liệu";
  }
  if (row.full_name.length > 100) errors.full_name = "Tối đa 100 ký tự";
  else if (/\d/.test(row.full_name)) errors.full_name = "Họ tên không được chứa chữ số";
  if (row.residence.length > 200) errors.residence = "Tối đa 200 ký tự";
  if (row.gender && row.gender !== "Nam" && row.gender !== "Nữ") errors.gender = "Chọn Nam hoặc Nữ";
  if (row.dob && !isValidDate(row.dob)) errors.dob = "Ngày không hợp lệ (DD/MM/YYYY)";
  else if (row.dob && parseDate(row.dob) > new Date()) errors.dob = "Ngày sinh ở tương lai";

  if (row.id_number && !errors.id_number) {
    const info = decodeIdNumber(row.id_number);
    if (!/^\d{12}$/.test(row.id_number)) {
      errors.id_number = "Phải gồm đúng 12 chữ số";
    } else if (!info) {
      errors.id_number = "Số CCCD không hợp lệ (mã tỉnh hoặc năm sinh sai)";
    } else {
      // Số CCCD mã hóa giới tính và năm sinh: lệch nhau chắc chắn có một ô đọc/nhập sai.
      if (row.gender && !errors.gender && row.gender !== info.gender) {
        errors.gender = `Không khớp số CCCD (số CCCD là ${info.gender})`;
      }
      if (row.dob && !errors.dob && Number(row.dob.slice(-4)) !== info.birthYear) {
        errors.dob = `Năm sinh không khớp số CCCD (${info.birthYear})`;
      }
    }
  }
  return errors;
}

/** Lỗi của cả danh sách: lỗi từng dòng + số CCCD bị trùng giữa các dòng. */
export function validateList(rows: ListRow[]): Map<string, RowErrors> {
  const result = new Map<string, RowErrors>();
  const byId = new Map<string, number>();
  for (const row of rows) {
    if (row.id_number) byId.set(row.id_number, (byId.get(row.id_number) ?? 0) + 1);
  }
  for (const row of rows) {
    const errors = validateRow(row);
    if (!errors.id_number && (byId.get(row.id_number) ?? 0) > 1) {
      errors.id_number = "Trùng số CCCD với dòng khác";
    }
    if (Object.keys(errors).length > 0) result.set(row.key, errors);
  }
  return result;
}

export function needsReview(
  row: ListRow,
  field: ListField,
  nearDuplicates: Map<string, number> = new Map(),
): boolean {
  if (row.reviewed[field] || !row[field]) return false;
  if (field === "id_number" && nearDuplicates.has(row.key)) return true;
  return (row.confidences[field] ?? 0) < REVIEW_CONFIDENCE;
}

export function pendingReviewCount(rows: ListRow[]): number {
  const nearDuplicates = nearDuplicateIds(rows);
  return rows.reduce(
    (count, row) =>
      count + LIST_FIELDS.filter((field) => needsReview(row, field, nearDuplicates)).length,
    0,
  );
}

/**
 * Thêm kết quả quét vào danh sách. Cùng số CCCD hợp lệ (ví dụ mặt trước + mặt sau của 1 thẻ)
 * thì ghép vào dòng cũ: mỗi ô giữ giá trị có độ tin cậy cao hơn, ô người dùng đã sửa giữ nguyên.
 */
export function mergeIntoList(rows: ListRow[], incoming: ListRow): ListRow[] {
  const index = decodeIdNumber(incoming.id_number)
    ? rows.findIndex((row) => row.id_number === incoming.id_number)
    : -1;
  if (index < 0) return [...rows, incoming];

  const current = rows[index]!;
  const merged: ListRow = {
    ...current,
    confidences: { ...current.confidences },
    scanIds: [...new Set([...current.scanIds, ...incoming.scanIds])],
    sources: [...new Set([...current.sources, ...incoming.sources])],
    hints: { ...incoming.hints, ...current.hints },
  };
  for (const field of LIST_FIELDS) {
    if (!incoming[field] || current.reviewed[field]) continue;
    const incomingConfidence = incoming.confidences[field] ?? 0;
    if (!current[field] || incomingConfidence > (current.confidences[field] ?? 0)) {
      merged[field] = incoming[field];
      merged.confidences[field] = incomingConfidence;
    }
  }
  merged.hints = keepHintsForEmpty(merged);
  return rows.map((row, i) => (i === index ? merged : row));
}

export function toExportRows(rows: ListRow[]) {
  return rows.map((row) => ({
    full_name: row.full_name.trim(),
    id_number: row.id_number.trim(),
    dob: row.dob.trim(),
    gender: row.gender,
    residence: row.residence.trim(),
    scan_ids: row.scanIds.slice(-10),
  }));
}

export type ExportListRow = ReturnType<typeof toExportRows>[number];
