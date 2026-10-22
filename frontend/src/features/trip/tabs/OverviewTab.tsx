import { ComingSoon } from "../../../ui";
import type { Trip } from "../../../data/types";

export default function OverviewTab({ trip }: { trip: Trip }) {
  return <ComingSoon title={`Обзор · ${trip.title}`} />;
}
