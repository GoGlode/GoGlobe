// Главный экран: «Куда поедем?», запрос, параметры, популярные направления. Владелец: Frontend №1.
import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { dateRange, money, plural } from "../../data/format";
import { DESTINATIONS } from "../../data/trips";
import { useSearch } from "../../state/SearchContext";
import { Icon, Logo, Photo } from "../../ui";
import "./home.css";

const EXAMPLE = "Хочу на 5 дней в Турцию в ноябре, на двоих, бюджет до 120 000 рублей. Нужен хороший отель рядом с морем и прямой перелёт";
const BUDGETS = [100_000, 150_000, 250_000];
const MAX_TRAVELERS = 9;
const today = () => new Date().toISOString().slice(0, 10);
const rub = (amount: number) => money({ amount, currency: "RUB" });

type Panel = "dates" | "travelers" | "budget" | null;

export default function HomePage() {
  const { query, setQuery, params, setParams, run, phase } = useSearch();
  const nav = useNavigate();
  const input = useRef<HTMLTextAreaElement>(null);
  const [panel, setPanel] = useState<Panel>(null);
  // Черновики открытой панели — применяются кнопкой «Готово»
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [people, setPeople] = useState(2);
  const [budget, setBudget] = useState("");

  const datesError = from && from < today() ? "Дата начала уже прошла" : from && to && to < from ? "Обратно — раньше, чем туда" : null;
  const budgetValue = Number(budget.replace(/\s/g, ""));
  const toggle = (p: Exclude<Panel, null>) => setPanel(panel === p ? null : p);
  const apply = (patch: Partial<typeof params>) => { setParams({ ...params, ...patch }); setPanel(null); };

  const submit = () => {
    if (!query.trim() || phase === "loading") return;
    void run();
    nav("/results");
  };
  const pick = (q: string) => {
    setQuery(q);
    input.current?.focus({ preventScroll: true });
    input.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  return (
    <div className="home">
      <header className="home__top">
        <Logo className="home__logo" />
      </header>

      <section className="home__hero" aria-labelledby="home-title">
        <div className="home__photo"><Photo src="/assets/photos/hero.jpg" alt="Голубые купола Ии на Санторини" /></div>
        <div className="home__panel glass">
          <h1 id="home-title">Куда поедем?</h1>
          <p className="muted">Опишите пожелания своими словами — AI подберёт путешествие.</p>
        </div>
      </section>

      <form className="home__form" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <label className="home__input glass">
          <span className="home__spark"><Icon name="sparkle" size={20} /></span>
          <span className="visually-hidden">Опишите путешествие</span>
          <textarea ref={input} rows={3} maxLength={2000} value={query} placeholder="Хочу неделю у моря с красивыми видами…"
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); submit(); } }} />
        </label>

        <div className="scroll-x home__chips" role="group" aria-label="Параметры путешествия">
          <button type="button" className={`chip ${params.dates ? "is-set" : ""}`} aria-expanded={panel === "dates"} onClick={() => toggle("dates")}>
            <Icon name="calendar" size={16} />{params.dates ?? "Даты"}</button>
          <button type="button" className={`chip ${params.travelers ? "is-set" : ""}`} aria-expanded={panel === "travelers"} onClick={() => toggle("travelers")}>
            <Icon name="users" size={16} />{params.travelers ?? "Путешественники"}</button>
          <button type="button" className={`chip ${params.budget ? "is-set" : ""}`} aria-expanded={panel === "budget"} onClick={() => toggle("budget")}>
            <Icon name="tag" size={16} />{params.budget ?? "Бюджет"}</button>
        </div>

        {panel === "dates" && (
          <div className="home__panel-form card fade-up">
            <div className="home__row">
              <label>Туда<input type="date" min={today()} value={from} onChange={(e) => setFrom(e.target.value)} /></label>
              <label>Обратно<input type="date" min={from || today()} value={to} onChange={(e) => setTo(e.target.value)} /></label>
            </div>
            {datesError && <p className="home__error" role="alert">{datesError}</p>}
            <PanelActions disabled={!from || !to || !!datesError} onReset={() => apply({ dates: undefined })}
              onApply={() => apply({ dates: dateRange(from, to) })} />
          </div>
        )}
        {panel === "travelers" && (
          <div className="home__panel-form card fade-up">
            <div className="home__row home__row--between">
              <span>Сколько путешественников?</span>
              <div className="home__stepper">
                <button type="button" aria-label="Меньше" disabled={people <= 1} onClick={() => setPeople(people - 1)}>−</button>
                <output aria-live="polite">{people}</output>
                <button type="button" aria-label="Больше" disabled={people >= MAX_TRAVELERS} onClick={() => setPeople(people + 1)}>+</button>
              </div>
            </div>
            <PanelActions onReset={() => apply({ travelers: undefined })}
              onApply={() => apply({ travelers: `${people} ${plural(people, "человек", "человека", "человек")}` })} />
          </div>
        )}
        {panel === "budget" && (
          <div className="home__panel-form card fade-up">
            <label>Максимум на всю поездку, ₽
              <input type="number" inputMode="numeric" min={1} step={1000} placeholder="Например, 150000" value={budget}
                onChange={(e) => setBudget(e.target.value)} />
            </label>
            <div className="home__row">
              {BUDGETS.map((b) => <button type="button" key={b} className="chip" onClick={() => setBudget(String(b))}>до {rub(b)}</button>)}
            </div>
            <PanelActions disabled={!(budgetValue > 0)} onReset={() => apply({ budget: undefined })}
              onApply={() => apply({ budget: `до ${rub(budgetValue)}` })} />
          </div>
        )}

        <button className="btn" disabled={!query.trim() || phase === "loading"}>Создать путешествие</button>
        <div className="home__hint">
          <span className="muted">Даты, состав и бюджет можно не указывать</span>
          <button type="button" className="home__example" onClick={() => pick(EXAMPLE)}>Пример</button>
        </div>
        <p className="home__demo">Демонстрационный режим — тестовые данные</p>
      </form>

      <section className="home__popular" aria-labelledby="popular-title">
        <h2 id="popular-title" className="h-title">Популярные направления</h2>
        <ul className="scroll-x home__dests">
          {DESTINATIONS.map((d) => (
            <li key={d.id}>
              <button type="button" className="home__dest" aria-label={`${d.name}: подставить пример запроса`} onClick={() => pick(d.query)}>
                <Photo src={d.img} alt="" />
                <span className="home__dest-label glass"><b>{d.name}</b><small>{d.sub}</small></span>
              </button>
            </li>
          ))}
        </ul>
        <Link to="/credits" className="home__credits">Фото: Wikimedia Commons — авторы и лицензии</Link>
      </section>
    </div>
  );
}

function PanelActions({ onApply, onReset, disabled }: { onApply: () => void; onReset: () => void; disabled?: boolean }) {
  return (
    <div className="home__actions">
      <button type="button" className="btn btn--sm btn--ghost" onClick={onReset}>Сбросить</button>
      <button type="button" className="btn btn--sm" disabled={disabled} onClick={onApply}>Готово</button>
    </div>
  );
}
