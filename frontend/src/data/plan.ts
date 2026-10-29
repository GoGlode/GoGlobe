// Params (контракт v0.3) ↔ подписи UI. Структурированный plan — единственный источник правды для запроса.
import type { Params } from "../api/v03Search";
import { dateRange, money, plural } from "./format";
import type { SearchParamsUI } from "./types";

export function travelersLabel(t: NonNullable<Params["travelers"]>): string {
  const k = t.children_ages.length;
  return `${t.adults} ${plural(t.adults, "взрослый", "взрослых", "взрослых")}${k ? `, ${k} ${plural(k, "ребёнок", "ребёнка", "детей")}` : ""}`;
}

export function uiFromPlan(plan: Params, prev: SearchParamsUI = {}): SearchParamsUI {
  const clean: Params = Object.fromEntries(Object.entries(plan).filter(([, v]) => v !== undefined && !(Array.isArray(v) && v.length === 0))) as Params;
  return {
    ...prev,
    dates: clean.dates ? dateRange(clean.dates.start_date, clean.dates.end_date) : undefined,
    travelers: clean.travelers ? travelersLabel(clean.travelers) : undefined,
    budget: clean.budget ? `до ${money({ amount: clean.budget.amount_minor / 100, currency: "RUB" })}` : undefined,
    plan: clean,
  };
}

/** Тело params для POST /searches: ровно то, что известно; пустое не отправляем. */
export function toApiParams(ui: SearchParamsUI): Params | undefined {
  const p = ui.plan;
  return p && Object.keys(p).length ? p : undefined;
}
