// Вкладка «Маршрут»: переключатель дней + таймлайн. Владелец: Frontend №2.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import type { Trip } from "../../../data/types";
import { useFavorites } from "../../../state/FavoritesContext";
import { Icon, PageHeader, Photo } from "../../../ui";
import TripTabs from "../TripTabs";

export default function ItineraryTab({ trip: t }: { trip: Trip }) {
  const [cur, setCur] = useState(1);
  const { has, toggle } = useFavorites();
  const nav = useNavigate();
  const jump = (d: number) => { setCur(d); document.getElementById(`day-${d}`)?.scrollIntoView({ behavior: "smooth", block: "start" }); };
  return (
    <>
      <PageHeader title="Маршрут" onBack={() => nav(`/trip/${t.id}`)} right={<>
        <button className="circle-btn" aria-label="В избранное" style={{ color: has(t.id) ? "var(--c-danger)" : undefined }} onClick={() => toggle(t.id)}><Icon name="heart" size={20} filled={has(t.id)} /></button>
      </>} />
      <TripTabs id={t.id} current="itinerary" />
      <div className="days scroll-x">
        {t.itinerary.map((d) => <button key={d.day} className={`chip ${cur === d.day ? "chip--active" : ""}`} onClick={() => jump(d.day)}>День {d.day}</button>)}
      </div>
      <div className="tl">
        {t.itinerary.map((d) => (
          <section className="tl__day" id={`day-${d.day}`} key={d.day}>
            <div className="tl__rail"><div className="tl__dot" /></div>
            <div className="tl__card">
              <div className="tl__head"><span><b>День {d.day}</b><small>{d.date}</small></span><Icon name="chevron" size={18} /></div>
              <div className="tl__img"><Photo src={d.photo} pos={d.photoPos} alt={d.title} /></div>
              <h4>{d.title}</h4>
              <div className="tl__items">{d.items.map((i) => <div key={i.label}><Icon name={i.icon} size={18} />{i.label}</div>)}</div>
            </div>
          </section>
        ))}
      </div>
    </>
  );
}
