// Поездка из API v0.3 (GET /trips/{id}): грузится по URL, переживает reload. Владелец: Frontend №2.
// Trip — самостоятельный маршрут: цены/отели/рейсы могут отсутствовать, это нормальное состояние, а не ошибка.
import { useState } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { ApiError, addFavorite, getTrip, isDemoApi, removeFavorite, saveTrip, setSchedule, unsaveTrip } from "../../api/trips";
import type { Component, Day, Item, Trip } from "../../api/v03";
import { dateRange, plural } from "../../data/format";
import { Icon, PageHeader, Photo, useToast } from "../../ui";
import OffersTab from "./OffersTab";
import { PriceBlock } from "./PriceBlock";
import { useApi } from "./useApi";
import { when } from "./priceFormat";
import "./apitrip.css";

const TABS = [{ id: "overview", label: "Обзор" }, { id: "itinerary", label: "Маршрут" }, { id: "hotels", label: "Отели" }, { id: "flights", label: "Перелёты" }] as const;
type TabId = (typeof TABS)[number]["id"];

export function Notice({ icon, title, text, children }: { icon: "x" | "clock" | "search" | "refresh"; title: string; text: string; children?: React.ReactNode }) {
  return (
    <div className="page atrip-notice" role="status">
      <div className="circle-btn" style={{ width: 64, height: 64 }}><Icon name={icon} size={28} /></div>
      <h2>{title}</h2><p className="muted">{text}</p><div className="row" style={{ gap: 8, justifyContent: "center" }}>{children}</div>
    </div>
  );
}

export default function ApiTripPage({ id, tab }: { id: string; tab: TabId }) {
  const nav = useNavigate();
  const [s, reload, put] = useApi(() => getTrip(id), [id]);
  const { show, toast } = useToast();
  const [busy, setBusy] = useState(false);

  if (s.status === "loading") return <><PageHeader title="Поездка" onBack={() => nav(-1)} /><div className="page atrip-skel" aria-busy="true" aria-label="Загружаем поездку"><i /><i /><i /></div></>;
  if (s.status === "error") {
    const e = s.error;
    if (e.isExpired) return <Notice icon="clock" title="Срок хранения истёк" text="Эта поездка больше не хранится на сервере. Создайте новую — подборка соберётся заново."><Link className="btn btn--sm" to="/">Найти путешествие</Link></Notice>;
    if (e.isNotFound) return <Notice icon="search" title="Поездка не найдена" text="Возможно, ссылка неверна или поездка принадлежит другой сессии браузера."><Link className="btn btn--sm" to="/">Найти путешествие</Link></Notice>;
    return <Notice icon="x" title="Не удалось загрузить поездку" text={e.status === 0 ? "Нет связи с сервером. Проверьте интернет." : e.message}><button className="btn btn--sm" onClick={reload}>Повторить</button></Notice>;
  }
  const t = s.data;
  const expired = t.expires_at != null && Date.parse(t.expires_at) < Date.now();
  if (expired) return <Notice icon="clock" title="Срок хранения истёк" text="Эта поездка больше не хранится на сервере."><Link className="btn btn--sm" to="/">Найти путешествие</Link></Notice>;

  const act = async (fn: () => Promise<unknown>, ok?: string) => {
    setBusy(true);
    try { await fn(); const fresh = await getTrip(id); put(fresh); if (ok) show(ok); }
    catch (e) {
      // 409: поездка изменилась в другом месте — подтягиваем актуальную revision, пользователь повторяет действие
      if (e instanceof ApiError && e.isConflict) { try { put(await getTrip(id)); } catch { /* оставим как есть */ } show("Поездка изменилась — данные обновлены, повторите действие"); }
      else show(e instanceof ApiError ? e.message : "Не получилось, попробуйте ещё раз");
    }
    finally { setBusy(false); }
  };
  const toggleSave = () => act(() => (t.saved_at ? unsaveTrip(id) : saveTrip(id)), t.saved_at ? "Убрано из «Моих поездок»" : "Поездка сохранена");
  const toggleFav = () => act(() => (t.favorite_at ? removeFavorite(id) : addFavorite(id)), t.favorite_at ? "Убрано из избранного" : "Добавлено в избранное");

  return (
    <>
      <PageHeader title={t.destination.name} onBack={() => nav(-1)} right={<>
        <button className="circle-btn" aria-label={t.saved_at ? "Убрать из сохранённых" : "Сохранить поездку"} aria-pressed={!!t.saved_at} disabled={busy} style={{ color: t.saved_at ? "var(--c-primary)" : undefined }} onClick={toggleSave}><Icon name="bag" size={20} filled={!!t.saved_at} /></button>
        <button className="circle-btn" aria-label="В избранное" aria-pressed={!!t.favorite_at} disabled={busy} style={{ color: t.favorite_at ? "var(--c-danger)" : undefined }} onClick={toggleFav}><Icon name="heart" size={20} filled={!!t.favorite_at} /></button>
      </>} />
      <div className="ttabs scroll-x" role="tablist">
        {TABS.map((x) => <NavLink key={x.id} role="tab" aria-selected={x.id === tab} replace to={x.id === "overview" ? `/trip/${id}` : `/trip/${id}/${x.id}`} className={`ttab ${x.id === tab ? "is-on" : ""}`}>{x.label}</NavLink>)}
      </div>
      {t.data_mode === "demo" && <p className="page atrip-demo">Демо-данные: условный маршрут, не реальные тарифы.{isDemoApi && " Сервер не подключён — изменения живут только в этой вкладке."}</p>}
      {tab === "overview" && <Overview t={t} busy={busy} onSchedule={(a, b) => act(() => setSchedule(id, { expected_revision: t.revision, start_date: a, end_date: b, timezone: t.schedule.timezone ?? t.destination.timezone ?? "UTC" }), "Даты назначены")} onReload={reload} />}
      {tab === "itinerary" && <Itinerary t={t} />}
      {(tab === "hotels" || tab === "flights") && <OffersTab key={tab} kind={tab} trip={t} onTrip={put} />}
      {toast}
    </>
  );
}

