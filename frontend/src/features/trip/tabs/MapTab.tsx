// Вкладка «Карта»: схематичная карта с остановками и список остановок. Владелец: Frontend №2.
// Карты в пакете дизайнера нет — рисуем стилизованную SVG-подложку; реальная карта подключается позже.
import { useNavigate } from "react-router-dom";
import type { Trip } from "../../../data/types";
import { Icon, PageHeader, Photo } from "../../../ui";
import TripTabs from "../TripTabs";

export default function MapTab({ trip: t }: { trip: Trip }) {
  const nav = useNavigate();
  const [a, b] = [t.stops[0], t.stops[1]];
  return (
    <>
      <PageHeader title="Карта" onBack={() => nav(`/trip/${t.id}`)} right={<span className="circle-btn"><Icon name="map" size={20} /></span>} />
      <TripTabs id={t.id} current="map" />
      <div className="map" role="img" aria-label={`Маршрут: ${t.stops.map((s) => s.city).join(" → ")}`}>
        <svg className="bg" viewBox="0 0 100 130" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
          <defs>
            <linearGradient id="sea" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#1e7fe8" /><stop offset="1" stopColor="#53b9ff" /></linearGradient>
            <filter id="soft"><feGaussianBlur stdDeviation="1.2" /></filter>
          </defs>
          <rect width="100" height="130" fill="url(#sea)" />
          <path d="M0 6 C14 2 26 14 30 30 C34 46 26 58 36 70 C44 80 30 96 40 112 L0 130Z" fill="#a9c488" />
          <path d="M0 10 C12 8 20 18 24 32 C27 44 20 56 28 66" fill="none" stroke="#d9e6b8" strokeWidth="1.4" opacity=".8" />
          <path d="M60 78 C66 74 72 80 70 86 C68 92 60 90 60 84Z" fill="#b9cf98" /><path d="M42 54 C46 52 50 56 48 60 C46 63 41 60 42 54Z" fill="#b9cf98" />
          <g fill="#fff" filter="url(#soft)" opacity=".7"><ellipse cx="86" cy="18" rx="16" ry="7" /><ellipse cx="94" cy="36" rx="12" ry="9" /><ellipse cx="90" cy="100" rx="14" ry="8" /></g>
        </svg>
        <svg className="bg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" style={{ height: "100%" }}>
          <path d={`M${a.x} ${a.y + 8} Q ${(a.x + b.x) / 2 + 18} ${(a.y + b.y) / 2 - 4} ${b.x} ${b.y - 6}`} fill="none" stroke="#fff" strokeWidth="0.9" strokeDasharray="2.2 2" strokeLinecap="round" vectorEffect="non-scaling-stroke" style={{ strokeWidth: 3 }} />
        </svg>
        {b && <span className="plane" style={{ left: `${(a.x + b.x) / 2 + 9}%`, top: `${(a.y + b.y) / 2 + 1}%` }}><Icon name="plane" size={22} style={{ transform: "rotate(45deg)" }} /></span>}
        {t.stops.map((s) => (
          <div className="pin" key={s.city} style={{ left: `${Math.min(s.x, 52)}%`, top: `${s.y}%` }}>
            <div className="pin__img"><Photo src={s.photo} pos={s.photoPos} alt={s.city} /></div>
            <div className="pin__lbl"><b>{s.city}</b><small>{s.days}</small></div>
          </div>
        ))}
      </div>
      <section className="stops glass">
        <h3>Остановки</h3>
        {t.stops.map((s) => (
          <div className="stop" key={s.city}>
            <div className="stop__img"><Photo src={s.photo} pos={s.photoPos} alt="" /></div>
            <span><b>{s.city}</b><small>{s.days}</small></span><Icon name="chevron" size={20} />
          </div>
        ))}
      </section>
    </>
  );
}
