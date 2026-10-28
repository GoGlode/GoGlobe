// Отображение Price из API v0.3: сумма только при известной цене, всегда с базой расчёта, охватом и свежестью.
import { money } from "../../data/format";
import type { Part, Price, PriceBasis } from "../../api/v03";

export const BASIS: Record<PriceBasis, string> = {
  trip_total: "за всю поездку", party_stay_total: "за проживание всей группой", party_return_total: "за перелёт туда-обратно, вся группа",
  room_night: "за ночь, за номер", person_total: "за человека",
};
const PART: Record<Part, string> = { hotels: "отель", flights: "перелёты", activities: "активности", transfers: "трансферы" };
export const partList = (p: Part[]) => p.map((x) => PART[x]).join(", ");

const dt = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });
export const when = (iso?: string | null) => { const t = iso ? Date.parse(iso) : NaN; return Number.isNaN(t) ? null : dt.format(t); };

export type Freshness = "unknown" | "stale" | "expired" | "fresh";
export function freshness(p: Price, now = Date.now()): Freshness {
  if (p.stale) return "stale";
  if (p.valid_until && Date.parse(p.valid_until) < now) return "expired";
  return p.checked_at ? "fresh" : "unknown";
}

export interface PriceView { amount: string | null; basis: string; status: string; covers: string | null; excludes: string | null; checked: string | null; warn: string | null }
export function priceView(p: Price, now = Date.now()): PriceView {
  const known = p.status !== "unknown" && p.money != null;
  const f = freshness(p, now);
  const checked = when(p.checked_at);
  return {
    amount: known ? money({ amount: p.money!.amount_minor / 100, currency: p.money!.currency }) : null,
    basis: BASIS[p.basis],
    status: p.status === "quoted" ? "Найденный тариф (не бронь)" : p.status === "estimated" ? "Оценка" : "Цена неизвестна",
    covers: p.coverage.length ? `Включено: ${partList(p.coverage)}` : null,
    excludes: p.exclusions.length ? `Не включено: ${partList(p.exclusions)}` : null,
    checked: checked ? `проверено ${checked}` : null,
    warn: !known ? null : f === "stale" || f === "expired" ? "Цена могла измениться — проверьте у поставщика" : p.status === "estimated" ? "Ориентировочная оценка, не тариф" : null,
  };
}

export const isHttp = (u?: string | null): u is string => !!u && /^https?:\/\//i.test(u);
export const hhmm = (iso: string, tz: string) => { try { return new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit", timeZone: tz }).format(Date.parse(iso)); } catch { return iso.slice(11, 16); } };
export const duration = (min: number) => `${Math.floor(min / 60)} ч ${String(min % 60).padStart(2, "0")} мин`;
