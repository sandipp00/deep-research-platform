import { fetchEventSource } from "@microsoft/fetch-event-source";
import { ApiError, messageFromBody } from "./errors";

export interface SseEvent {
  event?: string;
  data: string;
  id?: string;
  retry?: number;
}

export type SseHandlers = {
  onEvent: (msg: SseEvent) => void;
  onError?: (err: unknown) => void;
  onClose?: () => void;
  signal?: AbortSignal;
};

const baseURL = import.meta.env.VITE_API_URL || "/api";

export async function postSse(path: string, body: unknown, handlers: SseHandlers) {
  const token = localStorage.getItem("auth_token");
  await fetchEventSource(`${baseURL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal: handlers.signal,
    openWhenHidden: true,
    onmessage: handlers.onEvent,
    async onopen(res) {
      if (res.ok && res.headers.get("content-type")?.includes("text/event-stream")) return;
      if (res.status === 401) {
        localStorage.removeItem("auth_token");
        localStorage.removeItem("auth_user");
        if (!location.pathname.startsWith("/login")) location.href = "/login";
      }
      let body: unknown = null;
      try {
        const text = await res.text();
        try { body = JSON.parse(text); } catch { body = text; }
      } catch {
        body = null;
      }
      throw new ApiError(messageFromBody(body) || `Request failed (${res.status})`, res.status);
    },
    onerror(err) {
      handlers.onError?.(err);
      throw err;
    },
    onclose() {
      handlers.onClose?.();
    },
  });
}
