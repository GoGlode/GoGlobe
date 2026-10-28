// Викторина перед поиском. Владелец: Frontend №1.
// Вопросы — только про то, чего нет в тексте и параметрах (1–4); в конце — «Как я понял запрос» с правкой всех значений.
// Ответы кладутся прямо в Params контракта v0.3 (даты, состав с возрастами детей, бюджет в копейках, wishes) — не в строки.
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { Params, Wish } from "../../api/v03Search";
import { dateRange, money } from "../../data/format";
import { travelersLabel, uiFromPlan } from "../../data/plan";
import type { SearchParamsUI } from "../../data/types";
import { Icon, type IconName } from "../../ui";
import { parseIntent, validatePlan, type Missing } from "./intent";

interface Opt { id: string; label: string; sub?: string; icon: IconName }
const HINT: Opt[] = [
  { id: "в ближайший месяц", label: "Ближайший месяц", sub: "Скоро в путь", icon: "clock" },
  { id: "через 2–3 месяца", label: "Через 2–3 месяца", sub: "Время спланировать", icon: "calendar" },
  { id: "летом", label: "Летом", sub: "Июнь – август", icon: "sun" },
  { id: "зимой", label: "Зимой", sub: "Декабрь – февраль", icon: "leaf" },
];
const BUDGETS = [
  { id: "100", v: 100_000, label: "До 100 000 ₽", sub: "Экономно", icon: "wallet" as IconName },
  { id: "150", v: 150_000, label: "До 150 000 ₽", sub: "Комфортно", icon: "wallet" as IconName },
  { id: "250", v: 250_000, label: "До 250 000 ₽", sub: "Щедро", icon: "wallet" as IconName },
];
const MOOD: Opt[] = [
  { id: "Море и пляж", label: "Море и пляж", icon: "waves" }, { id: "Культура и история", label: "Культура и история", icon: "landmark" },
  { id: "Природа", label: "Природа", icon: "leaf" }, { id: "Гастрономия", label: "Гастрономия", icon: "utensils" },
  { id: "Активный отдых", label: "Активный отдых", icon: "nav" }, { id: "Спокойный отдых и спа", label: "Спа и релакс", icon: "spa" },
];
const WISHES: { id: Wish; label: string; icon: IconName }[] = [
  { id: "direct_flight", label: "Прямой рейс", icon: "plane" }, { id: "near_sea", label: "Рядом с морем", icon: "waves" },
  { id: "sea_view", label: "Вид на море", icon: "view" }, { id: "breakfast", label: "Завтрак", icon: "coffee" },
];
const CITIES = ["Москва", "Санкт-Петербург", "Казань", "Екатеринбург", "Сочи"];
const TITLE: Record<Step, { title: string; hint: string }> = {
  dates: { title: "Когда поедем?", hint: "Точные даты или пока не знаете" },
  travelers: { title: "Кто едет?", hint: "Возраст детей нужен для цен на отели и рейсы" },
  origin: { title: "Откуда летим?", hint: "Чтобы подобрать перелёты" },
  budget: { title: "Какой бюджет?", hint: "Максимум на всю поездку" },
  prefs: { title: "Чего хочется?", hint: "Можно выбрать несколько" },
  review: { title: "Как я понял запрос", hint: "Проверьте и поправьте, если нужно" },
};
type Step = Missing | "prefs" | "review";
const today = () => new Date().toISOString().slice(0, 10);
const ages = (s: string) => s.split(/[\s,;]+/).filter(Boolean).map(Number);

