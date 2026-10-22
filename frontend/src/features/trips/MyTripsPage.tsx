// Мои поездки: календарь месяца + предстоящие и прошедшие. Владелец: Frontend №1.
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { MY_TRIPS, TRIPS } from "../../data/trips";
import { Icon, PageHeader, Photo } from "../../ui";
import "./trips.css";

const MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];
const DOW = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
// Подсвечиваем только мои поездки: запланированные (Греция, Италия) и прошлую (Бали)
const RANGES: [string, string][] = [...TRIPS.filter((t) => ["greece", "italy"].includes(t.id)).map((t) => t.dateRange), ["2025-04-14", "2025-04-24"]];

const iso = (y: number, m: number, d: number) => `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;

export default function MyTripsPage() {
  const nav = useNavigate();
  const [ym, setYm] = useState({ y: 2025, m: 4 }); // макет: «Май 2025»
  const cells = useMemo(() => {
    const first = (new Date(ym.y, ym.m, 1).getDay() + 6) % 7;
    const total = new Date(ym.y, ym.m + 1, 0).getDate();
    const prevTotal = new Date(ym.y, ym.m, 0).getDate();
    const out: { d: number; cur: boolean; iso: string }[] = [];
    for (let i = first - 1; i >= 0; i--) out.push({ d: prevTotal - i, cur: false, iso: "" });
    for (let d = 1; d <= total; d++) out.push({ d, cur: true, iso: iso(ym.y, ym.m, d) });
    while (out.length % 7) out.push({ d: out.length - total - first + 1, cur: false, iso: "" });
    return out;
  }, [ym]);
  const step = (n: number) => setYm(({ y, m }) => { const x = m + n; return { y: y + Math.floor(x / 12), m: ((x % 12) + 12) % 12 }; });
  const inRange = (s: string) => RANGES.find(([a, b]) => s >= a && s <= b);

  return (
    <>
      <PageHeader title="Мои поездки" onBack={() => nav("/")} right={<Link to="/" className="circle-btn" aria-label="Новая поездка"><Icon name="plus" size={22} /></Link>} />
      <div className="page">
        <section className="cal glass" aria-label="Календарь">
          <div className="cal__head"><h2>{MONTHS[ym.m]} {ym.y}</h2><div className="row" style={{ gap: 8 }}>
            <button className="circle-btn" style={{ width: 38, height: 38 }} aria-label="Предыдущий месяц" onClick={() => step(-1)}><Icon name="chevron-left" size={18} /></button>
            <button className="circle-btn" style={{ width: 38, height: 38 }} aria-label="Следующий месяц" onClick={() => step(1)}><Icon name="chevron" size={18} /></button></div></div>
          <div className="cal__grid">
            {DOW.map((d) => <span key={d} className="cal__dow">{d}</span>)}
            {cells.map((c, i) => {
              const r = c.cur ? inRange(c.iso) : undefined;
              const start = r && c.iso === r[0], end = r && c.iso === r[1];
              return <span key={i} className={`cal__d ${c.cur ? "" : "off"} ${r ? "in" : ""} ${start ? "start" : ""} ${end ? "end" : ""}`}><i>{c.d}</i></span>;
            })}
          </div>
        </section>

        <h3 className="trips__h">Предстоящие поездки</h3>
        {MY_TRIPS.upcoming.map((t) => (
          <Link key={t.tripId} to={`/trip/${t.tripId}`} className="mt glass">
            <div className="mt__img"><Photo src={t.img} alt="" /></div>
            <div className="mt__txt"><b>{t.title}</b><small className="muted">{t.range}</small>
              {t.status === "prep" ? <span className="pill"><Icon name="clock" size={16} />Подготовка</span> : <span className="pill pill--ok"><Icon name="check" size={16} stroke={2.6} />Подтверждено</span>}</div>
            <Icon name="chevron" size={20} />
          </Link>
        ))}
        <h3 className="trips__h">Прошлые поездки</h3>
        {MY_TRIPS.past.map((t) => (
          <div key={t.tripId} className="mt glass">
            <div className="mt__img"><Photo src={t.img} alt="" /></div>
            <div className="mt__txt"><b>{t.title}</b><small className="muted">{t.range}</small></div><Icon name="chevron" size={20} />
          </div>
        ))}
        <p className="muted tdemo">Демо-данные</p>
      </div>
    </>
  );
}
