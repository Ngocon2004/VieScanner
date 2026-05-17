import {
  cccdExtractResponseSchema,
  errorResponseSchema,
  type CCCDExtractResponse,
  type CCCDData,
  type ErrorResponse,
} from "@/lib/schemas";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

/**
 * Custom error class mang theo `code`, `requestId` từ BE.
 * Component có thể switch theo `code` để hiển thị message phù hợp.
 */
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

/** Parse response error: thử match schema {code, message, ...} từ BE; fallback nếu không. */
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

export async function extractCCCD(file: File): Promise<CCCDExtractResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/extract`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    throw await asAPIError(response);
  }

  const body: unknown = await response.json();
  const parsed = cccdExtractResponseSchema.safeParse(body);
  if (!parsed.success) {
    throw new APIError({
      code: "invalid_response",
      message: "Server trả về dữ liệu không hợp lệ.",
      status: response.status,
      details: parsed.error.issues,
    });
  }
  return parsed.data;
}

export async function exportToExcel(data: CCCDData): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw await asAPIError(response);
  }

  // Lấy filename từ Content-Disposition để dùng tên server đặt (đã sanitize).
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

function parseFilenameFromDisposition(disposition: string): string | undefined {
  // Ưu tiên `filename*=UTF-8''...` (RFC 5987) vì hỗ trợ Unicode.
  const utf8 = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8?.[1]) {
    try {
      return decodeURIComponent(utf8[1]);
    } catch {
      /* fall through */
    }
  }
  const ascii = disposition.match(/filename="([^"]+)"/i);
  return ascii?.[1];
}
