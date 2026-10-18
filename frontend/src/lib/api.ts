import {
  cccdExtractResponseSchema,
  batchExtractResponseSchema,
  errorResponseSchema,
  userReadSchema,
  tokenSchema,
  scanListItemSchema,
  scanReadSchema,
  cccdRecordReadSchema,
  jobSchema,
  type CCCDExtractResponse,
  type Job,
  type BatchExtractResponse,
  type ErrorResponse,
  type UserRead,
  type Token,
  type UserLogin,
  type UserCreate,
  type ScanListItem,
  type ScanRead,
  type CCCDRecordRead,
} from "@/lib/schemas";
import type { ExportListRow } from "@/lib/cccdList";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

export class APIError extends Error {
  public readonly code: string;
  public readonly status: number;
  public readonly requestId: string | undefined;
  public readonly details: unknown;

  constructor(params: {
    code: string;
    message: string;
    status: number;
    requestId?: string;
    details?: unknown;
  }) {
    super(params.message);
    this.name = "APIError";
    this.code = params.code;
    this.status = params.status;
    this.requestId = params.requestId;
    this.details = params.details;
  }
}

async function asAPIError(response: Response): Promise<APIError> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  const parsed = errorResponseSchema.safeParse(body);
  if (parsed.success) {
    const data: ErrorResponse = parsed.data;
    return new APIError({
      code: data.code,
      message: data.message,
      status: response.status,
      requestId: data.request_id,
      details: data.details,
    });
  }
  return new APIError({
    code: "network_error",
    message: `Yêu cầu thất bại (HTTP ${response.status})`,
    status: response.status,
  });
}

export const TOKEN_STORAGE_KEY = "vs_token";
export const AUTH_EXPIRED_EVENT = "vs:auth-expired";

