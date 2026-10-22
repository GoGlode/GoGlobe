// Демо-данные по макетам дизайнера. Это НЕ реальные предложения: цены, рейтинги и фото — концепт.
// Реальные данные придут с backend (см. docs/api-contract.md) через адаптер в data/api.ts.
import type { Flight, Hotel, Trip } from "./types";

const IMG = "/assets/images/";
const usd = (amount: number) => ({ amount, currency: "USD" as const });

const flights: Flight[] = [
  { id: "f1", airline: "Aegean Airlines", code: "A3", logoColor: "#102448", depart: "10:25", arrive: "14:40", from: "SVO", fromCity: "Москва", to: "ATH", toCity: "Афины",
    duration: "4ч 15м", stops: "Прямой", carryOn: "8 кг", baggage: "23 кг", meal: "включено", pricePerPerson: usd(320) },
  { id: "f2", airline: "Turkish Airlines", code: "TK", logoColor: "#e30a17", depart: "08:50", arrive: "15:20", from: "SVO", fromCity: "Москва", to: "ATH", toCity: "Афины",
    duration: "6ч 30м", stops: "1 пересадка (IST)", carryOn: "8 кг", baggage: "23 кг", meal: "включено", pricePerPerson: usd(290) },
];

const hotels: Hotel[] = [
  { id: "h1", city: "Санторини", name: "Katikies Hotel", rating: 4.8, reviews: 320, location: "Ойя, Санторини", photo: IMG + "hero-santorini.jpg", photoPos: "20% 60%",
    amenities: [{ icon: "coffee", label: "Завтрак" }, { icon: "pool", label: "Бассейн" }, { icon: "wifi", label: "Wi-Fi" }], pricePerNight: usd(320), tags: ["stars45", "view"] },
  { id: "h2", city: "Санторини", name: "Canaves Oia Suites", rating: 4.7, reviews: 180, location: "Ойя, Санторини", photo: IMG + "dest-greece.jpg", photoPos: "50% 70%",
    amenities: [{ icon: "coffee", label: "Завтрак" }, { icon: "view", label: "Вид на кальдеру" }, { icon: "spa", label: "Спа" }], pricePerNight: usd(280), tags: ["stars45", "view"] },
  { id: "h3", city: "Санторини", name: "Andronis Boutique", rating: 4.6, reviews: 142, location: "Фира, Санторини", photo: IMG + "dest-italy.jpg", photoPos: "50% 40%",
    amenities: [{ icon: "coffee", label: "Завтрак" }, { icon: "pool", label: "Бассейн" }, { icon: "spa", label: "Спа" }], pricePerNight: usd(250), tags: ["boutique"] },
  { id: "h4", city: "Афины", name: "Electra Palace Athens", rating: 4.6, reviews: 410, location: "Плака, Афины", photo: IMG + "dest-greece.jpg", photoPos: "10% 30%",
    amenities: [{ icon: "coffee", label: "Завтрак" }, { icon: "view", label: "Вид на Акрополь" }, { icon: "wifi", label: "Wi-Fi" }], pricePerNight: usd(190), tags: ["stars45", "view"] },
  { id: "h5", city: "Афины", name: "Niche Hotel", rating: 4.5, reviews: 215, location: "Монастираки, Афины", photo: IMG + "dest-france.jpg", photoPos: "50% 50%",
    amenities: [{ icon: "coffee", label: "Завтрак" }, { icon: "wifi", label: "Wi-Fi" }], pricePerNight: usd(120), tags: ["boutique"] },
];

