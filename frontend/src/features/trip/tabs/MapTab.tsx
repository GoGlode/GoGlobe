// Вкладка «Карта»: схематичная карта с остановками и список остановок. Владелец: Frontend №2.
// Карты в пакете дизайнера нет — рисуем стилизованную SVG-подложку; реальная карта подключается позже.
import { useNavigate } from "react-router-dom";
import type { Trip } from "../../../data/types";
import { Icon, PageHeader, Photo } from "../../../ui";
import TripTabs from "../TripTabs";

export default function MapTab({ trip: t }: { trip: Trip }) {
  const nav = useNavigate();
  const [a, b] = [t.stops[0], t.stops[1]];
  const header = <PageHeader title="Карта" light onBack={() => nav(`/trip/${t.id}`)} right={<span className="circle-btn" style={{ color: "var(--c-navy)" }}><Icon name="map" size={20} /></span>} />;
  if (!a) return <><PageHeader title="Карта" onBack={() => nav(`/trip/${t.id}`)} /><TripTabs id={t.id} current="map" /><p className="page muted tl-empty">Точки маршрута пока недоступны: источники данных их не передали.</p></>;
  // Пунктир между двумя первыми остановками: квадратичная кривая, самолёт — в её середине
  const p0 = { x: a.x + 5, y: a.y + 4 }, p2 = { x: (b?.x ?? a.x) - 2, y: (b?.y ?? a.y) - 7 }, c = { x: (a.x + (b?.x ?? a.x)) / 2 + 10, y: (a.y + (b?.y ?? a.y)) / 2 - 6 };
  const mid = { x: .25 * p0.x + .5 * c.x + .25 * p2.x, y: .25 * p0.y + .5 * c.y + .25 * p2.y };
  return (
    <div className="map-screen">
      <div className="map" role="img" aria-label={`Маршрут: ${t.stops.map((s) => s.city).join(" → ")}`}>
        {header}
        {t.mapImage ? <img className="map__img" src={t.mapImage} alt="" aria-hidden="true" /> : <svg className="bg" viewBox="0 0 100 130" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
          <defs>
            <linearGradient id="sea" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#1e7fe8" /><stop offset="1" stopColor="#53b9ff" /></linearGradient>
            <filter id="soft"><feGaussianBlur stdDeviation="1.2" /></filter>
          </defs>
          <rect width="100" height="130" fill="url(#sea)" />
          <path d="M0 6 C14 2 26 14 30 30 C34 46 26 58 36 70 C44 80 30 96 40 112 L0 130Z" fill="#a9c488" />
          <path d="M0 10 C12 8 20 18 24 32 C27 44 20 56 28 66" fill="none" stroke="#d9e6b8" strokeWidth="1.4" opacity=".8" />
          <path d="M60 78 C66 74 72 80 70 86 C68 92 60 90 60 84Z" fill="#b9cf98" /><path d="M42 54 C46 52 50 56 48 60 C46 63 41 60 42 54Z" fill="#b9cf98" />
          <g fill="#fff" filter="url(#soft)" opacity=".7"><ellipse cx="86" cy="18" rx="16" ry="7" /><ellipse cx="94" cy="36" rx="12" ry="9" /><ellipse cx="90" cy="100" rx="14" ry="8" /></g>
        </svg>}
        {b && <svg className="bg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          <path d={`M${p0.x} ${p0.y} Q ${c.x} ${c.y} ${p2.x} ${p2.y}`} fill="none" stroke="#fff" strokeWidth="3.4" strokeDasharray="7 8" strokeLinecap="round" vectorEffect="non-scaling-stroke" style={{ filter: "drop-shadow(0 1px 2px rgba(0,40,100,.45))" }} />
        </svg>}
        {b && <span className="plane" style={{ left: `${mid.x}%`, top: `${mid.y}%` }}><Icon name="plane" size={22} style={{ transform: "rotate(45deg)" }} /></span>}
        {t.stops.map((s) => (
          <div className={`pin ${s.x > 55 ? "pin--below" : ""}`} key={s.city} style={{ left: `${s.x}%`, top: `${s.y}%` }}>
            <div className="pin__img"><Photo src={s.photo} pos={s.photoPos} alt={s.city} /></div>
            <div className="pin__lbl"><b>{s.city}</b><small>{s.days}</small></div>
          </div>
        ))}
      </div>
      <section className="tsheet map-sheet">
        <TripTabs id={t.id} current="map" />
        <h3>Остановки</h3>
        {t.stops.map((s) => (
          <div className="stop" key={s.city}>
            <div className="stop__img"><Photo src={s.photo} pos={s.photoPos} alt="" /></div>
            <span><b>{s.city}</b><small>{s.days}</small></span><Icon name="chevron" size={20} />
          </div>
        ))}
      </section>
    </div>
  );
}
