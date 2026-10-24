// Вкладка «Перелёты» поездки: экран поиска рейсов с параметрами поездки. Владелец: Frontend №1.
import type { Trip } from "../../../data/types";
import FlightsScreen from "../../flights/FlightsScreen";

export default function FlightsTab({ trip }: { trip: Trip }) {
  return <FlightsScreen trip={trip} />;
}
