import type { Money } from "./types";

const SYM = { USD: "$", RUB: "₽", EUR: "€" } as const;
export function money(m: Money): string {
  const n = Math.round(m.amount).toLocaleString("ru-RU").replace(/ /g, " ");
  return m.currency === "RUB" ? `${n} ₽` : `${SYM[m.currency]}${n}`;
}

/** «1 человек / 2 человека / 5 человек» */
export function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

const shortDate = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short", timeZone: "UTC" });
/** «10–16 нояб.» / «28 нояб. – 3 дек.» по датам YYYY-MM-DD */
export function dateRange(from: string, to: string): string {
  const a = new Date(`${from}T00:00:00Z`), b = new Date(`${to}T00:00:00Z`);
  if (a.getUTCMonth() === b.getUTCMonth() && a.getUTCFullYear() === b.getUTCFullYear()) return `${a.getUTCDate()}–${shortDate.format(b)}`;
  return `${shortDate.format(a)} – ${shortDate.format(b)}`;
}
