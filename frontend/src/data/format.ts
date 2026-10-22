import type { Money } from "./types";

const SYM = { USD: "$", RUB: "₽", EUR: "€" } as const;
export function money(m: Money): string {
  const n = Math.round(m.amount).toLocaleString("ru-RU").replace(/ /g, " ");
  return m.currency === "RUB" ? `${n} ₽` : `${SYM[m.currency]}${n}`;
}
