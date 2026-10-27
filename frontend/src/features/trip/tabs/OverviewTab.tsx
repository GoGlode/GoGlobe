// Вкладка «Обзор»: hero, вкладки, что включено, почему этот вариант, ключевые места. Владелец: Frontend №2.
import { Link, useNavigate } from "react-router-dom";
import { money } from "../../../data/format";
import type { Trip } from "../../../data/types";
import { useFavorites } from "../../../state/FavoritesContext";
import { SHARE_TEXT, shareTrip } from "../../../data/share";
import { Icon, Photo, useToast } from "../../../ui";
import { BookButton, ProsCons, SourceLine, bookingHint, hasBooking } from "../OfferInfo";
import TripTabs from "../TripTabs";

export default function OverviewTab({ trip: t }: { trip: Trip }) {
  const nav = useNavigate();
  const { has, toggle } = useFavorites();
  const fav = has(t.id);
  const { show, toast } = useToast();
  const share = async () => { const m = SHARE_TEXT[await shareTrip(t)]; if (m) show(m); };
  return (
    <>
      <div className="thero">
        <Photo src={t.hero} pos={t.heroPos} alt={t.title} />
        <div className="thero__bar">
          <button className="circle-btn" aria-label="Назад" onClick={() => nav(-1)}><Icon name="back" /></button>
          <div className="row">
            <button className="circle-btn" aria-label="В избранное" style={{ color: fav ? "var(--c-danger)" : undefined }} onClick={() => toggle(t.id)}><Icon name="heart" filled={fav} /></button>
            <button className="circle-btn" aria-label="Поделиться" onClick={share}><Icon name="share" /></button>
          </div>
        </div>
        <div className="thero__txt">
          <small>{t.country}</small>
          <h1>{t.title.replace(/^[^:]+:\s*/, "").replace(" и ", " и ")}</h1>
          <div className="thero__meta"><span>{t.days} дней</span><span>· {t.dates.replace(/ \d{4}$/, "")}</span><span>· {t.travelers} человека</span></div>
        </div>
      </div>

      <div className="tsheet">
        <TripTabs id={t.id} current="overview" />
        <div className="tstats">
          <div><Icon name="calendar" size={24} /><span><b>{t.days} дней</b><small>{t.dates.replace(/ \d{4}$/, "")}</small></span></div>
          <div><Icon name="users" size={24} /><span><b>{t.travelers} человека</b><small>из Москвы</small></span></div>
          <div><Icon name="wallet" size={24} /><span><b>{money(t.price)}</b><small>на двоих</small></span></div>
        </div>
        <h3>Что включено</h3>
        <div className="tinc">{t.includes.map((x) => <div key={x.title}><Icon name={x.icon} size={26} /><span>{x.title}</span><small>{x.sub}</small></div>)}</div>
        <h3>Почему этот вариант</h3>
        <div className="treasons">{t.reasons.map((r) => <div key={r.text}><Icon name={r.icon} size={22} /><span>{r.text}</span></div>)}</div>
        <ProsCons trip={t} />
        <SourceLine trip={t} />
        {t.photos.length > 0 && <h3>Ключевые места</h3>}
        {t.photos.length > 0 && <div className="scroll-x tplaces">{t.photos.map((p) => <div className="tplace" key={p.label}><Photo src={p.src} pos={p.pos} alt={p.label} /><span>{p.label}</span></div>)}</div>}
        <div className="tcta">
          <BookButton trip={t} />
          <Link className="btn btn--ghost" to={`/trip/${t.id}/itinerary`}>Маршрут <Icon name="arrow-right" size={20} /></Link>
        </div>
      </div>
      {toast}
    </>
  );
}
