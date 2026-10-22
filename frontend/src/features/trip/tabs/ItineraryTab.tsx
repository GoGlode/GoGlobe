import { ComingSoon } from "../../../ui";
import type { Trip } from "../../../data/types";

export default function ItineraryTab({ trip }: { trip: Trip }) {
  return <ComingSoon title={`Маршрут · ${trip.title}`} />;
}
