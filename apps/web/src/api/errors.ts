export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public fields?: Record<string, string>,
  ) {
    super(message);
    this.name = "ApiError";
  }

  get detail(): string {
    return this.message;
  }
}

function detailText(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) =>
        item && typeof item === "object" && "msg" in item
          ? String((item as { msg: unknown }).msg)
          : "",
      )
      .filter(Boolean);
    return messages.length > 0 ? messages.join("; ") : null;
  }
  return null;
}

function fieldMap(detail: unknown): Record<string, string> | undefined {
  if (!Array.isArray(detail)) return undefined;
  const fields: Record<string, string> = {};
  for (const item of detail) {
    if (!item || typeof item !== "object") continue;
    const loc = (item as { loc?: unknown }).loc;
    const msg = (item as { msg?: unknown }).msg;
    if (!Array.isArray(loc) || typeof msg !== "string") continue;
    const key = [...loc].reverse().find((part) => typeof part === "string");
    if (typeof key === "string") fields[key] = msg;
  }
  return Object.keys(fields).length > 0 ? fields : undefined;
}

export function toApiError(
  error: unknown,
  fallback: string,
  status = 0,
): ApiError {
  const detail =
    error && typeof error === "object" && "detail" in error
      ? (error as { detail?: unknown }).detail
      : undefined;
  return new ApiError(detailText(detail) ?? fallback, status, fieldMap(detail));
}