const CSTATE: Record<Component["state"], string> = { not_requested: "не запрошено", blocked: "не хватает данных", queued: "в очереди", processing: "ищем", ready: "готово", empty: "ничего не найдено", failed: "ошибка" };

function Overview({ t, busy, onSchedule, onReload }: { t: Trip; busy: boolean; onSchedule: (a: string, b: string) => void; onReload: () => void }) {
  const n = t.itinerary?.days.length ?? t.duration_days ?? 0;
  const [start, setStart] = useState(t.schedule.start_date ?? "");
  const end = start && n ? new Date(Date.parse(`${start}T00:00:00Z`) + (n - 1) * 864e5).toISOString().slice(0, 10) : "";
  const dated = t.schedule.start_date && t.schedule.end_date;
  return (
    <div className="page atrip">
      {t.destination.photos[0] && <div className="atrip__hero"><Photo src={t.destination.photos[0]} alt={t.destination.name} /></div>}
      <h2>{t.title}</h2>
      <p className="muted">{t.description}</p>
      <div className="atrip__facts">
        <span><Icon name="calendar" size={18} />{dated ? dateRange(t.schedule.start_date!, t.schedule.end_date!) : "Даты не назначены"}</span>
        {n > 0 && <span><Icon name="clock" size={18} />{n} {plural(n, "день", "дня", "дней")}</span>}
        {t.travelers && <span><Icon name="users" size={18} />{t.travelers.adults + t.travelers.children_ages.length} {plural(t.travelers.adults + t.travelers.children_ages.length, "человек", "человека", "человек")}</span>}
        {t.origin && <span><Icon name="pin" size={18} />из {t.origin}</span>}
      </div>
      <h3>Стоимость</h3>
      <PriceBlock p={t.price_summary} empty="Цена поездки пока неизвестна — тарифы не запрошены или не найдены." />
      <h3>Что найдено</h3>
      <ul className="atrip__comp">
        {(["itinerary", "hotels", "flights"] as const).map((k) => (
          <li key={k}><span>{{ itinerary: "Программа по дням", hotels: "Отели", flights: "Перелёты" }[k]}</span><b className={`cs cs--${t.components[k].state}`}>{CSTATE[t.components[k].state]}{t.components[k].incomplete ? " · неполно" : ""}</b></li>
        ))}
      </ul>
      <h3>Календарь</h3>
      <form className="card atrip__sched" onSubmit={(e) => { e.preventDefault(); if (start && end) onSchedule(start, end); }}>
        <p className="muted">{dated ? "Поездка стоит в календаре «Мои поездки». Можно перенести." : "Назначьте дату начала — поездка появится в календаре «Мои поездки»."}{n ? ` Длительность по программе: ${n} дн.` : " Длительность неизвестна — назначить даты нельзя."}</p>
        <label>Начало<input type="date" value={start} onChange={(e) => setStart(e.target.value)} disabled={!n || busy} /></label>
        {end && <p>Окончание: <b>{dateRange(end, end)}</b></p>}
        <button className="btn btn--sm" type="submit" disabled={!start || !end || busy}>{dated ? "Перенести даты" : "Назначить даты"}</button>
        <p className="muted atrip__fine">Внешняя синхронизация (Google Calendar и др.) не подключена.</p>
        <button type="button" className="atrip__link" onClick={onReload}>Обновить поездку</button>
      </form>
      {t.sources.length > 0 && <><h3>Источники</h3><ul className="atrip__src">{t.sources.map((s) => <li key={s.source_id}>{s.name}<small className="muted"> · проверено {when(s.checked_at) ?? "—"}</small></li>)}</ul></>}
      <p className="muted atrip__fine">Бронирование не оформлено: «найденный тариф» — не бронь.</p>
    </div>
  );
}

