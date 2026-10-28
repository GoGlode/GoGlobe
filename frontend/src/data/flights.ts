// Поиск перелётов. В API-контракте v0 (docs/api-contract.md) отдельного поиска рейсов нет —
// это ДЕМО-слой: расписания, авиакомпании и цены — примеры, не реальные билеты и не доступность.
// TODO(интеграция): заменить searchFlights на вызов backend, сохранив типы FlightQuery / FlightResult.
import type { Money } from "./types";

export type FlightMode = "round" | "oneway" | "multi";
export type CabinClass = "economy" | "comfort" | "business";
export const CABINS: { id: CabinClass; label: string }[] = [
  { id: "economy", label: "Эконом" }, { id: "comfort", label: "Комфорт" }, { id: "business", label: "Бизнес" },
];

export interface Airport { code: string; city: string; tz: number }
export const AIRPORTS: Airport[] = [
  { code: "SVO", city: "Москва", tz: 3 }, { code: "LED", city: "Санкт-Петербург", tz: 3 },
  { code: "ATH", city: "Афины", tz: 2 }, { code: "IST", city: "Стамбул", tz: 3 }, { code: "AYT", city: "Анталья", tz: 3 },
  { code: "FCO", city: "Рим", tz: 1 }, { code: "BKK", city: "Бангкок", tz: 7 }, { code: "HKT", city: "Пхукет", tz: 7 },
  { code: "NRT", city: "Токио", tz: 9 }, { code: "DPS", city: "Денпасар (Бали)", tz: 8 }, { code: "MLE", city: "Мале", tz: 5 },
  { code: "TBS", city: "Тбилиси", tz: 4 }, { code: "DXB", city: "Дубай", tz: 4 }, { code: "DOH", city: "Доха", tz: 3 },
];
const byCode = (c: string) => AIRPORTS.find((a) => a.code === c)!;
export const airportLabel = (a: Airport) => `${a.city} (${a.code})`;
/** Ищет аэропорт по «Город (КОД)», городу или коду. */
export function findAirport(text: string): Airport | undefined {
  const t = text.trim().toLowerCase();
  if (!t) return undefined;
  return AIRPORTS.find((a) => airportLabel(a).toLowerCase() === t || a.city.toLowerCase() === t || a.code.toLowerCase() === t);
}

export interface Leg { from: string; to: string; date: string } // коды аэропортов, YYYY-MM-DD
export interface FlightQuery { legs: Leg[]; adults: number; cabin: CabinClass }
export interface FlightOption {
  id: string; airline: string; code: string; logoColor: string; flightNo: string;
  from: Airport; to: Airport; date: string; depart: string; arrive: string; arriveDayShift: number;
  minutes: number; stops: number; via?: Airport; layoverMinutes?: number;
  carryOn: string | null; baggage: string | null; meal: string | null; price: Money; demo: true;
}
export interface FlightResult { leg: Leg; options: FlightOption[] }

