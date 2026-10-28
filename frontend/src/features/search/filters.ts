// Фильтры и сортировка выдачи: цена, звёзды отеля, прямой рейс. Чистые функции — без состояния и UI.
import type { Trip } from "../../data/types";

export type Sort = "default" | "price-asc" | "price-desc";
export interface Filters { direct: boolean; stars: 0 | 4 | 5; sort: Sort }
export const NO_FILTERS: Filters = { direct: false, stars: 0, sort: "default" };
export const isFiltered = (f: Filters) => f.direct || f.stars > 0 || f.sort !== "default";

/** Звёзды неизвестны → вариант не проходит фильтр по звёздам (не можем подтвердить). Цены сравниваются как есть: в одной выдаче валюта одна. */
export function applyFilters(trips: Trip[], f: Filters): Trip[] {
  const out = trips.filter((t) => (!f.direct || t.direct === true) && (f.stars === 0 || (t.stars ?? 0) >= f.stars));
  if (f.sort === "default") return out;
  const k = f.sort === "price-asc" ? 1 : -1;
  return [...out].sort((a, b) => k * (a.price.amount - b.price.amount));
}