function getAuthHeader(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem(TOKEN_STORAGE_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
}

const DEFAULT_TIMEOUT_MS = 30_000;
// OCR (đặc biệt real mode/lần đầu warm-up) hoặc batch nhiều ảnh có thể chậm.
const EXTRACT_TIMEOUT_MS = 120_000;

/** True nếu lỗi là do request bị hủy (AbortController), không phải lỗi server.
 *
 * Lưu ý: fetch bị abort ném `DOMException` (KHÔNG phải `instanceof Error` ở
 * Node/jsdom) nên kiểm tra theo thuộc tính `name` thay vì `instanceof`. */
export function isAbortError(err: unknown): boolean {
  return (
    typeof err === "object" &&
    err !== null &&
    "name" in err &&
    (err as { name?: unknown }).name === "AbortError"
  );
}

/**
 * Gộp nhiều AbortSignal thành 1 (abort khi bất kỳ signal nào abort). Dùng
 * `AbortSignal.any` nếu môi trường hỗ trợ, fallback bằng listener thủ công.
 */
function anySignal(signals: AbortSignal[]): AbortSignal {
  const ctor = AbortSignal as unknown as {
    any?: (signals: AbortSignal[]) => AbortSignal;
  };
  if (typeof ctor.any === "function") {
    return ctor.any(signals);
  }
  const controller = new AbortController();
  const onAbort = () => {
    controller.abort();
    for (const s of signals) s.removeEventListener("abort", onAbort);
  };
  for (const s of signals) {
    if (s.aborted) {
      controller.abort();
      break;
    }
    s.addEventListener("abort", onAbort);
  }
  return controller.signal;
}

/**
 * Fetch có timeout bằng AbortController để request không treo vô hạn khi server
 * chậm/không phản hồi. Nếu caller truyền `signal` (vd hủy khi unmount), signal đó
 * được **gộp** với signal timeout — vừa hủy được từ caller, vừa vẫn có timeout.
 *
 * - Hết thời gian chờ → ném `APIError` code `timeout`.
 * - Caller chủ động hủy → ném lại AbortError gốc để caller phân biệt và bỏ qua
 *   (xem `isAbortError`), không hiển thị như lỗi timeout.
 */
async function fetchWithTimeout(
  url: string,
  options: RequestInit,
  timeoutMs: number,
): Promise<Response> {
  if (typeof AbortController === "undefined") {
    return fetch(url, options);
  }

  const callerSignal = options.signal ?? undefined;
  const timeoutController = new AbortController();
  const timer = setTimeout(() => timeoutController.abort(), timeoutMs);
  const signal = callerSignal
    ? anySignal([callerSignal, timeoutController.signal])
    : timeoutController.signal;

  try {
    return await fetch(url, { ...options, signal });
  } catch (err) {
    // Hết thời gian chờ (caller không chủ động hủy) → lỗi timeout thân thiện.
    if (timeoutController.signal.aborted && !callerSignal?.aborted) {
      throw new APIError({
        code: "timeout",
        message:
          "Yêu cầu quá thời gian chờ. Vui lòng thử lại hoặc dùng ảnh nhẹ hơn.",
        status: 0,
      });
    }
    // Caller hủy (unmount/điều hướng) → giữ nguyên AbortError để caller bỏ qua.
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Fetch kèm token. Token hết hạn/không hợp lệ thì xóa token, báo AuthContext và gửi lại
 * 1 lần không kèm token: nếu không, sau khi token hết hạn mọi chức năng cho phép ẩn danh
 * (quét, xuất Excel) đều lỗi 401 tới khi người dùng tự đăng xuất.
 */
async function authedFetch(url: string, options: RequestInit, timeoutMs: number): Promise<Response> {
  const auth = getAuthHeader();
  const send = (extra: Record<string, string>) =>
    fetchWithTimeout(
      url,
      { ...options, headers: { ...extra, ...((options.headers as Record<string, string>) || {}) } },
      timeoutMs,
    );
  const response = await send(auth);
  if (response.status !== 401 || !auth.Authorization) return response;

  const error = await asAPIError(response.clone());
  if (error.code !== "auth_token_invalid") return response;
  localStorage.removeItem(TOKEN_STORAGE_KEY);
  window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
  return send({});
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  schema?: {
    safeParse: (
      data: unknown,
    ) => { success: boolean; data?: T | undefined; error?: { issues?: unknown } | undefined };
  },
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const url = path.startsWith("http") ? path : `${API_BASE_URL}${path}`;
  const response = await authedFetch(url, options, timeoutMs);

  if (!response.ok) {
    throw await asAPIError(response);
  }

  if (response.status === 204) return {} as T;

  const body: unknown = await response.json();
  if (!schema) return body as T;

  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    throw new APIError({
      code: "invalid_response",
      message: "Server trả về dữ liệu không hợp lệ.",
      status: response.status,
      details: parsed.error?.issues,
    });
  }
  return parsed.data as T;
}

// ----- OCR & Export -----

export async function extractCCCD(file: File): Promise<CCCDExtractResponse> {
  const formData = new FormData();
  formData.append("file", file);

  return request<CCCDExtractResponse>("/extract", {
    method: "POST",
    body: formData,
  }, cccdExtractResponseSchema, EXTRACT_TIMEOUT_MS);
}

// Backend OCR tuần tự từng ảnh (real mode ~16 s/ảnh), nên timeout cố định 120 s
// sẽ cắt ngang batch lớn trong khi server vẫn chạy tiếp.
const EXTRACT_BATCH_PER_FILE_MS = 30_000;

export function batchTimeoutMs(fileCount: number): number {
  return Math.max(EXTRACT_TIMEOUT_MS, fileCount * EXTRACT_BATCH_PER_FILE_MS);
}

export async function extractBatch(
  files: File[],
  signal?: AbortSignal,
): Promise<BatchExtractResponse> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }

  return request<BatchExtractResponse>("/extract-batch", {
    method: "POST",
    body: formData,
    signal: signal ?? null,
  }, batchExtractResponseSchema, batchTimeoutMs(files.length));
}

export type JobSource = "upload" | "camera";

// Upload nhiều file/PDF có thể lâu; xử lý OCR chạy nền nên chỉ cần đủ thời gian gửi file.
const JOB_UPLOAD_TIMEOUT_MS = 180_000;

