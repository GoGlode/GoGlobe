// Экран «Перелёты»: форма поиска (туда-обратно / в одну сторону / сложный маршрут), сортировка,
// фильтры, карточки рейсов. Открывается из поездки (вкладка) или отдельно (/flights).
// Данные — демо-слой data/flights.ts (в API-контракте v0 поиска рейсов нет).
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AIRPORTS, CABINS, TRIP_AIRPORT, airportLabel, durationLabel, findAirport, searchFlights,
  type CabinClass, type FlightMode, type FlightOption, type FlightQuery, type FlightResult,
} from "../../data/flights";
import { money, plural } from "../../data/format";
import { MY_TRIPS } from "../../data/trips";
import type { Trip } from "../../data/types";
import { CityInput, Icon, PageHeader, type CityOption } from "../../ui";
import TripTabs from "../trip/TripTabs";
import "./flights.css";

const MODES: { id: FlightMode; label: string }[] = [
  { id: "round", label: "Туда и обратно" }, { id: "oneway", label: "В одну сторону" }, { id: "multi", label: "Сложный маршрут" },
];
const SORTS = [
  { id: "best", label: "Рекомендуемые" }, { id: "cheap", label: "Дешевле" }, { id: "fast", label: "Быстрее" }, { id: "stops", label: "Меньше пересадок" },
] as const;
type Sort = (typeof SORTS)[number]["id"];
const MAX_LEGS = 4, MAX_ADULTS = 9;
const CITY_OPTIONS: CityOption[] = AIRPORTS.map((a) => ({ key: a.code, label: airportLabel(a), city: a.city, code: a.code }));
const CHOSEN_KEY = "goglobe.flights.chosen.v1";

interface LegForm { from: string; to: string; date: string }
const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
const dayLabel = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" });

function loadChosen(tripId?: string): Record<string, string> {
  if (!tripId) return {};
  try { return JSON.parse(localStorage.getItem(CHOSEN_KEY) ?? "{}")[tripId] ?? {}; } catch { return {}; }
}
function saveChosen(tripId: string, value: Record<string, string>) {
  try {
    const all = JSON.parse(localStorage.getItem(CHOSEN_KEY) ?? "{}");
    localStorage.setItem(CHOSEN_KEY, JSON.stringify({ ...all, [tripId]: value }));
  } catch { /* хранилище недоступно — выбор живёт до перезагрузки */ }
}

/** Начальные значения из поездки: направление, даты (если ещё не прошли), число путешественников. */
function initialForm(trip?: Trip) {
  const to = trip && TRIP_AIRPORT[trip.id] ? airportLabel(AIRPORTS.find((a) => a.code === TRIP_AIRPORT[trip.id])!) : "";
  const mine = trip && MY_TRIPS.find((m) => m.tripId === trip.id && m.start >= today());
  const [start, end] = mine ? [mine.start, mine.end] : trip && trip.dateRange[0] >= today() ? trip.dateRange : ["", ""];
  return {
    legs: [{ from: trip ? "Москва (SVO)" : "", to, date: start }, { from: to, to: trip ? "Москва (SVO)" : "", date: end }],
    adults: Math.min(Math.max(trip?.travelers ?? 1, 1), MAX_ADULTS),
  };
}

