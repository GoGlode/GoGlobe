// Страница поездки: шапка + вкладки Обзор / Маршрут / Отели / Перелёты / Карта. Владелец: Frontend №2.
// Вкладка «Перелёты» — Frontend №1 (features/trip/tabs/FlightsTab.tsx).
import { Link, useParams } from "react-router-dom";
import { getTrip } from "../../data/trips";
import FlightsTab from "./tabs/FlightsTab";
import HotelsTab from "./tabs/HotelsTab";
import ItineraryTab from "./tabs/ItineraryTab";
import MapTab from "./tabs/MapTab";
import OverviewTab from "./tabs/OverviewTab";
import "./trip.css";

export default function TripPage() {
  const { id, tab = "overview" } = useParams();
  const trip = getTrip(id);
  if (!trip) return <p className="page">Поездка не найдена. <Link to="/">На главную</Link></p>;
  const Tab = { overview: OverviewTab, itinerary: ItineraryTab, hotels: HotelsTab, flights: FlightsTab, map: MapTab }[tab] ?? OverviewTab;
  return <Tab trip={trip} />;
}
