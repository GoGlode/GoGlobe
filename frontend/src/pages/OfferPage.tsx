// Страница деталей варианта. Владелец: Frontend №2. TODO: карта, галерея, избранное, «поделиться».
import { Link, useParams } from "react-router-dom";
import { rub } from "../components/OfferCard";
import { useSearch } from "../state/SearchContext";

export default function OfferPage() {
  const { id } = useParams();
  const offer = useSearch().result?.offers.find((o) => o.id === id);
  if (!offer) return <p>Вариант не найден. <Link to="/results">К результатам</Link></p>;
  const ex = offer.explanation;
  return (
    <>
      <Link to="/results">← К результатам</Link>
      <h1>{offer.hotel.name}</h1>
      <p><strong>{rub(offer.total_price.amount)}</strong> · {offer.destination}</p>
      <div className="grid cols-2">
        <div className="card"><h3>Плюсы</h3><ul>{ex.pros.map((p) => <li key={p}>{p}</li>)}</ul></div>
        <div className="card"><h3>Минусы</h3><ul>{ex.cons.map((p) => <li key={p}>{p}</li>)}</ul></div>
      </div>
      <p className="muted">Источник: {ex.sources.join(", ")} · данные на {offer.data_freshness} · {ex.confidence === "confirmed" ? "подтверждено" : "оценка"}</p>
      <a className="btn" href={offer.booking_url} target="_blank" rel="noreferrer">Забронировать</a>
    </>
  );
}
