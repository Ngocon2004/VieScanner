import {
  cccdExtractResponseSchema,
  batchExtractResponseSchema,
  errorResponseSchema,
  userReadSchema,
  tokenSchema,
  scanListItemSchema,
  scanReadSchema,
  cccdRecordReadSchema,
  type CCCDExtractResponse,
  type BatchExtractResponse,
  type CCCDData,
  type ErrorResponse,
  type UserRead,
  type Token,
  type UserLogin,
  type UserCreate,
  type ScanListItem,
  type ScanRead,
  type CCCDRecordRead,
} from "@/lib/schemas";

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

function getAuthHeader(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("vs_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

const DEFAULT_TIMEOUT_MS = 30_000;
// OCR (đặc biệt real mode/lần đầu warm-up) hoặc batch nhiều ảnh có thể chậm.
const EXTRACT_TIMEOUT_MS = 120_000;

/**
 * Fetch có timeout bằng AbortController để request không treo vô hạn khi server
 * chậm/không phản hồi. Nếu caller đã truyền `signal` thì tôn trọng signal đó.
 */
async function fetchWithTimeout(
  url: string,
  options: RequestInit,
  timeoutMs: number,
): Promise<Response> {
  if (options.signal || typeof AbortController === "undefined") {
    return fetch(url, options);
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } catch (err) {
    if (controller.signal.aborted) {
      throw new APIError({
        code: "timeout",
        message:
          "Yêu cầu quá thời gian chờ. Vui lòng thử lại hoặc dùng ảnh nhẹ hơn.",
        status: 0,
      });
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
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
  const headers = {
    ...getAuthHeader(),
    ...((options.headers as Record<string, string>) || {}),
  };

  const response = await fetchWithTimeout(url, { ...options, headers }, timeoutMs);

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

export async function extractBatch(files: File[]): Promise<BatchExtractResponse> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }

  return request<BatchExtractResponse>("/extract-batch", {
    method: "POST",
    body: formData,
  }, batchExtractResponseSchema, EXTRACT_TIMEOUT_MS);
}

export async function exportToExcel(data: CCCDData, scanId?: string): Promise<void> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/export`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeader(),
    },
    body: JSON.stringify({ data, scan_id: scanId }),
  }, DEFAULT_TIMEOUT_MS);

  if (!response.ok) {
    throw await asAPIError(response);
  }

  const disposition = response.headers.get("Content-Disposition") ?? "";
  const filenameFromHeader = parseFilenameFromDisposition(disposition);
  const fallbackName = `CCCD_${data.full_name.replace(/\s+/g, "_")}.xlsx`;

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filenameFromHeader ?? fallbackName;
  document.body.appendChild(a);
  a.click();
  URL.revokeObjectURL(url);
  document.body.removeChild(a);
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

export async function getScans(limit = 50, offset = 0): Promise<ScanListItem[]> {
  return request<ScanListItem[]>(`/scans?limit=${limit}&offset=${offset}`, {}, {
    safeParse: (data) => {
      const parsed = scanListItemSchema.array().safeParse(data);
      return { success: parsed.success, data: parsed.data as ScanListItem[], error: parsed.error };
    }
  });
}

export async function getScan(id: string): Promise<ScanRead> {
  return request<ScanRead>(`/scans/${id}`, {}, scanReadSchema);
}

// ----- Records -----

export async function getRecords(limit = 50, offset = 0): Promise<CCCDRecordRead[]> {
  return request<CCCDRecordRead[]>(`/records?limit=${limit}&offset=${offset}`, {}, {
    safeParse: (data) => {
      const parsed = cccdRecordReadSchema.array().safeParse(data);
      return { success: parsed.success, data: parsed.data as CCCDRecordRead[], error: parsed.error };
    }
  });
}

export async function deleteRecord(id: string): Promise<void> {
  await request<void>(`/records/${id}`, { method: "DELETE" });
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