export default function FlightsScreen({ trip }: { trip?: Trip }) {
  const nav = useNavigate();
  const init = useMemo(() => initialForm(trip), [trip]);
  const [mode, setMode] = useState<FlightMode>("round");
  const [legs, setLegs] = useState<LegForm[]>(init.legs);
  const [adults, setAdults] = useState(init.adults);
  const [cabin, setCabin] = useState<CabinClass>("economy");
  const [paxOpen, setPaxOpen] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [results, setResults] = useState<FlightResult[]>([]);
  const [lastQuery, setLastQuery] = useState<FlightQuery | null>(null);
  const [sort, setSort] = useState<Sort>("best");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [onlyDirect, setOnlyDirect] = useState(false);
  const [withBaggage, setWithBaggage] = useState(false);
  const [chosen, setChosen] = useState<Record<string, string>>(() => loadChosen(trip?.id));
  const formRef = useRef<HTMLFormElement>(null);

  // В режиме «туда-обратно» обратный рейс зеркалит маршрут; дата — своя
  const activeLegs: LegForm[] = mode === "oneway" ? [legs[0]]
    : mode === "round" ? [legs[0], { from: legs[0].to, to: legs[0].from, date: legs[1]?.date ?? "" }] : legs;

  const setLeg = (i: number, patch: Partial<LegForm>) => setLegs((ls) => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)));
  const swap = (i: number) => setLeg(i, { from: legs[i].to, to: legs[i].from });
  const changeMode = (m: FlightMode) => {
    setMode(m); setErrors([]);
    if (m === "multi" && legs.length < 2) setLegs((ls) => [...ls, { from: ls[0].to, to: "", date: "" }]);
    if (m === "multi" && legs.length >= 2 && !legs[1].from) setLeg(1, { from: legs[0].to });
  };

  function validate(): FlightQuery | null {
    const errs: string[] = [];
    const t = today();
    const parsed = activeLegs.map((l, i) => {
      const n = mode === "multi" ? ` (перелёт ${i + 1})` : "";
      const from = findAirport(l.from), to = findAirport(l.to);
      const mirror = mode === "round" && i === 1; // обратный рейс повторяет маршрут — не дублируем ошибки
      if (!from && !mirror) errs.push(`Укажите город вылета из списка${n}`);
      if (!to && !mirror) errs.push(`Укажите город назначения из списка${n}`);
      if (from && to && from.code === to.code && !mirror) errs.push(`Города вылета и назначения совпадают${n}`);
      if (!l.date) errs.push(mode === "round" && i === 1 ? "Укажите дату возвращения" : `Укажите дату вылета${n}`);
      else if (l.date < t) errs.push(`Дата уже прошла${n}`);
      return { from: from?.code ?? "", to: to?.code ?? "", date: l.date };
    });
    for (let i = 1; i < parsed.length; i++) {
      if (parsed[i].date && parsed[i - 1].date && parsed[i].date < parsed[i - 1].date)
        errs.push(mode === "round" ? "Дата возвращения раньше даты вылета" : `Перелёт ${i + 1} раньше предыдущего`);
    }
    setErrors(errs);
    return errs.length ? null : { legs: parsed, adults, cabin };
  }

  async function run(q: FlightQuery) {
    setStatus("loading"); setLastQuery(q);
    try { setResults(await searchFlights(q)); setStatus("done"); } catch { setStatus("error"); }
  }
  const submit = () => { const q = validate(); if (q) void run(q); };

  // Открыли из поездки и всё известно — ищем сразу, не заставляя вводить заново
  useEffect(() => {
    if (trip && init.legs[0].date && init.legs[1].date) submit();
  }, []); // только при открытии

  const choose = (legKey: string, id: string) => {
    const next = { ...chosen, [legKey]: chosen[legKey] === id ? "" : id };
    setChosen(next);
    if (trip) saveChosen(trip.id, next);
  };

  const sortFn = (a: FlightOption, b: FlightOption) =>
    sort === "cheap" ? a.price.amount - b.price.amount
      : sort === "fast" ? a.minutes - b.minutes
        : sort === "stops" ? a.stops - b.stops || a.minutes - b.minutes
          : a.stops - b.stops || a.price.amount - b.price.amount; // рекомендуемые: сначала прямые, затем дешевле
  const visible = (opts: FlightOption[]) => opts.filter((o) => (!onlyDirect || o.stops === 0) && (!withBaggage || o.baggage)).sort(sortFn);
  const activeFilters = Number(onlyDirect) + Number(withBaggage);
  const back = () => (trip ? nav(`/trip/${trip.id}`) : (window.history.state as { idx?: number } | null)?.idx ? nav(-1) : nav("/"));
  const legTitle = (i: number) => (mode === "round" ? (i === 0 ? "Туда" : "Обратно") : `Перелёт ${i + 1}`);

  return (
    <div className="fl-screen">
      <PageHeader title="Перелёты" onBack={back}
        right={<button type="button" className={`circle-btn fl-filter-btn ${activeFilters ? "is-on" : ""}`} aria-label="Фильтры" aria-expanded={filtersOpen}
          onClick={() => setFiltersOpen(!filtersOpen)}><Icon name="filter" />{activeFilters > 0 && <span className="fl-badge">{activeFilters}</span>}</button>} />
      {trip && <TripTabs id={trip.id} current="flights" />}
      <div className="page fl">
        {filtersOpen && (
          <div className="fl-filters card fade-up" role="group" aria-label="Фильтры">
            <button type="button" className={`chip ${onlyDirect ? "chip--active" : ""}`} aria-pressed={onlyDirect} onClick={() => setOnlyDirect(!onlyDirect)}>Только прямые</button>
            <button type="button" className={`chip ${withBaggage ? "chip--active" : ""}`} aria-pressed={withBaggage} onClick={() => setWithBaggage(!withBaggage)}>С багажом</button>
          </div>
        )}
        {!trip && <p className="fl-lead muted">Подбери удобный маршрут для своего путешествия</p>}

        <div className="fl-modes" role="tablist" aria-label="Тип маршрута">
          {MODES.map((m) => <button key={m.id} type="button" role="tab" aria-selected={mode === m.id} className={mode === m.id ? "on" : ""} onClick={() => changeMode(m.id)}>{m.label}</button>)}
        </div>

        <form ref={formRef} className="fl-form" noValidate onSubmit={(e) => { e.preventDefault(); submit(); }}>
          {(mode === "multi" ? legs : [legs[0]]).map((l, i) => (
            <div key={i} className="fl-leg">
              {mode === "multi" && (
                <div className="fl-leg__head"><b>Перелёт {i + 1}</b>
                  {legs.length > 2 && <button type="button" className="fl-leg__rm" aria-label={`Удалить перелёт ${i + 1}`} onClick={() => setLegs(legs.filter((_, j) => j !== i))}><Icon name="x" size={16} /></button>}
                </div>
              )}
              <div className="fl-grid fl-grid--route">
                <label className="fl-field"><Icon name="pin" size={22} /><span className="visually-hidden">Откуда</span>
                  <CityInput placeholder="Откуда" options={CITY_OPTIONS} value={l.from} onChange={(v) => setLeg(i, { from: v })} /></label>
                <button type="button" className="fl-swap" aria-label="Поменять города местами" onClick={() => swap(i)}><Icon name="swap" size={16} stroke={2.2} /></button>
                <label className="fl-field"><Icon name="pin" size={22} /><span className="visually-hidden">Куда</span>
                  <CityInput placeholder="Куда" options={CITY_OPTIONS} value={l.to} onChange={(v) => setLeg(i, { to: v })} /></label>
              </div>
              {mode === "multi" && (
                <label className="fl-field fl-field--wide"><Icon name="calendar" size={22} /><span className="visually-hidden">Дата вылета</span>
                  <input type="date" min={today()} value={l.date} onChange={(e) => setLeg(i, { date: e.target.value })} /></label>
              )}
            </div>
          ))}
          {mode === "multi" && legs.length < MAX_LEGS && (
            <button type="button" className="fl-add" onClick={() => setLegs([...legs, { from: legs[legs.length - 1].to, to: "", date: "" }])}><Icon name="plus" size={18} />Добавить перелёт</button>
          )}
          {mode !== "multi" && (
            <div className={`fl-grid ${mode === "round" ? "fl-grid--dates" : ""}`}>
              <label className="fl-field"><Icon name="calendar" size={22} /><span className="visually-hidden">Дата вылета</span>
                <input type="date" min={today()} value={legs[0].date} onChange={(e) => setLeg(0, { date: e.target.value })} /></label>
              {mode === "round" && <>
                <span className="fl-dash" aria-hidden="true">—</span>
                <label className="fl-field"><Icon name="calendar" size={22} /><span className="visually-hidden">Дата возвращения</span>
                  <input type="date" min={legs[0].date || today()} value={legs[1]?.date ?? ""} onChange={(e) => setLeg(1, { date: e.target.value })} /></label>
              </>}
            </div>
          )}
          <div className="fl-grid">
            <button type="button" className="fl-field fl-field--btn" aria-expanded={paxOpen} onClick={() => setPaxOpen(!paxOpen)}>
              <Icon name="users" size={22} /><span><small>Пассажиры</small>{adults} {plural(adults, "взрослый", "взрослых", "взрослых")}</span>
            </button>
            <label className="fl-field fl-field--btn"><Icon name="user" size={22} />
              <span><small>Класс</small>
                <select value={cabin} onChange={(e) => setCabin(e.target.value as CabinClass)}>{CABINS.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}</select>
              </span></label>
          </div>
          {paxOpen && (
            <div className="fl-pax card fade-up">
              <span>Взрослые</span>
              <div className="fl-stepper">
                <button type="button" aria-label="Меньше" disabled={adults <= 1} onClick={() => setAdults(adults - 1)}>−</button>
                <output aria-live="polite">{adults}</output>
                <button type="button" aria-label="Больше" disabled={adults >= MAX_ADULTS} onClick={() => setAdults(adults + 1)}>+</button>
              </div>
            </div>
          )}
          {errors.length > 0 && <ul className="fl-errors" role="alert">{errors.map((e) => <li key={e}>{e}</li>)}</ul>}
          <button className="btn fl-submit" disabled={status === "loading"}><Icon name="search" size={22} stroke={2.2} />Найти рейсы<Icon name="arrow-right" size={20} /></button>
        </form>

        {status === "loading" && <div className="fl-results" aria-busy="true"><div className="fl-skel" /><div className="fl-skel" /></div>}
        {status === "error" && (
          <div className="fl-state card"><b>Не удалось загрузить рейсы</b><p className="muted">Проверьте соединение и попробуйте ещё раз.</p>
            {lastQuery && <button type="button" className="btn btn--sm" onClick={() => void run(lastQuery)}>Повторить</button>}</div>
        )}
        {status === "done" && (
          <div className="fl-results">
            <div className="scroll-x fl-sorts" role="group" aria-label="Сортировка">
              {SORTS.map((s) => <button key={s.id} type="button" className={`chip ${sort === s.id ? "chip--active" : ""}`} aria-pressed={sort === s.id} onClick={() => setSort(s.id)}>{s.label}</button>)}
            </div>
            <p className="fl-demo">Демо-данные: рейсы, время и цены — примеры, не реальные билеты</p>
            {results.map((r, i) => {
              const list = visible(r.options), legKey = `${i}:${r.leg.from}-${r.leg.to}`;
              const from = AIRPORTS.find((a) => a.code === r.leg.from)!, to = AIRPORTS.find((a) => a.code === r.leg.to)!;
              return (
                <section key={legKey} className="fl-leg-res" aria-label={legTitle(i)}>
                  {results.length > 1 && <h2 className="fl-leg-res__title">{legTitle(i)} · {from.city} → {to.city}<small>{dayLabel(r.leg.date)}</small></h2>}
                  {list.length === 0 ? (
                    <div className="fl-state card">
                      <b>Рейсы не найдены</b>
                      <p className="muted">{r.options.length ? "Попробуйте снять фильтры." : "В демо-данных есть рейсы из Москвы и Санкт-Петербурга в Афины, Стамбул, Анталью, Рим, Бангкок, Пхукет, Токио, Бали, Мале и Тбилиси (и обратно)."}</p>
                      <button type="button" className="btn btn--sm btn--ghost" onClick={() => (r.options.length ? (setOnlyDirect(false), setWithBaggage(false)) : formRef.current?.scrollIntoView({ behavior: "smooth" }))}>
                        {r.options.length ? "Снять фильтры" : "Изменить параметры"}</button>
                    </div>
                  ) : list.map((o) => <FlightCard key={o.id} o={o} chosen={chosen[legKey] === o.id} onChoose={() => choose(legKey, o.id)} />)}
                </section>
              );
            })}
            {trip && Object.values(chosen).some(Boolean) && <p className="fl-note muted">Выбранные рейсы отмечены в поездке. Это не бронирование и не покупка билета.</p>}
          </div>
        )}
      </div>
    </div>
  );
}

