export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type ValidationItem = { msg?: unknown; loc?: unknown };

function fromValidationItem(item: unknown): string | null {
  if (typeof item === "string") return item;
  if (!item || typeof item !== "object") return null;
  const { msg, loc } = item as ValidationItem;
  if (typeof msg !== "string" || !msg) return null;
  const field = Array.isArray(loc)
    ? loc.filter((p) => p !== "body" && (typeof p === "string" || typeof p === "number")).join(".")
    : "";
  return field ? `${field}: ${msg}` : msg;
}

export function messageFromBody(body: unknown): string | null {
  if (typeof body === "string") {
    const t = body.trim();
    return t && !t.startsWith("<") && t.length <= 300 ? t : null;
  }
  if (!body || typeof body !== "object") return null;
  const b = body as Record<string, unknown>;
  for (const key of ["detail", "error", "message"]) {
    const v = b[key];
    if (typeof v === "string" && v.trim()) return v.trim();
    if (Array.isArray(v)) {
      const parts = v.map(fromValidationItem).filter((s): s is string => !!s);
      if (parts.length) return parts.join("; ");
    }
    if (v && typeof v === "object") {
      const nested = fromValidationItem(v) ?? messageFromBody(v);
      if (nested) return nested;
    }
  }
  return null;
}

export function errorMessage(err: unknown, fallback = "Something went wrong."): string {
  if (err && typeof err === "object") {
    const response = (err as { response?: { data?: unknown } }).response;
    if (response) {
      const fromBody = messageFromBody(response.data);
      if (fromBody) return fromBody;
    }
    if (err instanceof ApiError) return err.message;
  }
  return fallback;
}
