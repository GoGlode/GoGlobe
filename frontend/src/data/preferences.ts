// Предпочтения путешественника. В API-контракте v0 профиля и предпочтений нет — значения хранятся
// локально (state/ProfileContext.tsx). Списки — справочник для UI, а не данные пользователя.
import type { IconName } from "../ui";
import type { CabinClass } from "./flights";

const P = "/assets/photos/";

export const DIRECTIONS = [
  { id: "sea", label: "Море и пляжи", img: P + "maldives-cover.jpg" },
  { id: "culture", label: "Города и культура", img: P + "italy-cover.jpg" },
  { id: "nature", label: "Природа и горы", img: P + "georgia-cover.jpg" },
  { id: "food", label: "Гастрономия", img: P + "greece-3.jpg" },
  { id: "adventure", label: "Приключения", img: P + "turkey-cover.jpg" },
  { id: "family", label: "Семейные путешествия", img: P + "thailand-cover.jpg" },
] as const;
export const BUDGETS = [{ id: "economy", label: "Эконом" }, { id: "middle", label: "Средний" }, { id: "comfort", label: "Комфорт" }, { id: "premium", label: "Премиум" }] as const;
export const STYLES = [{ id: "solo", label: "Самостоятельно" }, { id: "family", label: "С семьёй" }, { id: "friends", label: "С друзьями" }, { id: "romantic", label: "Романтическое" }] as const;
export const STAYS = [{ id: "hotel", label: "Отели" }, { id: "apartment", label: "Апартаменты" }, { id: "boutique", label: "Бутик-отели" }, { id: "hostel", label: "Хостелы" }] as const;
export const CABIN_PREFS: readonly { id: CabinClass; label: string }[] = [{ id: "economy", label: "Эконом" }, { id: "comfort", label: "Комфорт" }, { id: "business", label: "Бизнес" }];
export const PACES = [{ id: "calm", label: "Спокойный" }, { id: "busy", label: "Насыщенный" }] as const;

export type DirectionId = (typeof DIRECTIONS)[number]["id"];
export interface TravelPrefs {
  directions: DirectionId[];
  budget?: (typeof BUDGETS)[number]["id"];
  style?: (typeof STYLES)[number]["id"];
  stay?: (typeof STAYS)[number]["id"];
  cabin?: CabinClass;
  pace?: (typeof PACES)[number]["id"];
}
export const EMPTY_PREFS: TravelPrefs = { directions: [] };

/** Строки краткой сводки предпочтений: [иконка, подпись, значение | null]. */
export function prefSummary(p: TravelPrefs): { icon: IconName; title: string; value: string | null }[] {
  const label = <T extends { id: string; label: string }>(list: readonly T[], id?: string) => list.find((x) => x.id === id)?.label ?? null;
  return [
    { icon: "wallet", title: "Бюджет", value: label(BUDGETS, p.budget) },
    { icon: "users", title: "Стиль", value: label(STYLES, p.style) },
    { icon: "bed", title: "Тип проживания", value: label(STAYS, p.stay) },
    { icon: "plane", title: "Класс перелёта", value: label(CABIN_PREFS, p.cabin) },
    { icon: "sun", title: "Темп путешествия", value: label(PACES, p.pace) },
  ];
}