export default function QuizSheet({ query, params, onDone, onClose }: {
  query: string; params: SearchParamsUI; onDone: (query: string, params: SearchParamsUI) => void; onClose: () => void;
}) {
  // Что уже известно — не спрашиваем. Вопросов не больше 4; «чего хочется» — только если остался запас и пожеланий в тексте нет.
  const u = useMemo(() => parseIntent(query, params.plan ?? {}), [query, params.plan]);
  const steps = useMemo<Step[]>(() => { const q: Step[] = u.missing.slice(0, 4); if (q.length > 0 && q.length < 4 && !u.plan.wishes?.length) q.push("prefs"); return [...q, "review"]; }, [u]);
  const [i, setI] = useState(0);
  const step = steps[i];
  const [plan, setPlan] = useState<Params>(u.plan);
  const [hint, setHint] = useState<string | null>(null); // мягкая подсказка по времени — уходит в текст запроса
  const [mood, setMood] = useState<string[]>([]);
  const [datesMode, setDatesMode] = useState<"exact" | "unknown" | null>(null);
  const [kidsText, setKidsText] = useState("");
  const [who, setWho] = useState<"1" | "2" | "kids" | "group" | null>(null);
  const [budgetText, setBudgetText] = useState("");
  const timer = useRef<number>();
  useEffect(() => () => clearTimeout(timer.current), []);
  useEffect(() => {
    const on = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [onClose]);

  const patch = (p: Partial<Params>) => setPlan((c) => ({ ...c, ...p }));
  const go = () => setI((n) => Math.min(n + 1, steps.length - 1));
  const advance = (fn: () => void) => { fn(); clearTimeout(timer.current); timer.current = window.setTimeout(go, 260); };
  const errors = validatePlan(plan);
  const from = plan.dates?.start_date ?? "", to = plan.dates?.end_date ?? "";
  const setDates = (a: string, b: string) => patch({ dates: a || b ? { start_date: a, end_date: b } : undefined, ...(a && b && b >= a ? { duration_days: Math.min(30, Math.round((Date.parse(b) - Date.parse(a)) / 864e5) + 1) } : {}) });
  const datesIncomplete = !!plan.dates && (!from || !to);
  const stepBlocked =
    (step === "dates" && datesMode === "exact" && (datesIncomplete || !!errors.dates)) ||
    (step === "travelers" && (who === "kids" || who === "group") && (!!errors.travelers || (who === "kids" && ages(kidsText).length === 0)));
  const reviewBlocked = !!(errors.dates || errors.duration || errors.travelers || errors.budget) || datesIncomplete;

  const finish = () => {
    const p: Params = { ...plan };
    if (p.dates && p.dates.start_date && p.dates.end_date) p.duration_days = Math.min(30, Math.round((Date.parse(p.dates.end_date) - Date.parse(p.dates.start_date)) / 864e5) + 1);
    else delete p.dates;
    if (!p.origin?.trim()) delete p.origin; else p.origin = p.origin.trim();
    const parts = [query.trim()];
    if (hint && !p.dates) parts.push(`Когда: ${hint}`);
    else if (u.monthHint && !p.dates) parts.push(`Когда: ${u.monthHint}`);
    if (mood.length) parts.push(`Хочется: ${mood.map((m) => m.toLowerCase()).join(", ")}`);
    onDone(parts.join(". "), uiFromPlan(p, params));
  };
  const next = () => (step === "review" ? finish() : go());

  const host = document.querySelector(".app") ?? document.body;
  return createPortal(
    <div className="quiz" role="dialog" aria-modal="true" aria-label="Уточните поездку">
      <button type="button" className="quiz__scrim" aria-label="Закрыть" onClick={onClose} />
      <div className="quiz__sheet">
        <div className="quiz__top">
          <div className="quiz__bars" aria-hidden="true">{steps.map((_, k) => <i key={k} className={k <= i ? "is-on" : ""} />)}</div>
          {step !== "review" && <button type="button" className="quiz__skip" onClick={() => setI(steps.length - 1)}>Пропустить</button>}
        </div>
        <div className="quiz__body" key={step}>
          <small>{step === "review" ? "Проверка" : `Вопрос ${i + 1} из ${steps.length - 1}`}</small>
          <h2>{TITLE[step].title}</h2>
          {TITLE[step].hint && <p className="muted">{TITLE[step].hint}</p>}

          {step === "dates" && <>
            {u.monthHint && <p className="quiz__note">Вы писали: «{u.monthHint}». Для цен нужны точные даты — или оставим гибко.</p>}
            <div className="quiz__grid" role="radiogroup">
              <Card o={{ id: "exact", label: "Свои даты", sub: "Выберу сам", icon: "pencil" }} on={datesMode === "exact"} onPick={() => { setDatesMode("exact"); setHint(null); }} />
              <Card o={{ id: "unknown", label: "Пока не знаю", sub: "Подберите маршрут", icon: "globe" }} on={datesMode === "unknown"} onPick={() => advance(() => { setDatesMode("unknown"); patch({ dates: undefined }); })} />
              {!u.monthHint && HINT.map((o) => <Card key={o.id} o={o} on={hint === o.id} onPick={() => advance(() => { setHint(o.id); setDatesMode("unknown"); patch({ dates: undefined }); })} />)}
            </div>
            {datesMode === "exact" && (
              <div className="quiz__dates fade-up">
                <label>Туда<input type="date" min={today()} value={from} onChange={(e) => setDates(e.target.value, to)} /></label>
                <label>Обратно<input type="date" min={from || today()} value={to} onChange={(e) => setDates(from, e.target.value)} /></label>
                {errors.dates && from && to && <p className="home__error" role="alert">{errors.dates}</p>}
              </div>
            )}
          </>}

          {step === "travelers" && <>
            <div className="quiz__grid" role="radiogroup">
              <Card o={{ id: "1", label: "Один", sub: "1 взрослый", icon: "user" }} on={who === "1"} onPick={() => advance(() => { setWho("1"); patch({ travelers: { adults: 1, children_ages: [] } }); })} />
              <Card o={{ id: "2", label: "Вдвоём", sub: "2 взрослых", icon: "heart" }} on={who === "2"} onPick={() => advance(() => { setWho("2"); patch({ travelers: { adults: 2, children_ages: [] } }); })} />
              <Card o={{ id: "kids", label: "С детьми", sub: "Укажу возраст", icon: "users" }} on={who === "kids"} onPick={() => { setWho("kids"); patch({ travelers: { adults: plan.travelers?.adults ?? 2, children_ages: ages(kidsText).filter((x) => !Number.isNaN(x)) } }); }} />
              <Card o={{ id: "group", label: "Компания", sub: "3 и больше", icon: "users" }} on={who === "group"} onPick={() => { setWho("group"); patch({ travelers: { adults: Math.max(3, plan.travelers?.adults ?? 3), children_ages: [] } }); }} />
            </div>
            {(who === "kids" || who === "group") && (
              <div className="quiz__dates fade-up">
                <Adults value={plan.travelers?.adults ?? 2} min={who === "group" ? 3 : 1} onChange={(n) => patch({ travelers: { adults: n, children_ages: plan.travelers?.children_ages ?? [] } })} />
                {who === "kids" && <label>Возраст детей через запятую
                  <input inputMode="numeric" placeholder="Например: 4, 9" value={kidsText} onChange={(e) => { setKidsText(e.target.value); patch({ travelers: { adults: plan.travelers?.adults ?? 2, children_ages: ages(e.target.value).filter((x) => !Number.isNaN(x)) } }); }} />
                </label>}
                {errors.travelers && <p className="home__error" role="alert">{errors.travelers}</p>}
              </div>
            )}
          </>}

          {step === "origin" && (
            <div className="quiz__dates fade-up">
              <input aria-label="Город вылета" value={plan.origin ?? ""} maxLength={200} autoComplete="off" placeholder="Например, Москва" onChange={(e) => patch({ origin: e.target.value })} />
              <div className="home__row">{CITIES.map((c) => <button key={c} type="button" className="home__quick" onClick={() => patch({ origin: c })}>{c}</button>)}</div>
            </div>
          )}

          {step === "budget" && <>
            <div className="quiz__grid" role="radiogroup">
              {BUDGETS.map((o) => <Card key={o.id} o={o} on={plan.budget?.amount_minor === o.v * 100} onPick={() => advance(() => { setBudgetText(""); patch({ budget: { amount_minor: o.v * 100, currency: "RUB" } }); })} />)}
              <Card o={{ id: "inf", label: "Без ограничений", sub: "Лучшее", icon: "star" }} on={!plan.budget && budgetText === "inf"} onPick={() => advance(() => { setBudgetText("inf"); patch({ budget: undefined }); })} />
            </div>
            <div className="quiz__dates">
              <label>Своя сумма, ₽<input type="number" inputMode="numeric" min={1} step={1000} placeholder="Например, 120000" value={budgetText === "inf" ? "" : budgetText}
                onChange={(e) => { setBudgetText(e.target.value); const n = Math.round(Number(e.target.value)); patch({ budget: n > 0 ? { amount_minor: n * 100, currency: "RUB" } : undefined }); }} /></label>
            </div>
          </>}

          {step === "prefs" && <>
            <div className="quiz__grid" role="group">
              {WISHES.map((o) => { const on = !!plan.wishes?.includes(o.id); return <Card key={o.id} o={o} multi on={on} onPick={() => patch({ wishes: on ? plan.wishes!.filter((x) => x !== o.id) : [...(plan.wishes ?? []), o.id] })} />; })}
              {MOOD.map((o) => <Card key={o.id} o={o} multi on={mood.includes(o.id)} onPick={() => setMood(mood.includes(o.id) ? mood.filter((m) => m !== o.id) : [...mood, o.id])} />)}
            </div>
          </>}

          {step === "review" && (
            <div className="quiz__review fade-up">
              <p className="quiz__orig">«{query.trim()}»</p>
              <label>Откуда<input value={plan.origin ?? ""} maxLength={200} placeholder="не указано" onChange={(e) => patch({ origin: e.target.value })} /></label>
              <div className="home__row">
                <label>Туда<input type="date" min={today()} value={from} onChange={(e) => setDates(e.target.value, to)} /></label>
                <label>Обратно<input type="date" min={from || today()} value={to} onChange={(e) => setDates(from, e.target.value)} /></label>
              </div>
              {errors.dates && <p className="home__error" role="alert">{errors.dates}</p>}
              {datesIncomplete && <p className="home__error" role="alert">Укажите обе даты или очистите поля</p>}
              {!plan.dates && <small className="muted">Без дат соберём маршрут без цен на отели и рейсы.{u.monthHint ? ` Вы писали «${u.monthHint}».` : ""}</small>}
              {plan.dates && <button type="button" className="atrip__link" onClick={() => patch({ dates: undefined })}>Очистить даты</button>}
              <label>Дней<input type="number" min={1} max={30} value={plan.duration_days ?? ""} disabled={!!(from && to)} onChange={(e) => patch({ duration_days: e.target.value ? Number(e.target.value) : undefined })} /></label>
              {errors.duration && <p className="home__error" role="alert">{errors.duration}</p>}
              <Adults value={plan.travelers?.adults ?? 0} min={0} allowNone onChange={(n) => patch({ travelers: n ? { adults: n, children_ages: plan.travelers?.children_ages ?? [] } : undefined })} />
              {plan.travelers && <label>Возраст детей через запятую<input inputMode="numeric" placeholder="нет детей" value={kidsText || plan.travelers.children_ages.join(", ")}
                onChange={(e) => { setKidsText(e.target.value); patch({ travelers: { adults: plan.travelers!.adults, children_ages: ages(e.target.value).filter((x) => !Number.isNaN(x)) } }); }} /></label>}
              {errors.travelers && <p className="home__error" role="alert">{errors.travelers}</p>}
              <label>Бюджет, ₽<input type="number" min={1} step={1000} placeholder="без ограничений" value={plan.budget ? plan.budget.amount_minor / 100 : ""}
                onChange={(e) => { const n = Math.round(Number(e.target.value)); patch({ budget: n > 0 ? { amount_minor: n * 100, currency: "RUB" } : undefined }); }} /></label>
              <div className="quiz__wishes" role="group" aria-label="Пожелания">
                {WISHES.map((o) => { const on = !!plan.wishes?.includes(o.id); return <button key={o.id} type="button" className={`chip ${on ? "chip--active" : ""}`} aria-pressed={on} onClick={() => patch({ wishes: on ? plan.wishes!.filter((x) => x !== o.id) : [...(plan.wishes ?? []), o.id] })}>{o.label}</button>; })}
              </div>
              <small className="muted">Распознано автоматически по правилам, без нейросети: проверьте значения. Что не указано — не придумываем.</small>
              <small className="muted">{[plan.dates && dateRange(from, to), plan.travelers && travelersLabel(plan.travelers), plan.budget && `до ${money({ amount: plan.budget.amount_minor / 100, currency: "RUB" })}`].filter(Boolean).join(" · ")}</small>
            </div>
          )}
        </div>
        <div className="quiz__foot">
          {i > 0 && <button type="button" className="btn btn--ghost quiz__back" onClick={() => setI(i - 1)} aria-label="Назад"><Icon name="back" size={22} /></button>}
          <button type="button" className="home__cta quiz__next" disabled={stepBlocked || (step === "review" && reviewBlocked)} onClick={next}>
            <span>{step === "review" ? "Найти путешествие" : "Далее"}</span><Icon name={step === "review" ? "search" : "arrow-right"} size={20} stroke={2} />
          </button>
        </div>
      </div>
    </div>,
    host,
  );
}

function Adults({ value, min, onChange, allowNone }: { value: number; min: number; onChange: (n: number) => void; allowNone?: boolean }) {
  return (
    <div className="home__row home__row--between"><span>Взрослых{allowNone && value === 0 ? " (не указано)" : ""}</span>
      <div className="home__stepper">
        <button type="button" aria-label="Меньше" disabled={value <= min} onClick={() => onChange(value - 1)}>−</button>
        <output aria-live="polite">{value}</output>
        <button type="button" aria-label="Больше" disabled={value >= 9} onClick={() => onChange(value + 1)}>+</button>
      </div>
    </div>
  );
}

function Card({ o, on, onPick, multi }: { o: Opt; on: boolean; onPick: () => void; multi?: boolean }) {
  return (
    <button type="button" className={`quiz__card ${on ? "is-on" : ""}`} role={multi ? "checkbox" : "radio"} aria-checked={on} onClick={onPick}>
      <span className="quiz__ic"><Icon name={o.icon} size={22} stroke={1.8} /></span>
      <b>{o.label}</b>
      {o.sub && <small>{o.sub}</small>}
      {on && <span className="quiz__tick"><Icon name="check" size={14} stroke={3} /></span>}
    </button>
  );
}
