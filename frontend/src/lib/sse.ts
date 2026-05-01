import { fetchEventSource } from "@microsoft/fetch-event-source";

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
    onerror(err) {
      handlers.onError?.(err);
      throw err;  // stop retrying
    },
    onclose() {
      handlers.onClose?.();
    },
  });
}
