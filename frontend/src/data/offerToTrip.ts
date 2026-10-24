// Адаптер контракта: Offer (api/types.ts, docs/api-contract.md) → Trip (модель UI, data/types.ts).
// Только то, что реально пришло из API: ничего не додумываем. Чего нет (маршрут по дням, точки на карте, время рейса, рейтинг отеля) —
// остаётся пустым/необязательным, а экраны показывают честную заглушку.
import type { Offer, ParsedQuery } from "../api/types";
import { dateRange } from "./format";
import type { Trip } from "./types";

const DAY = 86_400_000;
const day = (s: string) => Date.parse(`${s}T00:00:00Z`);

export function offerToTrip(o: Offer, parsed?: Pick<ParsedQuery, "travelers">): Trip {
  const { hotel: h, flight: f, explanation: e } = o;
  const days = Math.max(1, Math.round((day(f.dates.to) - day(f.dates.from)) / DAY) || 1);
  const photos = (h.photos ?? []).filter(Boolean);
  const toSea = h.distance_to_sea_m;
  return {
    id: o.id, country: o.destination, title: o.destination,
    summary: [h.name, h.stars ? `${h.stars}★` : null, toSea != null ? `${toSea} м до моря` : null].filter(Boolean).join(" · "),
    why: e.why.join(" "),
    days, dates: dateRange(f.dates.from, f.dates.to), dateRange: [f.dates.from, f.dates.to], travelers: parsed?.travelers ?? 2, price: o.total_price,
    tags: [
      ...(f.direct ? [{ icon: "plane" as const, label: "Прямой рейс" }] : []),
      ...(toSea != null && toSea <= 500 ? [{ icon: "waves" as const, label: "У моря" }] : []),
      ...(h.stars && h.stars >= 4 ? [{ icon: "star" as const, label: `Отель ${h.stars}★` }] : []),
    ],
    hero: photos[0] ?? "", photos: photos.map((src, i) => ({ src, label: `${h.name} — фото ${i + 1}` })),
    includes: [
      { icon: "plane", title: "Перелёт", sub: f.direct ? "прямой" : "с пересадкой" },
      { icon: "bed", title: "Отель", sub: h.stars ? `${h.stars}★` : "без категории" },
    ],
    reasons: e.why.map((text) => ({ icon: "sparkle" as const, text })),
    itinerary: [], cities: [o.destination], stops: [],
    hotels: [{
      id: `${o.id}-hotel`, city: o.destination, name: h.name, rating: h.rating ?? undefined, stars: h.stars ?? undefined, location: o.destination,
      photo: photos[0] ?? "", amenities: toSea != null ? [{ icon: "waves", label: `${toSea} м до моря` }] : [], tags: [],
      // Контракт не уточняет, цена отеля за ночь или за весь срок — показываем как есть, без слов «за ночь» (вопрос к Backend, см. PR).
      // Нет цены отеля — не подставляем общую стоимость поездки: это было бы ложью.
      pricePerNight: h.price ?? undefined, priceNote: "цена по данным источника",
    }],
    flights: [{
      id: `${o.id}-flight`, airline: f.carrier ?? "Авиакомпания не указана", code: "", logoColor: "#6b7a96", depart: "—", arrive: "—", from: "", fromCity: "", to: "", toCity: "",
      duration: "—", stops: f.direct ? "Прямой" : "С пересадкой", carryOn: "—", baggage: "—", meal: "—", pricePerPerson: f.price ?? o.total_price,
    }],
    explanation: { why: e.why, pros: e.pros, cons: e.cons, sources: e.sources, confidence: e.confidence },
    dataFreshness: o.data_freshness, bookingUrl: o.booking_url || undefined,
    stars: h.stars ?? undefined, direct: f.direct,
  };
}