const KIND: Record<Item["kind"], string> = { activity: "Активность", arrival: "Прибытие", departure: "Отъезд", hotel: "Отель", meal: "Питание", transfer: "Трансфер" };
const VER: Record<Item["verification"], string> = { suggested: "Предложено", verified: "Проверено", unknown: "Не проверено" };

function Itinerary({ t }: { t: Trip }) {
  const days = t.itinerary?.days ?? [];
  if (t.components.itinerary.state !== "ready" && !days.length) return <Notice icon="clock" title="Программа ещё не готова" text={`Статус: ${CSTATE[t.components.itinerary.state]}.${t.components.itinerary.error ? " " + t.components.itinerary.error.message : ""}`} />;
  if (!days.length) return <Notice icon="search" title="Программы по дням нет" text="Источники не передали маршрут для этой поездки." />;
  return (
    <div className="page atrip">
      {days.map((d: Day) => (
        <section className="card atrip__day" key={d.day_index} aria-label={`День ${d.day_index}`}>
          <h3>День {d.day_index}{d.date && <small className="muted"> · {dateRange(d.date, d.date)}</small>}</h3>
          {d.items.length === 0 && <p className="muted">На этот день ничего не запланировано.</p>}
          <ol>
            {[...d.items].sort((a, b) => a.order - b.order).map((i) => (
              <li key={i.item_id}>
                <span className="atrip__time">{i.local_time ?? "—"}</span>
                <span className="atrip__what"><b>{i.title}</b>
                  <small className="muted">{KIND[i.kind]}{i.place ? ` · ${i.place.name}` : ""}</small></span>
                <em className={`ver ver--${i.verification}`}>{VER[i.verification]}</em>
              </li>
            ))}
          </ol>
        </section>
      ))}
    </div>
  );
}
