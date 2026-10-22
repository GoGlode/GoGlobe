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

export function demoHistory(): HistoryEntry[] {
  return [
    { id: "demo-greece", title: "Неделя у моря в Греции", query: "Хочу неделю у моря с красивыми видами, уютными отелями и вкусной едой",
      params: { travelers: "2 человека", budget: "до 150 000 ₽" }, days: 7, createdAt: at(0, "18:42"), image: P + "hero.jpg",
      resultTripIds: ["greece", "italy", "thailand"], demo: true },
    { id: "demo-thailand", title: "Таиланд в феврале", query: "Пляжи, природа, хорошие отели, не очень жарко",
      params: { travelers: "2 человека", budget: "до 250 000 ₽" }, days: 10, createdAt: at(0, "14:26"), image: P + "thailand-cover.jpg",
      resultTripIds: ["thailand", "bali"], demo: true },
    { id: "demo-italy", title: "Италия: Рим и побережье", query: "Города, море, вкусная кухня и красивые локации",
      params: { travelers: "2 человека", budget: "до 300 000 ₽" }, days: 10, createdAt: at(1, "20:15"), image: P + "italy-cover.jpg",
      resultTripIds: ["italy", "greece"], demo: true },
    { id: "demo-japan", title: "Япония весной", query: "Цветение сакуры, Токио, Киото, традиционная культура",
      params: { travelers: "2 человека" }, days: 9, createdAt: at(1, "11:03"), image: P + "japan-cover.jpg",
      resultTripIds: ["japan"], demo: true },
    { id: "demo-georgia", title: "Грузия на майские", query: "Горы, вино и старый Тбилиси, недалеко лететь",
      params: { travelers: "3 человека" }, days: 5, createdAt: at(4, "09:30"), image: P + "georgia-cover.jpg",
      resultTripIds: [], demo: true },
  ];
}

/** Короткое название из текста запроса: первая фраза, не длиннее 42 символов. */
export function titleFromQuery(q: string): string {
  const first = q.trim().split(/[.!?\n]/)[0].trim();
  const t = first.length > 42 ? `${first.slice(0, 41).trimEnd()}…` : first;
  return t.charAt(0).toUpperCase() + t.slice(1);
}
