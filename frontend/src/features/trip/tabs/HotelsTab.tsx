// Вкладка «Отели»: города, фильтры, карточки. Владелец: Frontend №2.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { money } from "../../../data/format";
import type { Hotel, Trip } from "../../../data/types";
import { useFavorites } from "../../../state/FavoritesContext";
import { Icon, PageHeader, Photo, Rating } from "../../../ui";
import TripTabs from "../TripTabs";

const FILTERS = [{ id: "all", label: "Все" }, { id: "boutique", label: "Бутик-отели" }, { id: "stars45", label: "4★ и 5★" }, { id: "view", label: "С видом" }] as const;

export default function HotelsTab({ trip: t }: { trip: Trip }) {
  const nav = useNavigate();
  const { has, toggle } = useFavorites();
  const [city, setCity] = useState(t.cities[t.cities.length - 1]);
  const [f, setF] = useState<(typeof FILTERS)[number]["id"]>("all");
  const list = t.hotels.filter((h) => h.city === city && (f === "all" || h.tags.includes(f)));
  return (
    <>
      <PageHeader title="Отели" onBack={() => nav(`/trip/${t.id}`)} right={<button className="circle-btn" aria-label="В избранное" style={{ color: has(t.id) ? "var(--c-danger)" : undefined }} onClick={() => toggle(t.id)}><Icon name="heart" size={20} filled={has(t.id)} /></button>} />
      <TripTabs id={t.id} current="hotels" />
      {t.cities.length > 1 && <div className="seg" role="tablist">{t.cities.map((c) => <button key={c} role="tab" aria-selected={c === city} className={c === city ? "on" : ""} onClick={() => setCity(c)}>{c}</button>)}</div>}
      <div className="scroll-x" style={{ padding: "0 var(--s-4) 12px" }}>{FILTERS.map((x) => <button key={x.id} className={`chip ${f === x.id ? "chip--active" : ""}`} onClick={() => setF(x.id)}>{x.label}</button>)}</div>
      {list.length === 0 && <p className="muted" style={{ textAlign: "center", padding: 32 }}>В этом городе нет отелей по выбранному фильтру</p>}
      {list.map((h) => <HotelCard key={h.id} h={h} fav={has(h.id)} onFav={() => toggle(h.id)} />)}
      <p className="muted tdemo">Демо-данные: цены и рейтинги ориентировочные</p>
    </>
  );
}

function HotelCard({ h, fav, onFav }: { h: Hotel; fav: boolean; onFav: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <article className="hcard">
      <div className="hcard__img"><Photo src={h.photo} pos={h.photoPos} alt={h.name} />
        <button className={`hcard__heart ${fav ? "is-on" : ""}`} aria-label="В избранное" onClick={onFav}><Icon name="heart" size={22} filled={fav} /></button></div>
      <div className="hcard__body">
        <div className="hcard__top"><div><h3>{h.name}</h3>{h.rating != null && <Rating value={h.rating} count={h.reviews} />}</div><span className="circle-btn" style={{ width: 36, height: 36, color: "var(--c-primary)" }}><Icon name="chevron" size={18} /></span></div>
        <div className="hcard__loc"><Icon name="pin" size={18} />{h.location}</div>
        <div className="hcard__am">{h.amenities.map((a) => <span key={a.label}><Icon name={a.icon} size={18} />{a.label}</span>)}</div>
        <div className="hcard__foot">
          <div className="hcard__price"><b>{money(h.pricePerNight)}</b><small>за ночь</small></div>
          <button className="btn btn--sm" onClick={() => setOpen(!open)}>Подробнее <Icon name="arrow-right" size={18} /></button>
        </div>
        {open && <p className="hcard__note">Ссылка на бронирование появится после подключения реальных источников данных.</p>}
      </div>
    </article>
  );
}
