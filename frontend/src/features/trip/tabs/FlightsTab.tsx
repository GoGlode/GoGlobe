import { ComingSoon } from "../../../ui";
import type { Trip } from "../../../data/types";

export default function FlightsTab({ trip }: { trip: Trip }) {
  return <ComingSoon title={`Перелёты · ${trip.title}`} />;
}
