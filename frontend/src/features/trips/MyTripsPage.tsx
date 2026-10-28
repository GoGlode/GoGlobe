// «Мои поездки»: календарь с диапазонами поездок + предстоящие / прошлые. Владелец: Frontend №2.
// Данные: GET /api/v1/trips?saved=true (v0.3). Без VITE_API_URL — явный демо-режим: демо-примеры (data/trips.ts → MY_TRIPS) + сохранённое в этой вкладке.
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { MY_TRIPS, type MyTrip } from "../../data/trips";
import { plural } from "../../data/format";
import { ApiError, isDemoApi, listSaved } from "../../api/trips";
import type { TripCard } from "../../api/v03";
import { Icon, PageHeader, Photo } from "../../ui";
import { Notice } from "../trip/ApiTripPage";
import { useApi } from "../trip/useApi";
import "./trips.css";

const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const STATUS = { prep: { label: "Подготовка", icon: "clock" as const }, confirmed: { label: "Подтверждено", icon: "check" as const } };

/** Локальная дата → "YYYY-MM-DD" (без UTC-сдвига) */
const key = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const parse = (k: string) => { const [y, m, d] = k.split("-").map(Number); return new Date(y, m - 1, d); };
const daysOf = (t: MyTrip) => Math.round((parse(t.end).getTime() - parse(t.start).getTime()) / 86_400_000) + 1;
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

function rangeLabel(t: MyTrip): string {
  const a = parse(t.start), b = parse(t.end);
  const dm = (d: Date) => d.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
  if (a.getFullYear() !== b.getFullYear()) return `${dm(a)} ${a.getFullYear()} — ${dm(b)} ${b.getFullYear()}`;
  if (a.getMonth() !== b.getMonth()) return `${dm(a)} — ${dm(b)} ${b.getFullYear()}`;
  return `${a.getDate()} — ${dm(b)} ${b.getFullYear()}`;
}

/** Недели месяца с понедельника, включая хвосты соседних месяцев. */
function monthGrid(y: number, m: number): Date[][] {
  const first = new Date(y, m, 1);
  const offset = (first.getDay() + 6) % 7;
  const total = Math.ceil((offset + new Date(y, m + 1, 0).getDate()) / 7) * 7;
  const cells = Array.from({ length: total }, (_, i) => new Date(y, m, 1 - offset + i));
  return Array.from({ length: total / 7 }, (_, w) => cells.slice(w * 7, w * 7 + 7));
}

