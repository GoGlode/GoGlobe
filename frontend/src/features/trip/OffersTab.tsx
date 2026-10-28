// Вкладки «Отели» / «Перелёты» поездки из API v0.3: состояния компонента, предложения, фильтры по реальным полям.
// Цены не суммируются и не сравниваются между разными basis; «Перейти к предложению» — только при реальной http(s)-ссылке.
import { useEffect, useMemo, useState } from "react";
import { ApiError, getFlights, getHotels, getTrip, startQuoteSearch } from "../../api/trips";
import type { Component, FlightList, FlightOffer, HotelList, HotelOffer, Price, Trip, Warning } from "../../api/v03";
import { dateRange, plural } from "../../data/format";
import { Icon, Photo, Rating } from "../../ui";
import { Notice } from "./ApiTripPage";
import { PriceBlock } from "./PriceBlock";
import { duration, hhmm, isHttp, when } from "./priceFormat";
import { useApi } from "./useApi";

type Kind = "hotels" | "flights";
type List = HotelList | FlightList;
const MISSING: Record<string, string> = { origin: "город вылета", travelers: "состав гостей", stay: "даты проживания", flight_dates: "даты перелёта" };
const minor = (p: Price) => (p.status !== "unknown" && p.money ? p.money.amount_minor : null);

