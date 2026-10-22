// Вкладка «Перелёты»: тип маршрута, форма (откуда/куда/даты/пассажиры/класс), карточки рейсов. Владелец: Frontend №1.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { money } from "../../../data/format";
import type { Flight, Trip } from "../../../data/types";
import { Icon, PageHeader, type IconName } from "../../../ui";
import TripTabs from "../TripTabs";
import "./flights.css";

const KINDS = ["Туда и обратно", "В одну сторону", "Сложный маршрут"];
const ru = (iso: string) => new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" }).replace(" г.", "");

export default function FlightsTab({ trip: t }: { trip: Trip }) {
  const nav = useNavigate();
  const [kind, setKind] = useState(0);
  const [loading, setLoading] = useState(false);
  const [picked, setPicked] = useState<string | null>(null);
  const f0 = t.flights[0];
  const search = () => { setLoading(true); setTimeout(() => setLoading(false), 600); };
  return (
    <>
      <PageHeader title="Перелёты" onBack={() => nav(`/trip/${t.id}`)} right={<span className="circle-btn"><Icon name="filter" size={20} /></span>} />
      <TripTabs id={t.id} current="flights" />
      <div className="fl">
        <div className="fl__kinds scroll-x" role="tablist">{KINDS.map((k, i) => <button key={k} role="tab" aria-selected={i === kind} className={`chip ${i === kind ? "chip--active" : ""}`} onClick={() => setKind(i)}>{k}</button>)}</div>
        <div className="fl__form">
          <Field icon="pin" v={`${f0.fromCity} (${f0.from})`} /><Field icon="pin" v={`${f0.toCity} (${f0.to})`} />
          <span className="fl__swap circle-btn" aria-hidden="true"><Icon name="swap" size={16} /></span>
          <Field icon="calendar" v={ru(t.dateRange[0])} />{kind === 1 ? <Field icon="calendar" v="—" dim /> : <Field icon="calendar" v={ru(t.dateRange[1])} />}
          <Field icon="users" label="Пассажиры" v={`${t.travelers} взрослых`} /><Field icon="user" label="Класс" v="Эконом" />
        </div>
        <button className="btn fl__go" onClick={search} disabled={loading}><Icon name="search" size={22} /> {loading ? "Ищем рейсы…" : "Найти рейсы"} {!loading && <Icon name="arrow-right" size={20} />}</button>

        {loading ? <div className="fl__skel" aria-busy="true"><i /><i /></div> : t.flights.map((f) => <FlightCard key={f.id} f={f} picked={picked === f.id} onPick={() => setPicked(picked === f.id ? null : f.id)} />)}
        <p className="muted tdemo">Демо-данные: цены и расписание ориентировочные</p>
      </div>
    </>
  );
}

function Field({ icon, v, label, dim }: { icon: IconName; v: string; label?: string; dim?: boolean }) {
  return <div className={`fl__field glass ${dim ? "dim" : ""}`}><Icon name={icon} size={22} /><span>{label && <small>{label}</small>}<b>{v}</b></span></div>;
}

function FlightCard({ f, picked, onPick }: { f: Flight; picked: boolean; onPick: () => void }) {
  return (
    <article className="fc glass">
      <div className="fc__head"><span className="fc__logo" style={{ background: f.logoColor }}>{f.code}</span><b>{f.airline}</b><Icon name="chevron" size={18} /></div>
      <div className="fc__route">
        <div><b>{f.depart}</b><strong>{f.from}</strong><small>{f.fromCity}</small></div>
        <div className="fc__mid"><small>{f.duration}</small><div className="fc__line"><i /><i /><i /></div><small>{f.stops}</small></div>
        <div style={{ textAlign: "right" }}><b>{f.arrive}</b><strong>{f.to}</strong><small>{f.toCity}</small></div>
      </div>
      <div className="fc__opts">
        <span><Icon name="bag" size={20} /><small>Ручная кладь<br />{f.carryOn}</small></span>
        <span><Icon name="suitcase" size={20} /><small>Багаж<br />{f.baggage}</small></span>
        <span><Icon name="meal" size={20} /><small>Питание<br />{f.meal}</small></span>
      </div>
      <div className="fc__foot"><div><b>{money(f.pricePerPerson)}</b><small>на человека</small></div><button className={`btn btn--sm ${picked ? "" : ""}`} onClick={onPick} aria-pressed={picked}>{picked ? <>Выбрано <Icon name="check" size={18} /></> : "Выбрать"}</button></div>
    </article>
  );
}
