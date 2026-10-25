// Страница поездки: шапка + вкладки Обзор / Маршрут / Отели / Перелёты / Карта. Владелец: Frontend №2.
// Вкладка «Перелёты» — Frontend №1 (features/trip/tabs/FlightsTab.tsx).
import { Link, useParams } from "react-router-dom";
import { getTrip } from "../../data/trips";
import { useSearch } from "../../state/SearchContext";
import FlightsTab from "./tabs/FlightsTab";
import HotelsTab from "./tabs/HotelsTab";
import ItineraryTab from "./tabs/ItineraryTab";
import MapTab from "./tabs/MapTab";
import OverviewTab from "./tabs/OverviewTab";
import "./trip.css";

export default function TripPage() {
  const { id, tab = "overview" } = useParams();
  const { trips } = useSearch();
  const trip = trips.find((t) => t.id === id) ?? getTrip(id); // варианты из ответа API живут только в текущем поиске
  if (!trip) return (
    <div className="page trip-missing">
      <h2>Вариант не найден</h2>
      <p className="muted">Он мог остаться в предыдущем поиске. Повторите запрос — подборка соберётся заново.</p>
      <Link className="btn btn--sm" to="/">Найти путешествие</Link>
    </div>
  );
  const Tab = { overview: OverviewTab, itinerary: ItineraryTab, hotels: HotelsTab, flights: FlightsTab, map: MapTab }[tab] ?? OverviewTab;
  return <Tab trip={trip} />;
}