const greece: Trip = {
  id: "greece", country: "Греция", title: "Греция: Санторини и Афины",
  summary: "Идеальное сочетание пляжного отдыха, живописной природы, истории и средиземноморской кухни.",
  why: "Вы хотели пляжи, природу и комфортный бюджет. Санторини даёт уникальные виды и атмосферу, а Афины добавляют культурные впечатления, при этом маршрут укладывается в ваш бюджет.",
  days: 7, dates: "12 – 18 мая 2025", dateRange: ["2025-05-12", "2025-05-18"], travelers: 2, price: usd(1290),
  tags: [{ icon: "waves", label: "Пляжи" }, { icon: "landmark", label: "Культура" }, { icon: "leaf", label: "Природа" }, { icon: "utensils", label: "Гастрономия" }],
  hero: IMG + "hero-santorini.jpg", heroPos: "50% 40%",
  photos: [{ src: IMG + "dest-greece.jpg", label: "Санторини" }, { src: IMG + "dest-greece.jpg", label: "Афины", pos: "0% 20%" }, { src: IMG + "hero-santorini.jpg", label: "Ойя", pos: "80% 60%" }, { src: IMG + "dest-italy.jpg", label: "Фира" }],
  includes: [{ icon: "plane", title: "Перелёты", sub: "включены" }, { icon: "bed", title: "Отели", sub: "4–5★" }, { icon: "car", title: "Трансферы", sub: "включены" }],
  reasons: [{ icon: "sparkle", text: "Идеальное сочетание моря и культуры" }, { icon: "leaf", text: "Живописные локации и атмосферные городки" }, { icon: "wallet", text: "Комфортный бюджет" }],
  itinerary: [
    { day: 1, date: "12 мая", title: "Прибытие в Афины", photo: IMG + "dest-greece.jpg", photoPos: "0% 20%", items: [{ icon: "plane", label: "Прибытие и трансфер" }, { icon: "bed", label: "Заселение в отель" }, { icon: "search", label: "Вечерняя прогулка" }] },
    { day: 2, date: "13 мая", title: "Афины: история и культура", photo: IMG + "dest-greece.jpg", photoPos: "0% 10%", items: [{ icon: "landmark", label: "Акрополь" }, { icon: "pin", label: "Прогулка по Плаке" }, { icon: "utensils", label: "Ужин в традиционной таверне" }] },
    { day: 3, date: "14 мая", title: "Переезд на Санторини", photo: IMG + "hero-santorini.jpg", photoPos: "50% 50%", items: [{ icon: "plane", label: "Перелёт на Санторини" }, { icon: "bed", label: "Заселение в отель" }, { icon: "heart", label: "Вечер в Ойе" }] },
    { day: 4, date: "15 мая", title: "Отдых на Санторини", photo: IMG + "dest-greece.jpg", photoPos: "60% 80%", items: [{ icon: "waves", label: "Пляж Периссы" }, { icon: "coffee", label: "Поздний завтрак" }, { icon: "sun", label: "Закат в Ойе" }] },
    { day: 5, date: "16 мая", title: "Кальдера и винные погреба", photo: IMG + "hero-santorini.jpg", photoPos: "90% 30%", items: [{ icon: "view", label: "Тропа Фира — Ойя" }, { icon: "utensils", label: "Дегустация вин" }] },
    { day: 6, date: "17 мая", title: "Свободный день", photo: IMG + "dest-greece.jpg", photoPos: "30% 60%", items: [{ icon: "spa", label: "Спа в отеле" }, { icon: "pin", label: "Прогулка по Фире" }] },
    { day: 7, date: "18 мая", title: "Вылет домой", photo: IMG + "hero-santorini.jpg", photoPos: "10% 50%", items: [{ icon: "car", label: "Трансфер в аэропорт" }, { icon: "plane", label: "Перелёт домой" }] },
  ],
  hotels, cities: ["Афины", "Санторини"], flights,
  stops: [{ city: "Афины", days: "Дни 1–3", photo: IMG + "dest-greece.jpg", photoPos: "0% 20%", x: 30, y: 17 }, { city: "Санторини", days: "Дни 4–7", photo: IMG + "hero-santorini.jpg", x: 68, y: 60 }],
};