export default function MyTripsPage() {
  const nav = useNavigate();
  const today = key(new Date());
  const [saved, reload] = useApi(listSaved, []);
  const cards: TripCard[] = saved.status === "ready" ? saved.data.items : [];
  const dated: MyTrip[] = cards.filter((c) => c.start_date && c.end_date).map((c) => ({ tripId: c.trip_id, title: c.title, start: c.start_date!, end: c.end_date!, img: c.cover_url ?? "" }));
  const undated = cards.filter((c) => !c.start_date || !c.end_date);
  const trips = useMemo(() => (isDemoApi ? [...MY_TRIPS, ...dated] : dated), [saved]); // eslint-disable-line react-hooks/exhaustive-deps
  const upcomingAll = useMemo(() => trips.filter((t) => t.end >= today).sort((a, b) => a.start.localeCompare(b.start)), [trips, today]);
  const pastAll = useMemo(() => trips.filter((t) => t.end < today).sort((a, b) => b.start.localeCompare(a.start)), [trips, today]);

  const initial = parse(upcomingAll[0]?.start ?? today);
  const [month, setMonth] = useState({ y: initial.getFullYear(), m: initial.getMonth() });
  const [selected, setSelected] = useState<string | null>(null);

  const weeks = useMemo(() => monthGrid(month.y, month.m), [month]);
  const tripsOn = (k: string) => trips.filter((t) => t.start <= k && k <= t.end);
  const shift = (delta: number) => setMonth(({ y, m }) => { const d = new Date(y, m + delta, 1); return { y: d.getFullYear(), m: d.getMonth() }; });
  const pick = (d: Date) => {
    const k = key(d);
    if (d.getMonth() !== month.m) setMonth({ y: d.getFullYear(), m: d.getMonth() });
    setSelected(selected === k ? null : k);
  };

  const onDay = (t: MyTrip) => !selected || (t.start <= selected && selected <= t.end);
  const upcoming = upcomingAll.filter(onDay), past = pastAll.filter(onDay);
  const monthTitle = `${cap(new Date(month.y, month.m, 1).toLocaleDateString("ru-RU", { month: "long" }))} ${month.y}`;

  if (!isDemoApi && saved.status === "error") return (
    <div className="mytrips-screen"><PageHeader large title="Мои поездки" />
      <Notice icon="x" title="Не удалось загрузить поездки" text={saved.error instanceof ApiError ? saved.error.message : "Ошибка"}><button className="btn btn--sm" onClick={reload}>Повторить</button></Notice></div>
  );
  return (
    <div className="mytrips-screen">
      <PageHeader large title="Мои поездки"
        right={<button type="button" className="circle-btn" aria-label="Новая поездка" onClick={() => nav("/")}><Icon name="plus" /></button>} />
      <div className="page mytrips">
        <section className="cal card" aria-label="Календарь поездок">
          <div className="cal__head">
            <h2 aria-live="polite">{monthTitle}</h2>
            <div className="row" style={{ gap: 8 }}>
              <button type="button" className="cal__nav" aria-label="Предыдущий месяц" onClick={() => shift(-1)}><Icon name="chevron-left" size={20} stroke={2.4} /></button>
              <button type="button" className="cal__nav" aria-label="Следующий месяц" onClick={() => shift(1)}><Icon name="chevron" size={20} stroke={2.4} /></button>
            </div>
          </div>
          <div className="cal__grid" role="grid">
            <div className="cal__row" role="row">{WEEKDAYS.map((w) => <span key={w} className="cal__wd" role="columnheader">{w}</span>)}</div>
            {weeks.map((week) => (
              <div className="cal__row" role="row" key={key(week[0])}>
                {week.map((d) => {
                  const k = key(d), on = tripsOn(k);
                  const cls = [
                    "cal__day",
                    d.getMonth() !== month.m && "is-out",
                    on.length > 0 && "in-trip",
                    on.some((t) => t.start === k) && "trip-start",
                    on.some((t) => t.end === k) && "trip-end",
                    k === today && "is-today",
                    k === selected && "is-selected",
                  ].filter(Boolean).join(" ");
                  const label = d.toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" })
                    + (on.length ? `, ${on.map((t) => t.title).join(", ")}` : "");
                  return (
                    <span key={k} role="gridcell" className={cls}>
                      <button type="button" aria-label={label} aria-pressed={k === selected} onClick={() => pick(d)}>{d.getDate()}</button>
                    </span>
                  );
                })}
              </div>
            ))}
          </div>
        </section>

        {selected && (
          <div className="mytrips__filter">
            <span>Поездки на {parse(selected).toLocaleDateString("ru-RU", { day: "numeric", month: "long" })}</span>
            <button type="button" className="chip" onClick={() => setSelected(null)}><Icon name="x" size={14} />Показать все</button>
          </div>
        )}

        {isDemoApi && <p className="muted" style={{ fontSize: 13, margin: 0 }}>Демо-режим: сервер не подключён, примеры ниже условные; сохранённое вами живёт только в этой вкладке.</p>}
        {!isDemoApi && saved.status === "loading" && <p className="muted" role="status">Загружаем поездки…</p>}
        {upcoming.length > 0 && <TripSection title="Предстоящие поездки" list={upcoming} />}
        {past.length > 0 && <TripSection title="Прошлые поездки" list={past} past />}
        {!selected && undated.length > 0 && (
          <section className="mytrips__sec" aria-label="Без дат">
            <h2 className="h-title">Без дат</h2>
            {undated.map((c) => (
              <Link key={c.trip_id} to={`/trip/${c.trip_id}`} className="mtcard">
                <span className="mtcard__img"><Photo src={c.cover_url ?? ""} alt="" /></span>
                <span className="mtcard__txt"><b>{c.title}</b><small className="muted">{c.duration_days ? `${c.duration_days} ${plural(c.duration_days, "день", "дня", "дней")} · ` : ""}даты не назначены</small></span>
                <span className="mtcard__go"><Icon name="chevron" size={20} stroke={2.4} /></span>
              </Link>
            ))}
          </section>
        )}
        {selected && upcoming.length === 0 && past.length === 0 && (
          <div className="mytrips__empty card">
            <p><b>На эту дату поездок нет</b></p>
            <p className="muted">Выберите другую дату или спланируйте новое путешествие.</p>
            <Link className="btn btn--sm" to="/">Создать путешествие</Link>
          </div>
        )}
        {!selected && trips.length === 0 && undated.length === 0 && saved.status !== "loading" && (
          <div className="mytrips__empty card"><p><b>Поездок пока нет</b></p><Link className="btn btn--sm" to="/">Создать путешествие</Link></div>
        )}
      </div>
    </div>
  );
}

function TripSection({ title, list, past }: { title: string; list: MyTrip[]; past?: boolean }) {
  return (
    <section className="mytrips__sec" aria-label={title}>
      <h2 className="h-title">{title}</h2>
      {list.map((t) => {
        const days = daysOf(t), st = !past && t.status ? STATUS[t.status] : null;
        return (
          <Link key={t.tripId + t.start} to={`/trip/${t.tripId}`} className="mtcard">
            <span className="mtcard__img"><Photo src={t.img} alt="" /></span>
            <span className="mtcard__txt">
              <b>{t.title}</b>
              <small className="muted">{rangeLabel(t)}{!past && <span className="nowrap"> · {days}{"\u00a0"}{plural(days, "день", "дня", "дней")}</span>}</small>
              {st && <span className={`mtcard__status is-${t.status}`}><Icon name={st.icon} size={14} stroke={2.4} />{st.label}</span>}
            </span>
            <span className="mtcard__go"><Icon name="chevron" size={20} stroke={2.4} /></span>
          </Link>
        );
      })}
    </section>
  );
}
