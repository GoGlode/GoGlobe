// Поиск API v0.3: создание, снимок, ответ на вопрос, отмена, SSE. Владелец: Frontend №1.
// Только настоящий backend (`/api/v1/*`). Старого `/api/search` здесь нет и быть не должно.
import { ApiError, apiCall, isLive } from "./trips";
import { isTerminal, type Accepted, type Params, type PlanRequest, type Snapshot } from "./v03Search";

const enc = encodeURIComponent;
const BASE = import.meta.env.VITE_API_URL as string | undefined;

/** Ключ идемпотентности: новый на каждое намерение пользователя; повтор того же запроса после обрыва — с тем же ключом. */
export const newKey = () => crypto.randomUUID();

export const createSearch = (req: PlanRequest, key: string, signal?: AbortSignal) =>
  apiCall<Accepted>("POST", "/searches", req, { "Idempotency-Key": key }, signal);
export const getSearch = (id: string, signal?: AbortSignal) => apiCall<Snapshot>("GET", `/searches/${enc(id)}`, undefined, {}, signal).then(checkSnapshot);
export const answerQuestion = (id: string, a: { question_id: string; expected_revision: number; answer: string }, key: string) =>
  apiCall<Accepted>("POST", `/searches/${enc(id)}/clarifications`, a, { "Idempotency-Key": key });
export const cancelSearch = (id: string) => apiCall<Snapshot>("PUT", `/searches/${enc(id)}/cancellation`, {}).then(checkSnapshot);

export interface IntentPreview {
  preview_id: string;
  parsed: Params;
  questions: { id: string; field: string; kind: string; title: string; required: boolean; options: unknown[] }[];
  warnings: { code: string; message: string }[];
  analysis_mode: "fallback" | "llm";
}

export const previewIntent = (query: string, params: Params, signal?: AbortSignal) =>
  apiCall<IntentPreview>("POST", "/intent/preview", { query, params }, {}, signal);

/** Невалидный JSON/форма ответа не должны ронять UI — превращаем в понятную ошибку. */
export function checkSnapshot(s: unknown): Snapshot {
  const x = s as Partial<Snapshot> | null;
  if (!x || typeof x !== "object" || typeof x.search_id !== "string" || typeof x.state !== "string" || typeof x.revision !== "number" || typeof x.trip_id !== "string")
    throw new ApiError(0, "BAD_JSON", "Сервер вернул некорректный ответ", true);
  return x as Snapshot;
}

/** Разбор текстового SSE-потока: блоки разделены пустой строкой; данные — JSON Snapshot. Любое имя события считается обновлением. */
export function parseSse(buf: string): { events: { id?: string; event?: string; data: string }[]; rest: string } {
  const parts = buf.replace(/\r\n/g, "\n").split("\n\n");
  const rest = parts.pop() ?? "";
  const events = parts.map((blk) => {
    const e: { id?: string; event?: string; data: string } = { data: "" };
    const data: string[] = [];
    for (const line of blk.split("\n")) {
      if (line.startsWith(":")) continue;
      const i = line.indexOf(":"); const k = i < 0 ? line : line.slice(0, i); const v = i < 0 ? "" : line.slice(i + 1).replace(/^ /, "");
      if (k === "id") e.id = v; else if (k === "event") e.event = v; else if (k === "data") data.push(v);
    }
    e.data = data.join("\n");
    return e;
  }).filter((e) => e.data);
  return { events, rest };
}

/** SSE через fetch (cookie + любые имена событий). Возвращает, когда поток закрылся; бросает при обрыве/ошибке статуса. */
export async function streamSearch(id: string, onSnapshot: (s: Snapshot) => void, signal: AbortSignal): Promise<void> {
  if (!isLive) throw new ApiError(0, "CONFIG", "Нет адреса backend");
  const r = await fetch(`${BASE}/api/v1/searches/${enc(id)}/events`, { credentials: "include", headers: { Accept: "text/event-stream" }, signal });
  if (!r.ok || !r.body) throw new ApiError(r.status, "SSE", "Поток событий недоступен", true);
  const reader = r.body.getReader(); const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) return;
    buf += dec.decode(value, { stream: true });
    const { events, rest } = parseSse(buf); buf = rest;
    for (const ev of events) {
      try { const s = checkSnapshot(JSON.parse(ev.data)); onSnapshot(s); if (isTerminal(s.state)) return; } catch { /* битое событие пропускаем — догонит polling */ }
    }
  }
}
