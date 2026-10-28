// Локальное распознавание запроса → Params + список недостающего. Владелец: Frontend №1.
// ВАЖНО: это НЕ DeepSeek. Контракт v0.3 не содержит intent/preview; пока BE1/BE2 его не утвердили, викторина строится на этом
// детерминированном разборе (fixture-режим). Позже `parseIntent` заменяется вызовом preview — компоненты не меняются.
// Принцип: берём только то, что явно написано; не угадываем — недостающее спрашиваем или оставляем пустым.
import type { Params, Wish } from "../../api/v03Search";

export type Missing = "dates" | "travelers" | "origin" | "budget";
export interface Understood { plan: Params; monthHint?: string; missing: Missing[] }

const CITY: Record<string, string> = {
  москвы: "Москва", москва: "Москва", петербурга: "Санкт-Петербург", "санкт-петербурга": "Санкт-Петербург", казани: "Казань", екатеринбурга: "Екатеринбург",
  новосибирска: "Новосибирск", сочи: "Сочи", краснодара: "Краснодар", самары: "Самара", уфы: "Уфа", перми: "Пермь", нижнего: "Нижний Новгород",
  калининграда: "Калининград", владивостока: "Владивосток", минска: "Минск", ростова: "Ростов-на-Дону",
};
const MONTHS = ["январ", "феврал", "март", "апрел", "ма[йя]", "июн", "июл", "август", "сентябр", "октябр", "ноябр", "декабр"];
const MONTH_NAME = ["январе", "феврале", "марте", "апреле", "мае", "июне", "июле", "августе", "сентябре", "октябре", "ноябре", "декабре"];
const NUM_WORD: Record<string, number> = { один: 1, одна: 1, одного: 1, двое: 2, двоих: 2, два: 2, две: 2, трое: 3, троих: 3, три: 3, четверо: 4, четверых: 4, четыре: 4, пять: 5, пятеро: 5 };
const iso = (y: number, m: number, d: number) => `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;

export function parseIntent(query: string, base: Params = {}, now = new Date()): Understood {
  const t = query.toLowerCase().replace(/ё/g, "е");
  const plan: Params = { ...base };
  let monthHint: string | undefined;

  if (!plan.duration_days) {
    const m = t.match(/(\d{1,2})\s*(?:дн|день|дня|дней|суток|ноч)/);
    if (m && +m[1] >= 1 && +m[1] <= 30) plan.duration_days = +m[1];
    else if (/недел[юи]/.test(t)) plan.duration_days = 7;
  }
  if (!plan.origin) {
    const m = t.match(/(?<![а-я])из\s+([а-я-]+(?:\s+[а-я-]+)?)/);
    const w = m && (CITY[m[1]] ?? CITY[m[1].split(" ")[0]]);
    if (w) plan.origin = w;
  }
  if (!plan.travelers) {
    const kids = /(с\s+(?:ребенк|детьм|дет)|ребенок|дети)/.test(t);
    const a = t.match(/(\d)\s*взросл/) ?? t.match(/(один|одна|двое|двоих|два|две|трое|троих|три|четверо|четверых|четыре|пять|пятеро)\s+взросл/);
    let adults: number | undefined = a ? (/\d/.test(a[1]) ? +a[1] : NUM_WORD[a[1]]) : undefined;
    if (adults == null) {
      if (/вдвоем|на\s+двоих|двое(?![а-я])|с\s+(?:женой|мужем|девушкой|парнем|подругой|другом)/.test(t)) adults = 2;
      else if (/(?<![а-я])(?:один|одна|сам|сама)(?![а-я])|соло/.test(t)) adults = 1;
    }
    // дети без возрастов — возраст нужен для тарифов, поэтому состав остаётся «неизвестным» и уточняется
    if (adults && adults >= 1 && adults <= 9 && !kids) plan.travelers = { adults, children_ages: [] };
  }
  if (!plan.budget) {
    const m = t.match(/(?:до|бюджет[^\d]{0,12}|не\s+больше|максимум)\s*(\d[\d\s.]*)\s*(тыс\w*|т\.?\s?р|к(?![а-я])|₽|руб\w*|р(?![а-я]))?/);
    if (m) {
      let n = parseInt(m[1].replace(/[\s.]/g, ""), 10);
      if (m[2] && /^(тыс|т\.?\s?р|к)/.test(m[2])) n *= 1000;
      if (n >= 1000 && n <= 90_000_000) plan.budget = { amount_minor: n * 100, currency: "RUB" };
    }
  }
  if (!plan.dates) {
    const iso2 = t.match(/(\d{4}-\d{2}-\d{2}).{1,6}?(\d{4}-\d{2}-\d{2})/);
    const r = t.match(new RegExp(`с\\s+(\\d{1,2})\\s*(${MONTHS.join("|")})?\\w*\\s+по\\s+(\\d{1,2})\\s+(${MONTHS.join("|")})\\w*`));
    if (iso2) plan.dates = { start_date: iso2[1], end_date: iso2[2] };
    else if (r) {
      const em = MONTHS.findIndex((x) => new RegExp(`^${x}`).test(r[4])), sm = r[2] ? MONTHS.findIndex((x) => new RegExp(`^${x}`).test(r[2])) : em;
      let y = now.getFullYear(); if (new Date(y, em, +r[3]) < now) y++;
      const sy = sm > em ? y - 1 : y;
      if (sm >= 0 && em >= 0) plan.dates = { start_date: iso(sy, sm, +r[1]), end_date: iso(y, em, +r[3]) };
    }
    if (!plan.dates) {
      const i = MONTHS.findIndex((x) => new RegExp(`(?<![а-я])в\\s+${x}\\w*`).test(t));
      if (i >= 0) monthHint = `в ${MONTH_NAME[i]}`;
    }
  }
  const wishes = new Set<Wish>(plan.wishes ?? []);
  if (/прям(?:ой|ым|ого)\s+рейс|без\s+пересадок/.test(t)) wishes.add("direct_flight");
  if (/(у|рядом\s+с)\s+мор|первая\s+линия/.test(t)) wishes.add("near_sea");
  if (/вид\s+на\s+мор/.test(t)) wishes.add("sea_view");
  if (/завтрак/.test(t)) wishes.add("breakfast");
  if (wishes.size) plan.wishes = [...wishes];

  const missing: Missing[] = [];
  if (!plan.dates) missing.push("dates");
  if (!plan.travelers) missing.push("travelers");
  if (!plan.origin) missing.push("origin");
  if (!plan.budget) missing.push("budget");
  return { plan, monthHint, missing };
}

/** Проверка плана перед отправкой: человекочитаемые ошибки по полям. */
export function validatePlan(p: Params, today = new Date().toISOString().slice(0, 10)): Partial<Record<"dates" | "duration" | "travelers" | "budget" | "origin", string>> {
  const e: Partial<Record<"dates" | "duration" | "travelers" | "budget" | "origin", string>> = {};
  if (p.dates && p.dates.start_date && p.dates.end_date) {
    const { start_date: a, end_date: b } = p.dates;
    if (a < today) e.dates = "Дата начала уже прошла";
    else if (b < a) e.dates = "Обратно — раньше, чем туда";
    else if ((Date.parse(b) - Date.parse(a)) / 864e5 + 1 > 30) e.dates = "Не больше 30 дней";
  }
  if (p.duration_days != null && (p.duration_days < 1 || p.duration_days > 30)) e.duration = "От 1 до 30 дней";
  if (p.travelers) {
    const { adults: n, children_ages: k } = p.travelers;
    if (n < 1 || n > 9) e.travelers = "Взрослых от 1 до 9";
    else if (k.length > 9 - n || k.length > 8) e.travelers = "Слишком много детей для такого состава";
    else if (k.some((x) => !Number.isInteger(x) || x < 0 || x > 17)) e.travelers = "Возраст ребёнка — от 0 до 17";
  }
  if (p.budget && !(p.budget.amount_minor >= 100)) e.budget = "Укажите сумму больше нуля";
  return e;
}
