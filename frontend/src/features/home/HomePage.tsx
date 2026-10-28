// Главный экран: «Куда поедем?», запрос, параметры, популярные направления. Владелец: Frontend №1.
import { useLayoutEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { money } from "../../data/format";
import { uiFromPlan } from "../../data/plan";
import { DESTINATIONS, getTrip } from "../../data/trips";
import { useFavorites } from "../../state/FavoritesContext";
import { useSearch } from "../../state/SearchContext";
import { Icon, MaskIcon, Photo } from "../../ui";
import QuizSheet from "./QuizSheet";
import "./home.css";

const BUDGETS = [100_000, 150_000, 250_000];
const MAX_TRAVELERS = 9; // взрослых (контракт v0.3: 1–9)
const today = () => new Date().toISOString().slice(0, 10);
const rub = (amount: number) => money({ amount, currency: "RUB" });

// Карточки направлений — отрисованные картинки из пакета дизайнера; у остальных остаётся обложка поездки
const CARD_IMG: Record<string, string> = {
  greece: "/assets/images/dest-greece.jpg", thailand: "/assets/images/dest-thailand.jpg", italy: "/assets/images/dest-italy.jpg",
  japan: "/assets/images/dest-japan.jpg", bali: "/assets/images/dest-bali.jpg",
};

// Короткая справка на карточке: когда лучше ехать и на сколько
const FACTS: Record<string, { season: string; stay: string }> = {
  greece: { season: "май – октябрь", stay: "7–10 дней" }, thailand: { season: "ноябрь – апрель", stay: "10–14 дней" },
  italy: { season: "апрель – октябрь", stay: "7–10 дней" }, japan: { season: "март – май", stay: "8–12 дней" },
  bali: { season: "апрель – октябрь", stay: "10–14 дней" }, turkey: { season: "май – октябрь", stay: "7–10 дней" },
  maldives: { season: "ноябрь – апрель", stay: "5–7 дней" }, georgia: { season: "май – октябрь", stay: "5–7 дней" },
};

type Panel = "dates" | "travelers" | "budget" | null;

export default function HomePage() {
  const { query, setQuery, params, setParams, run, phase, busy, live, configError, submitError, clearSubmitError } = useSearch();
  const { has, toggle: toggleFav } = useFavorites();
  const nav = useNavigate();
  const input = useRef<HTMLTextAreaElement>(null);
  const [panel, setPanel] = useState<Panel>(null);
  const [quiz, setQuiz] = useState(false); // викторина-уточнение перед поиском
  const [nudge, setNudge] = useState(false); // подсветка пустого поля при нажатии на «Создать»
  // Черновики открытой панели — применяются кнопкой «Готово»
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [people, setPeople] = useState(2);
  const [budget, setBudget] = useState("");

  const datesError = from && from < today() ? "Дата начала уже прошла" : from && to && to < from ? "Обратно — раньше, чем туда" : null;
  const budgetValue = Number(budget.replace(/\s/g, ""));
  const togglePanel = (p: Exclude<Panel, null>) => setPanel(panel === p ? null : p);
  const plan = params.plan ?? {};
  const apply = (patch: NonNullable<typeof params.plan>) => { setParams(uiFromPlan({ ...plan, ...patch }, params)); setPanel(null); };

  // Поле растёт вместе с текстом, пока запрос короткий — выглядит как одна строка поиска
  useLayoutEffect(() => {
    const el = input.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 112)}px`;
  }, [query]);

  const submit = () => {
    if (phase === "loading" || busy) return;
    clearSubmitError();
    if (!query.trim()) {
      input.current?.focus({ preventScroll: true });
      setNudge(true);
      return;
    }
    setPanel(null);
    setQuiz(true);
  };
  const go = async (q?: string, p?: typeof params) => {
    setQuiz(false);
    if (!live) { void (q !== undefined && p ? run({ query: q, params: p }) : run()); nav("/results"); return; } // ДЕМО на макетах
    const id = await (q !== undefined && p ? run({ query: q, params: p }) : run());
    if (id) nav(`/search/${id}`); // иначе остаёмся на Home и показываем ошибку
  };
  const pick = (q: string) => {
    setQuery(q);
    input.current?.focus({ preventScroll: true });
    input.current?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  return (
    <div className="home">
      <div className="home__bg" aria-hidden="true">
        <img src="/assets/images/hero-santorini.jpg" alt="" />
        <i className="home__shade" />
        <i className="home__frost" />
      </div>

      <section className="home__hero" aria-labelledby="home-title">
        <header className="home__top">
          <div className="home__brand" role="img" aria-label="GoGlobe — Plan. Explore. Travel.">
            <b>GoGlobe</b>
            <span>Plan. Explore. Travel.</span>
          </div>
          <nav className="home__round-nav" aria-label="Разделы">
            <Link to="/profile" className="home__round" aria-label="Профиль"><Icon name="user" size={21} stroke={1.8} /></Link>
          </nav>
        </header>
        <div className="home__intro">
          <h1 id="home-title">Куда<br />поедем?</h1>
          <p>Расскажите о своей идеальной<br />поездке — и мы создадим<br />для вас маршрут</p>
        </div>
      </section>

      <form className="home__form" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <label className={`home__input ${nudge ? "is-nudge" : ""}`} onAnimationEnd={() => setNudge(false)}>
          <MaskIcon src="search-sparkle" size={24} className="home__search-ic" />
          <span className="visually-hidden">Опишите путешествие</span>
          <textarea ref={input} rows={1} maxLength={2000} value={query} placeholder="Например: Италия на 7 дней, море и культура"
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit(); } }} />
        </label>

        <div className="home__opts" role="group" aria-label="Параметры путешествия">
          <button type="button" className={`home__opt ${params.dates ? "is-set" : ""}`} aria-expanded={panel === "dates"} onClick={() => togglePanel("dates")}>
            <Icon name="calendar" size={24} stroke={1.7} /><span><b>Даты</b><small>{params.dates ?? "Любые"}</small></span></button>
          <button type="button" className={`home__opt ${params.travelers ? "is-set" : ""}`} aria-expanded={panel === "travelers"} onClick={() => togglePanel("travelers")}>
            <Icon name="users" size={24} stroke={1.7} /><span><b>Путешественники</b><small>{params.travelers ?? "1–2"}</small></span></button>
          <button type="button" className={`home__opt ${params.budget ? "is-set" : ""}`} aria-expanded={panel === "budget"} onClick={() => togglePanel("budget")}>
            <Icon name="wallet" size={24} stroke={1.7} /><span><b>Бюджет</b><small>{params.budget ?? "Любой"}</small></span></button>
        </div>

        {panel === "dates" && (
          <div className="home__panel-form card fade-up">
            <div className="home__row">
              <label>Туда<input type="date" min={today()} value={from} onChange={(e) => setFrom(e.target.value)} /></label>
              <label>Обратно<input type="date" min={from || today()} value={to} onChange={(e) => setTo(e.target.value)} /></label>
            </div>
            {datesError && <p className="home__error" role="alert">{datesError}</p>}
            <PanelActions disabled={!from || !to || !!datesError} onReset={() => apply({ dates: undefined, duration_days: undefined })}
              onApply={() => apply({ dates: { start_date: from, end_date: to }, duration_days: Math.min(30, Math.round((Date.parse(to) - Date.parse(from)) / 864e5) + 1) })} />
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
              onApply={() => apply({ travelers: { adults: people, children_ages: plan.travelers?.children_ages ?? [] } })} />
          </div>
        )}
        {panel === "budget" && (
          <div className="home__panel-form card fade-up">
            <label>Максимум на всю поездку, ₽
              <input type="number" inputMode="numeric" min={1} step={1000} placeholder="Например, 150000" value={budget}
                onChange={(e) => setBudget(e.target.value)} />
            </label>
            <div className="home__row">
              {BUDGETS.map((b) => <button type="button" key={b} className="home__quick" onClick={() => setBudget(String(b))}>до {rub(b)}</button>)}
            </div>
            <PanelActions disabled={!(budgetValue > 0)} onReset={() => apply({ budget: undefined })}
              onApply={() => apply({ budget: { amount_minor: Math.round(budgetValue) * 100, currency: "RUB" } })} />
          </div>
        )}

        {configError && <p className="home__error" role="alert">{configError}</p>}
        {submitError && !configError && <p className="home__error" role="alert">{submitMessage(submitError)}</p>}
        {!live && !configError && <p className="home__demo">Демо-режим: backend не подключён, результаты — условные примеры.</p>}
        <button className="home__cta" disabled={phase === "loading" || busy || !!configError} aria-busy={busy}>
          <MaskIcon src="search-sparkle" size={28} />
          <span>{busy ? "Отправляем…" : "Создать путешествие"}</span>
          <Icon name="arrow-right" size={22} stroke={2} />
        </button>
      </form>

      <section className="home__popular" aria-labelledby="popular-title">
        <h2 id="popular-title">Популярные направления</h2>
        <ul className="home__dests">
          {DESTINATIONS.map((d) => {
            const fav = has(d.id);
            const f = FACTS[d.id];
            return (
              <li key={d.id} className="dest">
                <button type="button" className="dest__main" aria-label={`${d.name}: подставить пример запроса`} onClick={() => pick(d.query)}>
                  <span className="dest__img"><Photo src={CARD_IMG[d.id] ?? d.img} alt="" /></span>
                  <span className="dest__txt">
                    <b>{d.name}</b>
                    <small>{d.sub}</small>
                    {f && (
                      <span className="dest__facts">
                        <span><Icon name="sun" size={15} stroke={1.8} />{f.season}</span>
                        <span><Icon name="clock" size={15} stroke={1.8} />{f.stay}</span>
                      </span>
                    )}
                  </span>
                </button>
                {getTrip(d.id) && (
                  <button type="button" className={`dest__heart ${fav ? "is-on" : ""}`} aria-pressed={fav}
                    aria-label={fav ? `Убрать «${d.name}» из избранного` : `Добавить «${d.name}» в избранное`} onClick={() => toggleFav(d.id)}>
                    <Icon name="heart" size={18} stroke={2} filled={fav} />
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      </section>

      {quiz && <QuizSheet query={query} params={params} onClose={() => setQuiz(false)} onDone={go} />}
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

/** Понятный текст по коду ошибки: 401/403 сессия, 409 конфликт, 422 данные, 429 лимит, 5xx сервер, 0 сеть. */
function submitMessage(e: { status: number; message: string }): string {
  if (e.status === 0) return "Нет связи с сервером. Проверьте интернет — запрос не потерян, можно повторить.";
  if (e.status === 401 || e.status === 403) return "Сессия не начата или истекла. Обновите страницу и повторите.";
  if (e.status === 409) return "Похожий запрос уже обрабатывается. Подождите секунду и повторите.";
  if (e.status === 422 || e.status === 400) return `Сервер не принял параметры: ${e.message}`;
  if (e.status === 429) return "Слишком много запросов. Подождите минуту и повторите.";
  return "Сервер временно недоступен. Повторите чуть позже.";
}
