// Страница поездки: шапка + вкладки Обзор / Маршрут / Отели / Перелёты / Карта. Владелец: Frontend №2.
// Вкладка «Перелёты» — Frontend №1 (features/trip/tabs/FlightsTab.tsx).
import { Link, useParams } from "react-router-dom";
import { getTrip } from "../../data/trips";
import { useSearch } from "../../state/SearchContext";
import ApiTripPage from "./ApiTripPage";
import FlightsTab from "./tabs/FlightsTab";
import HotelsTab from "./tabs/HotelsTab";
import ItineraryTab from "./tabs/ItineraryTab";
import MapTab from "./tabs/MapTab";
import OverviewTab from "./tabs/OverviewTab";
import "./trip.css";

export default function TripPage() {
  const { id, tab = "overview" } = useParams();
  const { trips } = useSearch();
  // Демо-варианты выдачи (макеты) — прежний вид; любой другой id — настоящая поездка из API v0.3, которая грузится по URL и переживает reload
  const trip = trips.find((t) => t.id === id) ?? getTrip(id);
  if (!trip && id) return <ApiTripPage id={id} tab={(["overview", "itinerary", "hotels", "flights"] as const).find((x) => x === tab) ?? "overview"} />;
  if (!trip) return (
    <div className="page trip-missing">
      <h2>Вариант не найден</h2>
      <p className="muted">Повторите запрос — подборка соберётся заново.</p>
      <Link className="btn btn--sm" to="/">Найти путешествие</Link>
    </div>
  );
  const Tab = { overview: OverviewTab, itinerary: ItineraryTab, hotels: HotelsTab, flights: FlightsTab, map: MapTab }[tab] ?? OverviewTab;
  return <Tab trip={trip} />;
}