// Демо-расписания из Москвы. Обратные и из Петербурга строятся из них.
interface Tpl { airline: string; code: string; color: string; dep: string; minutes: number; usd: number; via?: string; lowcost?: boolean }
const ROUTES: Record<string, Tpl[]> = {
  ATH: [{ airline: "Aegean Airlines", code: "A3", color: "#102448", dep: "10:25", minutes: 255, usd: 320 },
    { airline: "Turkish Airlines", code: "TK", color: "#e30a17", dep: "08:50", minutes: 450, usd: 290, via: "IST" }],
  IST: [{ airline: "Turkish Airlines", code: "TK", color: "#e30a17", dep: "09:40", minutes: 230, usd: 210 },
    { airline: "Pegasus", code: "PC", color: "#f2a900", dep: "13:20", minutes: 235, usd: 160, lowcost: true }],
  AYT: [{ airline: "Pegasus", code: "PC", color: "#f2a900", dep: "11:05", minutes: 255, usd: 195, lowcost: true },
    { airline: "Turkish Airlines", code: "TK", color: "#e30a17", dep: "07:15", minutes: 400, usd: 240, via: "IST" }],
  FCO: [{ airline: "Turkish Airlines", code: "TK", color: "#e30a17", dep: "07:15", minutes: 520, usd: 360, via: "IST" },
    { airline: "Aegean Airlines", code: "A3", color: "#102448", dep: "10:25", minutes: 560, usd: 380, via: "ATH" }],
  BKK: [{ airline: "Emirates", code: "EK", color: "#d71921", dep: "09:55", minutes: 900, usd: 610, via: "DXB" },
    { airline: "Qatar Airways", code: "QR", color: "#5c0632", dep: "08:30", minutes: 870, usd: 640, via: "DOH" }],
  HKT: [{ airline: "Qatar Airways", code: "QR", color: "#5c0632", dep: "08:30", minutes: 960, usd: 640, via: "DOH" },
    { airline: "Emirates", code: "EK", color: "#d71921", dep: "09:55", minutes: 990, usd: 670, via: "DXB" }],
  NRT: [{ airline: "Turkish Airlines", code: "TK", color: "#e30a17", dep: "09:00", minutes: 1050, usd: 860, via: "IST" },
    { airline: "Emirates", code: "EK", color: "#d71921", dep: "09:55", minutes: 1150, usd: 910, via: "DXB" }],
  DPS: [{ airline: "Qatar Airways", code: "QR", color: "#5c0632", dep: "08:30", minutes: 1150, usd: 890, via: "DOH" },
    { airline: "Emirates", code: "EK", color: "#d71921", dep: "09:55", minutes: 1190, usd: 930, via: "DXB" }],
  MLE: [{ airline: "Emirates", code: "EK", color: "#d71921", dep: "09:55", minutes: 870, usd: 820, via: "DXB" },
    { airline: "Qatar Airways", code: "QR", color: "#5c0632", dep: "08:30", minutes: 840, usd: 790, via: "DOH" }],
  TBS: [{ airline: "Georgian Airways", code: "A9", color: "#7a1f2b", dep: "11:40", minutes: 190, usd: 210 },
    { airline: "Turkish Airlines", code: "TK", color: "#e30a17", dep: "09:40", minutes: 420, usd: 230, via: "IST" }],
};
const HOME = ["SVO", "LED"];
const CABIN_K: Record<CabinClass, number> = { economy: 1, comfort: 1.6, business: 3.2 };

const toMin = (hhmm: string) => { const [h, m] = hhmm.split(":").map(Number); return h * 60 + m; };
const fmt = (min: number) => `${String(Math.floor(min / 60) % 24).padStart(2, "0")}:${String(min % 60).padStart(2, "0")}`;
const hash = (s: string) => [...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);

function build(leg: Leg, cabin: CabinClass): FlightOption[] {
  const out = HOME.includes(leg.from) ? leg.to : leg.from;
  const reverse = !HOME.includes(leg.from);
  if (!HOME.includes(reverse ? leg.to : leg.from) || !ROUTES[out]) return [];
  const from = byCode(leg.from), to = byCode(leg.to);
  return ROUTES[out].map((t, i) => {
    const extra = leg.from === "LED" || leg.to === "LED" ? 30 : 0;
    const minutes = t.minutes + extra;
    const dep = reverse ? (toMin(t.dep) + 300 + i * 95) % 1440 : toMin(t.dep) + extra;
    const arrAbs = dep + minutes + (to.tz - from.tz) * 60;
    const usd = Math.round((t.usd * (extra ? 1.1 : 1) * CABIN_K[cabin]) / 5) * 5;
    return {
      id: `${leg.from}-${leg.to}-${leg.date}-${t.code}${i}`, airline: t.airline, code: t.code, logoColor: t.color,
      flightNo: `${t.code} ${100 + (hash(leg.from + leg.to + t.code) % 800)}`,
      from, to, date: leg.date, depart: fmt(dep), arrive: fmt(((arrAbs % 1440) + 1440) % 1440), arriveDayShift: Math.floor(arrAbs / 1440),
      minutes, stops: t.via ? 1 : 0, via: t.via ? byCode(t.via) : undefined, layoverMinutes: t.via ? 95 + (hash(t.code + out) % 60) : undefined,
      carryOn: "8 кг", baggage: t.lowcost && cabin === "economy" ? null : cabin === "business" ? "2 × 32 кг" : "23 кг",
      meal: t.lowcost && cabin === "economy" ? null : "включено",
      price: { amount: usd, currency: "USD" }, demo: true,
    };
  });
}

/** Демо-поиск: имитирует задержку сети. Пустой список — маршрута нет в демо-данных. */
export async function searchFlights(q: FlightQuery): Promise<FlightResult[]> {
  await new Promise((r) => setTimeout(r, 900));
  return q.legs.map((leg) => ({ leg, options: build(leg, q.cabin) }));
}

/** Аэропорт назначения для демо-поездок (data/trips.ts). */
export const TRIP_AIRPORT: Record<string, string> = { greece: "ATH", thailand: "HKT", italy: "FCO", japan: "NRT", bali: "DPS" };

export const durationLabel = (min: number) => `${Math.floor(min / 60)}ч ${String(min % 60).padStart(2, "0")}м`;
