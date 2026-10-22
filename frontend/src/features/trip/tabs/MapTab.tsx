import { ComingSoon } from "../../../ui";
import type { Trip } from "../../../data/types";

export default function MapTab({ trip }: { trip: Trip }) {
  return <ComingSoon title={`Карта · ${trip.title}`} />;
}
