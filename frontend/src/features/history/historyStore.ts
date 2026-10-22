// История запросов (localStorage). Пишет Home при отправке, читает HistoryPage.
const KEY = "goglobe.history.v1";
export interface HistoryItem { q: string; at: number }

export function readHistory(): HistoryItem[] { try { return JSON.parse(localStorage.getItem(KEY) ?? "[]"); } catch { return []; } }
export function pushHistory(q: string) {
  try { localStorage.setItem(KEY, JSON.stringify([{ q, at: Date.now() }, ...readHistory().filter((h) => h.q !== q)].slice(0, 30))); } catch { /* ignore */ }
}
export function clearHistory() { try { localStorage.removeItem(KEY); } catch { /* ignore */ } }
