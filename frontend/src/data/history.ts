// История поисковых запросов. В API-контракте v0 (docs/api-contract.md) эндпоинта истории нет,
// поэтому история хранится локально (state/HistoryContext.tsx). DEMO_HISTORY — примеры для показа,
// помечены demo: true и в интерфейсе подписаны как примеры, а не как данные пользователя.
import type { SearchParamsUI } from "./types";

export interface HistoryEntry {
  id: string;
  title: string;
  query: string;
  params: SearchParamsUI;
  days?: number;
  createdAt: string; // ISO
  image: string;
  /** id поездок из выдачи; пустой массив — результатов нет */
  resultTripIds: string[];
  demo?: boolean;
}

const P = "/assets/photos/";

/** Момент «сегодня/вчера/N дней назад в HH:MM» — чтобы примеры раскладывались по группам. */
function at(daysAgo: number, time: string): string {
  const [h, m] = time.split(":").map(Number);
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  d.setHours(h, m, 0, 0);
  return d.toISOString();
}

/** Примеры запросов отключены: история начинается пустой и наполняется только реальными поисками. */
export function demoHistory(): HistoryEntry[] {
  return [];
}

/** Короткое название из текста запроса: первая фраза, не длиннее 42 символов. */
export function titleFromQuery(q: string): string {
  const first = q.trim().split(/[.!?\n]/)[0].trim();
  const t = first.length > 42 ? `${first.slice(0, 41).trimEnd()}…` : first;
  return t.charAt(0).toUpperCase() + t.slice(1);
}