export async function createJob(
  files: File[],
  source: JobSource = "upload",
  signal?: AbortSignal,
): Promise<Job> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }
  formData.append("source", source);

  return request<Job>("/jobs", {
    method: "POST",
    body: formData,
    signal: signal ?? null,
  }, jobSchema, JOB_UPLOAD_TIMEOUT_MS);
}

export async function getJob(jobId: string, signal?: AbortSignal): Promise<Job> {
  return request<Job>(`/jobs/${encodeURIComponent(jobId)}`, { signal: signal ?? null }, jobSchema);
}

export async function cancelJob(jobId: string): Promise<Job> {
  return request<Job>(`/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" }, jobSchema);
}

export async function exportListToExcel(rows: ExportListRow[]): Promise<void> {
  const response = await authedFetch(`${API_BASE_URL}/export-list`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rows }),
  }, DEFAULT_TIMEOUT_MS);

  if (!response.ok) {
    throw await asAPIError(response);
  }

  const disposition = response.headers.get("Content-Disposition") ?? "";
  const filename = parseFilenameFromDisposition(disposition) ?? "DanhSach_CCCD.xlsx";

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Thu hồi ngay sau click làm Firefox/Safari hủy tải: đợi trình duyệt nhận file trước.
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

// ----- Auth -----

export async function login(payload: UserLogin): Promise<Token> {
  return request<Token>("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }, tokenSchema);
}

export async function register(payload: UserCreate): Promise<UserRead> {
  return request<UserRead>("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }, userReadSchema);
}

export async function getMe(): Promise<UserRead> {
  return request<UserRead>("/auth/me", {}, userReadSchema);
}

// ----- Scans -----

export async function getScans(
  limit = 50,
  offset = 0,
  signal?: AbortSignal,
): Promise<ScanListItem[]> {
  return request<ScanListItem[]>(`/scans?limit=${limit}&offset=${offset}`, { signal: signal ?? null }, {
    safeParse: (data) => {
      const parsed = scanListItemSchema.array().safeParse(data);
      return { success: parsed.success, data: parsed.data as ScanListItem[], error: parsed.error };
    }
  });
}

export async function getScan(id: string, signal?: AbortSignal): Promise<ScanRead> {
  return request<ScanRead>(`/scans/${id}`, { signal: signal ?? null }, scanReadSchema);
}

// ----- Records -----

export async function getRecords(
  limit = 50,
  offset = 0,
  signal?: AbortSignal,
): Promise<CCCDRecordRead[]> {
  return request<CCCDRecordRead[]>(`/records?limit=${limit}&offset=${offset}`, { signal: signal ?? null }, {
    safeParse: (data) => {
      const parsed = cccdRecordReadSchema.array().safeParse(data);
      return { success: parsed.success, data: parsed.data as CCCDRecordRead[], error: parsed.error };
    }
  });
}

export async function deleteRecord(id: string): Promise<void> {
  await request<void>(`/records/${id}`, { method: "DELETE" });
}

// Cho module API khác (vd. `lib/admin.ts`) dùng chung token, timeout và chuẩn hóa lỗi.
export function apiRequest<T>(
  path: string,
  options: RequestInit,
  schema: { safeParse: (data: unknown) => { success: boolean; data?: T | undefined; error?: { issues?: unknown } | undefined } },
): Promise<T> {
  return request<T>(path, options, schema);
}

// Engine "mock" trả dữ liệu mẫu cố định, không đọc ảnh: trang quét phải cảnh báo để không ai tin nhầm kết quả.
export async function getOcrEngine(signal?: AbortSignal): Promise<string | null> {
  try {
    const response = await fetch(`${API_BASE_URL.replace(/\/api\/?$/, "")}/health`, { signal: signal ?? null });
    if (!response.ok) return null;
    const body: unknown = await response.json();
    const engine = (body as { ocr_engine?: unknown })?.ocr_engine;
    return typeof engine === "string" ? engine : null;
  } catch {
    return null;
  }
}

// ----- Utils -----

function parseFilenameFromDisposition(disposition: string): string | undefined {
  const utf8 = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8?.[1]) {
    try {
      return decodeURIComponent(utf8[1]);
    } catch { /* ignore */ }
  }
  const ascii = disposition.match(/filename="([^"]+)"/i);
  return ascii?.[1];
}