export default function OffersTab({ kind, trip, onTrip }: { kind: Kind; trip: Trip; onTrip: (t: Trip) => void }) {
  const load = () => (kind === "hotels" ? getHotels(trip.trip_id) : getFlights(trip.trip_id)) as Promise<List>;
  const [s, reload, put] = useApi<List>(load, [trip.trip_id, kind, trip.revision]);
  const [tries, setTries] = useState(0);
  const state = s.status === "ready" ? s.data.state : null;

  // Пока поиск идёт — тихо опрашиваем (SSE для тарифов не обязателен); потолок, чтобы не крутиться бесконечно
  useEffect(() => {
    if ((state !== "queued" && state !== "processing") || tries >= 20) return;
    const h = setTimeout(() => { load().then(put).catch(() => undefined); setTries((n) => n + 1); }, 2500);
    return () => clearTimeout(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, tries]);

  if (s.status === "loading") return <div className="page atrip-skel" aria-busy="true"><i /><i /></div>;
  if (s.status === "error") return <Notice icon="x" title="Не удалось загрузить предложения" text="Маршрут остался доступным — проблема только с тарифами." ><button className="btn btn--sm" onClick={reload}>Повторить</button></Notice>;
  const l = s.data;
  const comp: Component = trip.components[kind];
  const name = kind === "hotels" ? "отелей" : "перелётов", what = kind === "hotels" ? "отели" : "перелёты";
  const stale = l.trip_revision !== trip.revision;

  return (
    <div className="page atrip">
      {l.warnings.map((w: Warning) => <p className="atrip__warn" role="note" key={w.code + w.message}><Icon name="clock" size={16} />{w.message}</p>)}
      {stale && l.items.length > 0 && <p className="atrip__warn" role="note">Поездка изменилась после этого поиска — цены относятся к прежним параметрам. Запустите поиск заново.</p>}
      {(l.state === "queued" || l.state === "processing") && <p className="atrip__warn" role="status" aria-live="polite"><Icon name="refresh" size={16} />Ищем предложения… {tries >= 20 && "Поиск идёт дольше обычного — обновите страницу позже."}</p>}
      {l.state === "failed" && <p className="atrip__warn atrip__warn--err" role="alert">Поиск {name} не удался{l.error ? `: ${l.error.message}` : ""}. Маршрут по дням доступен.</p>}
      {l.state === "empty" && <p className="muted atrip__fine">По заданным параметрам {name} не найдено. Попробуйте другие даты.</p>}
      {l.state === "blocked" && <p className="muted atrip__fine">Чтобы искать {what}, не хватает: {l.missing_fields.map((f) => MISSING[f] ?? f).join(", ") || "данных"}.</p>}
      {l.context && <p className="atrip__ctx">{kind === "hotels"
        ? `Для ${guests(l as HotelList)}, ${dateRange((l as HotelList).context!.stay.check_in, (l as HotelList).context!.stay.check_out)}`
        : `Для ${guestsF(l as FlightList)}, из ${(l as FlightList).context!.origin}, ${dateRange((l as FlightList).context!.flight_dates.outbound_date, (l as FlightList).context!.flight_dates.return_date)}`}</p>}
      {l.items.length > 0 && (kind === "hotels" ? <Hotels items={l.items as HotelOffer[]} /> : <Flights items={l.items as FlightOffer[]} />)}
      {l.items.length > 0 && l.sources.length > 0 && <p className="muted atrip__fine">Источники: {l.sources.map((x) => `${x.name} (${when(x.checked_at) ?? "—"})`).join("; ")}{l.data_mode === "demo" ? " · демо" : ""}</p>}
      {comp.state !== "processing" && comp.state !== "queued" && <QuoteForm kind={kind} trip={trip} onTrip={onTrip} onStarted={() => { setTries(0); reload(); }} />}
    </div>
  );
}

const guests = (l: HotelList) => { const n = l.context!.travelers.adults + l.context!.travelers.children_ages.length; return `${n} ${plural(n, "гостя", "гостей", "гостей")}`; };
const guestsF = (l: FlightList) => { const n = l.context!.travelers.adults + l.context!.travelers.children_ages.length; return `${n} ${plural(n, "пассажира", "пассажиров", "пассажиров")}`; };

function Hotels({ items }: { items: HotelOffer[] }) {
  const [stars, setStars] = useState(0);
  const [budget, setBudget] = useState("");
  const [sort, setSort] = useState<"price" | "rating">("price");
  const list = useMemo(() => {
    const cap = budget ? Number(budget) * 100 : null;
    const f = items.filter((h) => (h.stars ?? 0) >= stars && (cap == null || (minor(h.total_price) ?? Infinity) <= cap));
    const key = (h: HotelOffer) => sort === "price" ? (minor(h.total_price) ?? Infinity) : -(h.rating ?? -1);
    return [...f].sort((a, b) => key(a) - key(b));
  }, [items, stars, budget, sort]);
  return (
    <>
      <div className="atrip__filters">
        <label>Звёзды<select value={stars} onChange={(e) => setStars(+e.target.value)}><option value={0}>Любые</option><option value={3}>3★+</option><option value={4}>4★+</option><option value={5}>5★</option></select></label>
        <label>Бюджет за проживание, ₽<input inputMode="numeric" value={budget} onChange={(e) => setBudget(e.target.value.replace(/\D/g, ""))} placeholder="без лимита" /></label>
        <label>Сортировка<select value={sort} onChange={(e) => setSort(e.target.value as "price" | "rating")}><option value="price">Сначала дешевле</option><option value="rating">По рейтингу</option></select></label>
      </div>
      {list.length === 0 && <p className="muted atrip__fine">Нет предложений по выбранным фильтрам ({items.length} скрыто).</p>}
      {list.map((h) => (
        <article className="card offer" key={h.offer_id}>
          {h.photos[0] && <div className="offer__img"><Photo src={h.photos[0]} alt={h.name} /></div>}
          <div className="offer__top"><h3>{h.name}</h3>{h.rating != null && <Rating value={h.rating} />}</div>
          <p className="muted">{h.stars ? `${h.stars}★ · ` : ""}{dateRange(h.check_in, h.check_out)}{h.place ? ` · ${h.place.name}` : ""}</p>
          <PriceBlock p={h.total_price} />
          {minor(h.nightly_price) != null && <PriceBlock p={h.nightly_price} compact />}
          {h.availability === "unknown" && <small className="muted">Наличие мест не подтверждено</small>}
          <Go url={h.booking_url} />
        </article>
      ))}
    </>
  );
}

const stops = (n: number) => (n <= 1 ? "прямой" : `${n - 1} ${plural(n - 1, "пересадка", "пересадки", "пересадок")}`);
const mins = (f: FlightOffer) => [...f.outbound_segments, ...f.inbound_segments].reduce((a, s) => a + s.duration_minutes, 0);
const isDirect = (f: FlightOffer) => f.outbound_segments.length === 1 && f.inbound_segments.length === 1; // прямой — ни одной пересадки в обе стороны

function Flights({ items }: { items: FlightOffer[] }) {
  const [direct, setDirect] = useState(false);
  const [budget, setBudget] = useState("");
  const [sort, setSort] = useState<"price" | "time">("price");
  const list = useMemo(() => {
    const cap = budget ? Number(budget) * 100 : null;
    const f = items.filter((x) => (!direct || isDirect(x)) && (cap == null || (minor(x.total_price) ?? Infinity) <= cap));
    const key = (x: FlightOffer) => (sort === "price" ? (minor(x.total_price) ?? Infinity) : mins(x));
    return [...f].sort((a, b) => key(a) - key(b));
  }, [items, direct, budget, sort]);
  return (
    <>
      <div className="atrip__filters">
        <label className="atrip__check"><input type="checkbox" checked={direct} onChange={(e) => setDirect(e.target.checked)} />Только прямые</label>
        <label>Бюджет на перелёт, ₽<input inputMode="numeric" value={budget} onChange={(e) => setBudget(e.target.value.replace(/\D/g, ""))} placeholder="без лимита" /></label>
        <label>Сортировка<select value={sort} onChange={(e) => setSort(e.target.value as "price" | "time")}><option value="price">Сначала дешевле</option><option value="time">Сначала быстрее</option></select></label>
      </div>
      {list.length === 0 && <p className="muted atrip__fine">Нет рейсов по выбранным фильтрам ({items.length} скрыто).</p>}
      {list.map((f) => (
        <article className="card offer" key={f.offer_id}>
          {([["Туда", f.outbound_segments], ["Обратно", f.inbound_segments]] as const).map(([lbl, segs]) => segs.length > 0 && (
            <div className="offer__leg" key={lbl}>
              <b>{lbl}</b>
              <span>{segs[0].origin.code} {hhmm(segs[0].departure_at, segs[0].origin.timezone)} → {segs[segs.length - 1].destination.code} {hhmm(segs[segs.length - 1].arrival_at, segs[segs.length - 1].destination.timezone)}</span>
              <small className="muted">{duration(segs.reduce((a, x) => a + x.duration_minutes, 0))} · {stops(segs.length)}</small>
            </div>
          ))}
          <PriceBlock p={f.total_price} />
          {f.availability === "unknown" && <small className="muted">Наличие мест не подтверждено</small>}
          <Go url={f.booking_url} />
        </article>
      ))}
    </>
  );
}

/** Только подтверждённая ссылка поставщика; иначе кнопки нет вовсе. */
function Go({ url }: { url: string | null }) {
  if (!isHttp(url)) return <small className="muted">Ссылка на предложение не получена</small>;
  return <a className="btn btn--sm btn--ghost" href={url} target="_blank" rel="noopener noreferrer">Перейти к предложению<Icon name="arrow-right" size={18} /></a>;
}

function QuoteForm({ kind, trip, onTrip, onStarted }: { kind: Kind; trip: Trip; onTrip: (t: Trip) => void; onStarted: () => void }) {
  const [adults, setAdults] = useState(String(trip.travelers?.adults ?? 2));
  const [origin, setOrigin] = useState(trip.origin ?? "");
  const [a, setA] = useState(trip.schedule.start_date ?? "");
  const [b, setB] = useState(trip.schedule.end_date ?? "");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ok = Number(adults) >= 1 && a && b && b > a && (kind === "hotels" || origin.trim());
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null); setBusy(true);
    try {
      await startQuoteSearch(trip.trip_id, {
        expected_revision: trip.revision, components: [kind], travelers: { adults: Number(adults), children_ages: trip.travelers?.children_ages ?? [] },
        ...(kind === "hotels" ? { stay: { check_in: a, check_out: b } } : { origin: origin.trim(), flight_dates: { outbound_date: a, return_date: b } }),
      });
      onStarted();
    } catch (x) {
      if (x instanceof ApiError && x.isConflict) {
        try { onTrip(await getTrip(trip.trip_id)); } catch { /* оставим форму */ }
        setErr("Поездка изменилась в другом месте — данные обновлены, проверьте поля и отправьте ещё раз.");
      } else setErr(x instanceof ApiError ? x.message : "Не удалось запустить поиск");
    } finally { setBusy(false); }
  };
  return (
    <form className="card atrip__sched" onSubmit={submit}>
      <h3>{kind === "hotels" ? "Найти отели" : "Найти перелёты"}</h3>
      <p className="muted atrip__fine">Поиск запускается только по вашему подтверждению. Даты вылета не считаются датами заезда автоматически.</p>
      <label>Взрослых<input type="number" min={1} max={9} value={adults} onChange={(e) => setAdults(e.target.value)} /></label>
      {kind === "flights" && <label>Город вылета<input value={origin} onChange={(e) => setOrigin(e.target.value)} placeholder="Москва" maxLength={80} /></label>}
      <label>{kind === "hotels" ? "Заезд" : "Вылет туда"}<input type="date" value={a} onChange={(e) => setA(e.target.value)} /></label>
      <label>{kind === "hotels" ? "Выезд" : "Вылет обратно"}<input type="date" value={b} min={a || undefined} onChange={(e) => setB(e.target.value)} /></label>
      {err && <p className="atrip__warn atrip__warn--err" role="alert">{err}</p>}
      <button className="btn btn--sm" type="submit" disabled={!ok || busy}>{busy ? "Запускаем…" : "Запустить поиск"}</button>
    </form>
  );
}
