// Единая точка общения с backend. Владелец: Frontend №1 (контракт — Backend №1).
import type { SearchEvent, SearchRequest, SearchResponse } from "./types";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function search(req: SearchRequest): Promise<SearchResponse> {
  const r = await fetch(`${API}/api/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!r.ok) throw new Error(`API ${r.status}`);
  return r.json();
}

/** Подписка на статусы поиска (SSE). Возвращает функцию отписки. */
export function subscribeEvents(searchId: string, onEvent: (e: SearchEvent) => void): () => void {
  const es = new EventSource(`${API}/api/search/${searchId}/events`);
  es.onmessage = (m) => {
    const ev: SearchEvent = JSON.parse(m.data);
    onEvent(ev);
    if (ev.stage === "done" || ev.stage === "error") es.close();
  };
  es.onerror = () => es.close();
  return () => es.close();
}
