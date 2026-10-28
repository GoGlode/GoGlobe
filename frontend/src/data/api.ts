// Демо-поиск для UI на макетах с имитацией задержки (без сети). В живом режиме не используется.
import type { SearchStatus } from "../api/types";
import { TRIPS } from "./trips";
import type { SearchParamsUI, Trip } from "./types";

export const SEARCH_STEPS = ["Разбираю запрос…", "Ищу перелёты…", "Ищу отели…", "Проверяю бюджет и даты…", "Ранжирую и объясняю варианты…"];

export interface SearchResult { status: SearchStatus; trips: Trip[]; clarifyingQuestion?: string; warnings: string[] }

const FORCEABLE: SearchStatus[] = ["ok", "needs_clarification", "partial", "empty", "error"];
/** Демо-статус по запросу (docs/demo-scenario.md): «Хочу в Турцию» → уточнение, бюджет до 30 000 ₽ → пусто. `?status=…` в адресе форсирует любой из пяти. */
export function demoStatus(query: string, forced?: string | null): SearchStatus {
  if (FORCEABLE.includes(forced as SearchStatus)) return forced as SearchStatus;
  const m = query.match(/(\d[\d\s]*)\s*(тыс\w*|₽|руб\w*)/i);
  const amount = m ? parseInt(m[1].replace(/\s/g, ""), 10) * (/тыс/i.test(m[2]) ? 1000 : 1) : 0;
  if (amount && amount < 30_000) return "empty";
  if (!/\d/.test(query) && query.trim().split(/\s+/).length <= 3) return "needs_clarification";
  return "ok";
}

/** ДЕМО-поиск (только dev/VITE_DEMO_MODE): имитация шагов на макетах. Настоящий поиск — api/searches.ts (v0.3) через SearchContext. */
export async function searchTrips(query: string, _params: SearchParamsUI, onStep?: (i: number) => void, forced?: string | null): Promise<SearchResult> {
  for (let i = 0; i < SEARCH_STEPS.length; i++) {
    onStep?.(i);
    await new Promise((r) => setTimeout(r, 650));
  }
  const status = demoStatus(query, forced);
  if (status === "error") throw new Error("demo error");
  if (status === "needs_clarification") return { status, trips: [], clarifyingQuestion: "На сколько дней и в какие даты вы планируете поездку?", warnings: [] };
  if (status === "empty") return { status, trips: [], warnings: [] };
  if (status === "partial") return { status, trips: TRIPS.slice(0, 3), warnings: ["Перелёты: источник временно недоступен, показаны данные из кэша.", "Цены отелей могли измениться — проверьте на странице бронирования."] };
  return { status, trips: TRIPS, warnings: [] };
}