function FlightCard({ o, chosen, onChoose }: { o: FlightOption; chosen: boolean; onChoose: () => void }) {
  const [open, setOpen] = useState(false);
  const stops = o.stops === 0 ? "Прямой" : `${o.stops} ${plural(o.stops, "пересадка", "пересадки", "пересадок")}${o.via ? ` (${o.via.code})` : ""}`;
  const amen = [
    { icon: "bag" as const, title: "Ручная кладь", v: o.carryOn ?? "не включена" },
    { icon: "suitcase" as const, title: "Багаж", v: o.baggage ?? "не включён" },
    { icon: "meal" as const, title: "Питание", v: o.meal ?? "не включено" },
  ];
  return (
    <article className={`fcard ${chosen ? "is-chosen" : ""}`}>
      <button type="button" className="fcard__head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="fcard__logo" style={{ background: o.logoColor }} aria-hidden="true">{o.code}</span>
        <b>{o.airline}</b>
        <span className="fcard__chev"><Icon name="chevron" size={20} stroke={2.4} /></span>
        <span className="visually-hidden">{open ? "Скрыть подробности" : "Подробнее"}</span>
      </button>
      <div className="fcard__route">
        <div className="fcard__pt"><strong>{o.depart}</strong><b>{o.from.code}</b><small>{o.from.city}</small></div>
        <div className="fcard__mid"><small>{durationLabel(o.minutes)}</small><span className="fcard__line"><i /><Icon name="plane" size={14} /><i /></span><small>{stops}</small></div>
        <div className="fcard__pt fcard__pt--end"><strong>{o.arrive}{o.arriveDayShift > 0 && <sup>+{o.arriveDayShift}</sup>}</strong><b>{o.to.code}</b><small>{o.to.city}</small></div>
      </div>
      <div className="fcard__amen">
        {amen.map((a) => <span key={a.title}><Icon name={a.icon} size={20} /><span><small>{a.title}</small>{a.v}</span></span>)}
      </div>
      {open && (
        <dl className="fcard__details fade-up">
          <div><dt>Рейс</dt><dd>{o.flightNo}</dd></div>
          <div><dt>Дата вылета</dt><dd>{dayLabel(o.date)}</dd></div>
          {o.via && <div><dt>Пересадка</dt><dd>{o.via.city} ({o.via.code}), {durationLabel(o.layoverMinutes ?? 0)}</dd></div>}
          <div><dt>Время</dt><dd>местное для каждого аэропорта</dd></div>
          <div><dt>Цена и места</dt><dd>не проверены — демо-пример</dd></div>
        </dl>
      )}
      <div className="fcard__foot">
        <div className="fcard__price"><b>{money(o.price)}</b><small>на человека · пример</small></div>
        <button type="button" className={`btn btn--sm ${chosen ? "btn--ghost" : ""}`} aria-pressed={chosen} onClick={onChoose}>
          {chosen ? <><Icon name="check" size={18} stroke={2.4} />Выбран</> : "Выбрать"}
        </button>
      </div>
    </article>
  );
}
