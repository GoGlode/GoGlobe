// Карточка варианта. Владелец: Frontend №2 (внешний вид — по макетам дизайнера).
import { Link } from "react-router-dom";
import type { Offer } from "../api/types";

export const rub = (n: number) => `${Math.round(n).toLocaleString("ru-RU")} ₽`;

export default function OfferCard({ offer }: { offer: Offer }) {
  const { hotel, flight, explanation: ex } = offer;
  return (
    <article className="card">
      {hotel.photos[0] && <img src={hotel.photos[0]} alt={hotel.name} style={{ width: "100%", borderRadius: 10 }} />}
      <h3 style={{ marginBottom: 4 }}>{hotel.name}{hotel.stars ? ` · ${hotel.stars}★` : ""}</h3>
      <div className="muted">{offer.destination}{hotel.rating ? ` · рейтинг ${hotel.rating}` : ""}</div>
      <p><strong style={{ fontSize: 22 }}>{rub(offer.total_price.amount)}</strong>{" "}
        <span className="muted">{flight.direct ? "прямой перелёт" : "с пересадкой"}</span></p>
      <div>{ex.why.map((w) => <span className="tag" key={w}>{w}</span>)}</div>
      <div style={{ display: "flex", gap: 8 }}>
        <Link className="btn" to={`/offers/${offer.id}`}>Подробнее</Link>
        <a className="btn secondary" href={offer.booking_url} target="_blank" rel="noreferrer">Забронировать</a>
      </div>
    </article>
  );
}