/** Короткая фабрика для остальных вариантов выдачи (в макетах детализированы только Санторини и Афины). */
function lite(p: { id: string; country: string; title: string; summary: string; why: string; days: number; dates: string; range: [string, string]; price: number; img: string; pos?: string; city: string; place: string }): Trip {
  const h: Hotel[] = [
    { id: `${p.id}-h1`, city: p.city, name: `${p.city} Grand Resort`, rating: 4.7, reviews: 210, location: p.place, photo: p.img, photoPos: p.pos, amenities: [{ icon: "coffee", label: "Завтрак" }, { icon: "pool", label: "Бассейн" }, { icon: "wifi", label: "Wi-Fi" }], pricePerNight: usd(210), tags: ["stars45"] },
    { id: `${p.id}-h2`, city: p.city, name: `${p.city} Boutique`, rating: 4.5, reviews: 96, location: p.place, photo: p.img, photoPos: "30% 40%", amenities: [{ icon: "coffee", label: "Завтрак" }, { icon: "spa", label: "Спа" }], pricePerNight: usd(160), tags: ["boutique"] },
  ];
  return {
    ...greece, id: p.id, country: p.country, title: p.title, summary: p.summary, why: p.why, days: p.days, dates: p.dates, dateRange: p.range, price: usd(p.price),
    hero: p.img, heroPos: p.pos, photos: [{ src: p.img, label: p.city, pos: p.pos }, { src: p.img, label: "Главные места", pos: "20% 30%" }, { src: p.img, label: "Отели", pos: "70% 60%" }, { src: p.img, label: "Природа", pos: "50% 80%" }],
    itinerary: greece.itinerary.slice(0, 4).map((d) => ({ ...d, photo: p.img })), hotels: h, cities: [p.city], flights: [flights[0]],
    stops: [{ city: p.city, days: `Дни 1–${p.days}`, photo: p.img, photoPos: p.pos, x: 50, y: 40 }],
  };
}

export const TRIPS: Trip[] = [
  greece,
  lite({ id: "thailand", country: "Таиланд", title: "Таиланд: Пхукет и Краби", summary: "Пляжи, тропическая природа и расслабленный отдых у тёплого моря.", why: "Тёплое море и пляжи в рамках бюджета; много природы и спокойных локаций.", days: 8, dates: "10 – 17 мая 2025", range: ["2025-05-10", "2025-05-17"], price: 1240, img: IMG + "dest-thailand.jpg", city: "Пхукет", place: "Карон, Пхукет" }),
  lite({ id: "italy", country: "Италия", title: "Италия: Рим и Амальфи", summary: "История Рима и побережье Амальфи: культура, гастрономия и море.", why: "Сочетание культуры и гастрономии с отдыхом у моря; маршрут укладывается в бюджет.", days: 8, dates: "3 – 10 июня 2025", range: ["2025-06-03", "2025-06-10"], price: 1380, img: IMG + "dest-italy.jpg", city: "Амальфи", place: "Амальфи" }),
  lite({ id: "japan", country: "Япония", title: "Япония: Токио и Киото", summary: "Современные кварталы Токио и древние храмы Киото.", why: "Культурная программа и природа, вы просили необычный маршрут.", days: 9, dates: "14 – 22 мая 2025", range: ["2025-05-14", "2025-05-22"], price: 1490, img: IMG + "dest-japan.jpg", city: "Киото", place: "Гион, Киото" }),
  lite({ id: "france", country: "Франция", title: "Франция: Париж и Ницца", summary: "Музеи и кафе Парижа, затем Лазурный берег.", why: "Гастрономия и культура плюс пляжный отдых в конце поездки.", days: 7, dates: "12 – 18 мая 2025", range: ["2025-05-12", "2025-05-18"], price: 1460, img: IMG + "dest-france.jpg", city: "Ницца", place: "Променад дез Англе, Ницца" }),
];

export const getTrip = (id?: string) => TRIPS.find((t) => t.id === id);

export const DESTINATIONS = [
  { id: "greece", name: "Греция", sub: "Море, культура, история", img: IMG + "dest-greece.jpg" },
  { id: "thailand", name: "Таиланд", sub: "Пляжи, природа, отдых", img: IMG + "dest-thailand.jpg" },
  { id: "italy", name: "Италия", sub: "Культура, гастрономия", img: IMG + "dest-italy.jpg" },
  { id: "japan", name: "Япония", sub: "Традиции и технологии", img: IMG + "dest-japan.jpg" },
  { id: "france", name: "Франция", sub: "Города и побережье", img: IMG + "dest-france.jpg" },
  { id: "bali", name: "Бали", sub: "Острова, храмы, сёрфинг", img: IMG + "dest-bali.jpg" },
];

export const MY_TRIPS = {
  upcoming: [
    { tripId: "greece", title: "Санторини и Афины", range: "12 — 18 мая 2025 · 7 дней", status: "prep" as const, img: IMG + "hero-santorini.jpg" },
    { tripId: "italy", title: "Италия: Рим и Амальфи", range: "3 — 10 июня 2025 · 8 дней", status: "confirmed" as const, img: IMG + "dest-italy.jpg" },
  ],
  past: [{ tripId: "bali", title: "Бали", range: "14 — 24 апреля 2025", img: IMG + "dest-bali.jpg" }],
};
