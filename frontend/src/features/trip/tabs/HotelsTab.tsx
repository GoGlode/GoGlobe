import { ComingSoon } from "../../../ui";
import type { Trip } from "../../../data/types";

export default function HotelsTab({ trip }: { trip: Trip }) {
  return <ComingSoon title={`Отели · ${trip.title}`} />;
}
