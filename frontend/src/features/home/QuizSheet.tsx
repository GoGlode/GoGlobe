// Викторина перед поиском: по шагам уточняем даты, состав, бюджет и настроение поездки. Каждый шаг можно пропустить.
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { dateRange, money } from "../../data/format";
import type { SearchParamsUI } from "../../data/types";
import { Icon, type IconName } from "../../ui";

interface Opt { id: string; label: string; sub?: string; icon: IconName }
const WHEN: Opt[] = [
  { id: "soon", label: "Ближайший месяц", sub: "Скоро в путь", icon: "clock" },
  { id: "q", label: "Через 2–3 месяца", sub: "Время спланировать", icon: "calendar" },
  { id: "summer", label: "Летом", sub: "Июнь – август", icon: "sun" },
  { id: "winter", label: "Зимой", sub: "Декабрь – февраль", icon: "leaf" },
  { id: "custom", label: "Свои даты", sub: "Выберу сам", icon: "pencil" },
  { id: "any", label: "Пока не знаю", sub: "Подберите варианты", icon: "globe" },
];
const WHO: (Opt & { n: number })[] = [
  { id: "1", n: 1, label: "Один", sub: "1 человек", icon: "user" },
  { id: "2", n: 2, label: "Вдвоём", sub: "2 человека", icon: "heart" },
  { id: "4", n: 4, label: "Семья", sub: "3–4 человека", icon: "users" },
  { id: "6", n: 6, label: "Компания", sub: "5 и больше", icon: "users" },
];
const HOW_MUCH = [
  { id: "100", v: 100_000, label: "До 100 000 ₽", sub: "Экономно", icon: "wallet" as IconName },
  { id: "150", v: 150_000, label: "До 150 000 ₽", sub: "Комфортно", icon: "wallet" as IconName },
  { id: "250", v: 250_000, label: "До 250 000 ₽", sub: "Щедро", icon: "wallet" as IconName },
  { id: "inf", v: 0, label: "Без ограничений", sub: "Лучшее", icon: "star" as IconName },
];
const MOOD: Opt[] = [
  { id: "Море и пляж", label: "Море и пляж", icon: "waves" },
  { id: "Культура и история", label: "Культура и история", icon: "landmark" },
  { id: "Природа", label: "Природа", icon: "leaf" },
  { id: "Гастрономия", label: "Гастрономия", icon: "utensils" },
  { id: "Активный отдых", label: "Активный отдых", icon: "nav" },
  { id: "Спокойный отдых и спа", label: "Спа и релакс", icon: "spa" },
];
const STEPS = [
  { title: "Когда поедем?", hint: "Выберите время — или пропустите" },
  { title: "Кто едет?", hint: "Сколько вас будет" },
  { title: "Какой бюджет?", hint: "Максимум на всю поездку" },
  { title: "Чего хочется?", hint: "Можно выбрать несколько" },
];
const today = () => new Date().toISOString().slice(0, 10);

export default function QuizSheet({ query, params, onDone, onClose }: {
  query: string; params: SearchParamsUI; onDone: (query: string, params: SearchParamsUI) => void; onClose: () => void;
}) {
  const [step, setStep] = useState(0);
  const [when, setWhen] = useState<string | null>(null);
  const [from, setFrom] = useState(""); const [to, setTo] = useState("");
  const [who, setWho] = useState<string | null>(null);
  const [cash, setCash] = useState<string | null>(null);
  const [mood, setMood] = useState<string[]>([]);
  const timer = useRef<number>();
  useEffect(() => () => clearTimeout(timer.current), []);
  useEffect(() => {
    const on = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [onClose]);

  const last = step === STEPS.length - 1;
  const datesError = when === "custom" ? (!from || !to ? "Укажите обе даты" : from < today() ? "Дата начала уже прошла" : to < from ? "Обратно — раньше, чем туда" : null) : null;
  const next = () => (last ? finish() : setStep(step + 1));
  const pickAndGo = (set: () => void) => { set(); clearTimeout(timer.current); timer.current = window.setTimeout(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 260); };

  const finish = () => {
    const p: SearchParamsUI = { ...params };
    if (when === "custom" && !datesError) p.dates = dateRange(from, to);
    else if (when === "any") p.dates = undefined;
    else if (when) p.dates = WHEN.find((o) => o.id === when)!.label.toLowerCase().replace(/^./, (c) => c.toUpperCase());
    if (who) { const w = WHO.find((o) => o.id === who)!; p.travelers = w.sub; }
    if (cash) { const c = HOW_MUCH.find((o) => o.id === cash)!; p.budget = c.v ? `до ${money({ amount: c.v, currency: "RUB" })}` : undefined; }
    const q = mood.length ? `${query.trim()}. Хочется: ${mood.map((m) => m.toLowerCase()).join(", ")}` : query;
    onDone(q, p);
  };

  const host = document.querySelector(".app") ?? document.body;
  return createPortal(
    <div className="quiz" role="dialog" aria-modal="true" aria-label="Уточните поездку">
      <button type="button" className="quiz__scrim" aria-label="Закрыть" onClick={onClose} />
      <div className="quiz__sheet">
        <div className="quiz__top">
          <div className="quiz__bars" aria-hidden="true">{STEPS.map((_, i) => <i key={i} className={i <= step ? "is-on" : ""} />)}</div>
          <button type="button" className="quiz__skip" onClick={() => onDone(query, params)}>Пропустить</button>
        </div>
        <div className="quiz__body" key={step}>
          <small>Шаг {step + 1} из {STEPS.length}</small>
          <h2>{STEPS[step].title}</h2>
          <p className="muted">{STEPS[step].hint}</p>
          <div className="quiz__grid" role={step === 3 ? "group" : "radiogroup"}>
            {step === 0 && WHEN.map((o) => <Card key={o.id} o={o} on={when === o.id} onPick={() => (o.id === "custom" ? setWhen("custom") : pickAndGo(() => setWhen(o.id)))} />)}
            {step === 1 && WHO.map((o) => <Card key={o.id} o={o} on={who === o.id} onPick={() => pickAndGo(() => setWho(o.id))} />)}
            {step === 2 && HOW_MUCH.map((o) => <Card key={o.id} o={o} on={cash === o.id} onPick={() => pickAndGo(() => setCash(o.id))} />)}
            {step === 3 && MOOD.map((o) => <Card key={o.id} o={o} multi on={mood.includes(o.id)} onPick={() => setMood(mood.includes(o.id) ? mood.filter((m) => m !== o.id) : [...mood, o.id])} />)}
          </div>
          {step === 0 && when === "custom" && (
            <div className="quiz__dates fade-up">
              <label>Туда<input type="date" min={today()} value={from} onChange={(e) => setFrom(e.target.value)} /></label>
              <label>Обратно<input type="date" min={from || today()} value={to} onChange={(e) => setTo(e.target.value)} /></label>
              {datesError && from && to && <p className="home__error" role="alert">{datesError}</p>}
            </div>
          )}
        </div>
        <div className="quiz__foot">
          {step > 0 && <button type="button" className="btn btn--ghost quiz__back" onClick={() => setStep(step - 1)} aria-label="Назад"><Icon name="back" size={22} /></button>}
          <button type="button" className="home__cta quiz__next" disabled={!!datesError} onClick={next}>
            <span>{last ? "Найти путешествие" : "Далее"}</span><Icon name={last ? "search" : "arrow-right"} size={20} stroke={2} />
          </button>
        </div>
      </div>
    </div>,
    host,
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
