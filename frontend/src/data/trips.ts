// Демо-данные по макетам дизайнера. Это НЕ реальные предложения: цены, рейтинги и фото — концепт.
// Реальные данные придут с backend (см. docs/api-contract.md) через адаптер в data/api.ts.
import type { Flight, Hotel, Trip } from "./types";

const IMG = "/assets/photos/"; // Wikimedia Commons, авторы — data/photoCredits.ts
/** Дата «снимка» демо-данных — показывается как «данные от …». */
const DEMO_DATE = "2025-04-28T10:00:00Z";
const usd = (amount: number) => ({ amount, currency: "USD" as const });

const flights: Flight[] = [
  { id: "f1", airline: "Aegean Airlines", code: "A3", logoColor: "#102448", depart: "10:25", arrive: "14:40", from: "SVO", fromCity: "Москва", to: "ATH", toCity: "Афины",
    duration: "4ч 15м", stops: "Прямой", carryOn: "8 кг", baggage: "23 кг", meal: "включено", pricePerPerson: usd(320) },
  { id: "f2", airline: "Turkish Airlines", code: "TK", logoColor: "#e30a17", depart: "08:50", arrive: "15:20", from: "SVO", fromCity: "Москва", to: "ATH", toCity: "Афины",
    duration: "6ч 30м", stops: "1 пересадка (IST)", carryOn: "8 кг", baggage: "23 кг", meal: "включено", pricePerPerson: usd(290) },
];

const hotels: Hotel[] = [
  { id: "h1", city: "Санторини", name: "Katikies Hotel", rating: 4.8, reviews: 320, location: "Ойя, Санторини", photo: IMG + "hero.jpg",
    amenities: [{ icon: "coffee", label: "Завтрак" }, { icon: "pool", label: "Бассейн" }, { icon: "wifi", label: "Wi-Fi" }], pricePerNight: usd(320), tags: ["stars45", "view"] },
  { id: "h2", city: "Санторини", name: "Canaves Oia Suites", rating: 4.7, reviews: 180, location: "Ойя, Санторини", photo: IMG + "greece-cover.jpg",
    amenities: [{ icon: "coffee", label: "Завтрак" }, { icon: "view", label: "Вид на кальдеру" }, { icon: "spa", label: "Спа" }], pricePerNight: usd(280), tags: ["stars45", "view"] },
  { id: "h3", city: "Санторини", name: "Andronis Boutique", rating: 4.6, reviews: 142, location: "Фира, Санторини", photo: IMG + "greece-3.jpg",
    amenities: [{ icon: "coffee", label: "Завтрак" }, { icon: "pool", label: "Бассейн" }, { icon: "spa", label: "Спа" }], pricePerNight: usd(250), tags: ["boutique"] },
  { id: "h4", city: "Афины", name: "Electra Palace Athens", rating: 4.6, reviews: 410, location: "Плака, Афины", photo: IMG + "greece-2.jpg",
    amenities: [{ icon: "coffee", label: "Завтрак" }, { icon: "view", label: "Вид на Акрополь" }, { icon: "wifi", label: "Wi-Fi" }], pricePerNight: usd(190), tags: ["stars45", "view"] },
  { id: "h5", city: "Афины", name: "Niche Hotel", rating: 4.5, reviews: 215, location: "Монастираки, Афины", photo: IMG + "greece-4.jpg",
    amenities: [{ icon: "coffee", label: "Завтрак" }, { icon: "wifi", label: "Wi-Fi" }], pricePerNight: usd(120), tags: ["boutique"] },
];

const greece: Trip = {
  id: "greece", country: "Греция", title: "Греция: Санторини и Афины",
  summary: "Идеальное сочетание пляжного отдыха, живописной природы, истории и средиземноморской кухни.",
  why: "Вы хотели пляжи, природу и комфортный бюджет. Санторини даёт уникальные виды и атмосферу, а Афины добавляют культурные впечатления, при этом маршрут укладывается в ваш бюджет.",
  days: 7, dates: "12 – 18 мая 2025", dateRange: ["2025-05-12", "2025-05-18"], travelers: 2, price: usd(1290),
  tags: [{ icon: "waves", label: "Пляжи" }, { icon: "landmark", label: "Культура" }, { icon: "leaf", label: "Природа" }, { icon: "utensils", label: "Гастрономия" }],
  hero: IMG + "hero.jpg",
  photos: [{ src: IMG + "greece-1.jpg", label: "Ойя ночью" }, { src: IMG + "greece-2.jpg", label: "Закат в Ойе" }, { src: IMG + "greece-3.jpg", label: "Фира" }, { src: IMG + "greece-4.jpg", label: "Пиргос" }],
  includes: [{ icon: "plane", title: "Перелёты", sub: "включены" }, { icon: "bed", title: "Отели", sub: "4–5★" }, { icon: "car", title: "Трансферы", sub: "включены" }],
  reasons: [{ icon: "sparkle", text: "Идеальное сочетание моря и культуры" }, { icon: "leaf", text: "Живописные локации и атмосферные городки" }, { icon: "wallet", text: "Комфортный бюджет" }],
  itinerary: [
    { day: 1, date: "12 мая", title: "Прибытие в Афины", photo: IMG + "greece-2.jpg", items: [{ icon: "plane", label: "Прибытие и трансфер" }, { icon: "bed", label: "Заселение в отель" }, { icon: "search", label: "Вечерняя прогулка" }] },
    { day: 2, date: "13 мая", title: "Афины: история и культура", photo: IMG + "greece-cover.jpg", items: [{ icon: "landmark", label: "Акрополь" }, { icon: "pin", label: "Прогулка по Плаке" }, { icon: "utensils", label: "Ужин в традиционной таверне" }] },
    { day: 3, date: "14 мая", title: "Переезд на Санторини", photo: IMG + "hero.jpg", items: [{ icon: "plane", label: "Перелёт на Санторини" }, { icon: "bed", label: "Заселение в отель" }, { icon: "heart", label: "Вечер в Ойе" }] },
    { day: 4, date: "15 мая", title: "Отдых на Санторини", photo: IMG + "greece-1.jpg", items: [{ icon: "waves", label: "Пляж Периссы" }, { icon: "coffee", label: "Поздний завтрак" }, { icon: "sun", label: "Закат в Ойе" }] },
    { day: 5, date: "16 мая", title: "Кальдера и винные погреба", photo: IMG + "greece-3.jpg", items: [{ icon: "view", label: "Тропа Фира — Ойя" }, { icon: "utensils", label: "Дегустация вин" }] },
    { day: 6, date: "17 мая", title: "Свободный день", photo: IMG + "greece-4.jpg", items: [{ icon: "spa", label: "Спа в отеле" }, { icon: "pin", label: "Прогулка по Фире" }] },
    { day: 7, date: "18 мая", title: "Вылет домой", photo: IMG + "greece-2.jpg", items: [{ icon: "car", label: "Трансфер в аэропорт" }, { icon: "plane", label: "Перелёт домой" }] },
  ],
  explanation: {
    why: ["Вы хотели пляжи, природу и комфортный бюджет", "Санторини даёт виды и атмосферу, Афины — культурные впечатления", "Маршрут укладывается в бюджет"],
    pros: ["Прямой рейс из Москвы", "Отели 4–5★ с завтраком", "Тёплое море и мало дождей в мае"],
    cons: ["Высокий сезон на Санторини — цены выше", "Переезд между островами зависит от погоды"],
    sources: ["Демо-данные GoGlobe"], confidence: "estimated",
  },
  dataFreshness: DEMO_DATE, demo: true,
  hotels, cities: ["Афины", "Санторини"], flights,
  stops: [{ city: "Афины", days: "Дни 1–3", photo: IMG + "greece-2.jpg", x: 30, y: 17 }, { city: "Санторини", days: "Дни 4–7", photo: IMG + "hero.jpg", x: 68, y: 60 }],
};

/** Короткая фабрика для остальных вариантов выдачи (в макетах детализированы только Санторини и Афины). */
function lite(p: { id: string; country: string; title: string; summary: string; why: string; days: number; dates: string; range: [string, string]; price: number; img: string; city: string; place: string }): Trip {
  const h: Hotel[] = [
    { id: `${p.id}-h1`, city: p.city, name: `${p.city} Grand Resort`, rating: 4.7, reviews: 210, location: p.place, photo: p.img, amenities: [{ icon: "coffee", label: "Завтрак" }, { icon: "pool", label: "Бассейн" }, { icon: "wifi", label: "Wi-Fi" }], pricePerNight: usd(210), tags: ["stars45"] },
    { id: `${p.id}-h2`, city: p.city, name: `${p.city} Boutique`, rating: 4.5, reviews: 96, location: p.place, photo: IMG + `${p.id}-2.jpg`, amenities: [{ icon: "coffee", label: "Завтрак" }, { icon: "spa", label: "Спа" }], pricePerNight: usd(160), tags: ["boutique"] },
  ];
  return {
    ...greece, id: p.id, country: p.country, title: p.title, summary: p.summary, why: p.why,
    explanation: { why: [p.why], pros: [`${p.days} дней в рамках бюджета`, "Отели 4–5★ в выдаче"], cons: ["Подробный маршрут уточняется"], sources: ["Демо-данные GoGlobe"], confidence: "estimated" }, days: p.days, dates: p.dates, dateRange: p.range, price: usd(p.price),
    hero: p.img, photos: [1, 2, 3, 4].map((n, i) => ({ src: IMG + `${p.id}-${n}.jpg`, label: i === 0 ? p.city : ["Главные места", "Природа", "Виды"][i - 1] })),
    itinerary: greece.itinerary.slice(0, 4).map((d, i) => ({ ...d, photo: i === 0 ? p.img : IMG + `${p.id}-${i}.jpg` })), hotels: h, cities: [p.city], flights: [flights[0]],
    stops: [{ city: p.city, days: `Дни 1–${p.days}`, photo: p.img, x: 50, y: 40 }],
  };
}

const BASE: Trip[] = [
  greece,
  lite({ id: "thailand", country: "Таиланд", title: "Таиланд: Пхукет и Краби", summary: "Пляжи, тропическая природа и расслабленный отдых у тёплого моря.", why: "Тёплое море и пляжи в рамках бюджета; много природы и спокойных локаций.", days: 8, dates: "10 – 17 мая 2025", range: ["2025-05-10", "2025-05-17"], price: 1240, img: IMG + "thailand-cover.jpg", city: "Пхукет", place: "Карон, Пхукет" }),
  lite({ id: "italy", country: "Италия", title: "Италия: Рим и Амальфи", summary: "История Рима и побережье Амальфи: культура, гастрономия и море.", why: "Сочетание культуры и гастрономии с отдыхом у моря; маршрут укладывается в бюджет.", days: 8, dates: "3 – 10 июня 2025", range: ["2025-06-03", "2025-06-10"], price: 1380, img: IMG + "italy-cover.jpg", city: "Амальфи", place: "Амальфи" }),
  lite({ id: "japan", country: "Япония", title: "Япония: Токио и Киото", summary: "Современные кварталы Токио и древние храмы Киото.", why: "Культурная программа и природа, вы просили необычный маршрут.", days: 9, dates: "14 – 22 мая 2025", range: ["2025-05-14", "2025-05-22"], price: 1490, img: IMG + "japan-cover.jpg", city: "Киото", place: "Гион, Киото" }),
  lite({ id: "bali", country: "Индонезия", title: "Бали: Убуд и побережье", summary: "Храмы на воде, рисовые террасы и закаты над океаном.", why: "Природа и культура в одной поездке, тёплый океан и много вариантов жилья в рамках бюджета.", days: 9, dates: "8 – 16 мая 2025", range: ["2025-05-08", "2025-05-16"], price: 1350, img: IMG + "bali-cover.jpg", city: "Убуд", place: "Убуд, Бали" }),
];

/** Звёзды лучшего отеля и прямой рейс — для фильтров выдачи (у реальных данных приходят из Offer). */
const STARS: Record<string, number> = { greece: 5, thailand: 4, italy: 5, japan: 4, bali: 5 };
const LONG_HAUL = ["japan", "bali"]; // пересадка в демо
export const TRIPS: Trip[] = BASE.map((t) => ({ ...t, stars: STARS[t.id], direct: !LONG_HAUL.includes(t.id) }));

export const getTrip = (id?: string) => TRIPS.find((t) => t.id === id);

export const DESTINATIONS = [
  { id: "greece", name: "Греция", sub: "Море, культура, история", img: IMG + "greece-cover.jpg", query: "Хочу неделю на Санторини: море, закаты и красивые виды" },
  { id: "thailand", name: "Таиланд", sub: "Пляжи, природа, отдых", img: IMG + "thailand-cover.jpg", query: "Хочу 10 дней в Таиланде: тёплое море, острова и пляжи" },
  { id: "italy", name: "Италия", sub: "Культура, гастрономия", img: IMG + "italy-cover.jpg", query: "Хочу неделю в Италии у моря: цветные городки и вкусная еда" },
  { id: "japan", name: "Япония", sub: "Традиции и технологии", img: IMG + "japan-cover.jpg", query: "Хочу 8 дней в Японии весной: Токио, Киото, Фудзи и сакура" },
  { id: "bali", name: "Бали", sub: "Острова, храмы, сёрфинг", img: IMG + "bali-cover.jpg", query: "Хочу 10 дней на Бали: храмы, рисовые террасы и океан" },
  { id: "turkey", name: "Турция", sub: "Каппадокия и Анталья", img: IMG + "turkey-cover.jpg", query: "Хочу на неделю в Турцию: полёт на шаре в Каппадокии и море в Анталье" },
  { id: "maldives", name: "Мальдивы", sub: "Виллы над водой", img: IMG + "maldives-cover.jpg", query: "Хочу 7 дней на Мальдивах вдвоём: вилла над водой и снорклинг" },
  { id: "georgia", name: "Грузия", sub: "Горы и Тбилиси", img: IMG + "georgia-cover.jpg", query: "Хочу 6 дней в Грузии: Тбилиси, горы Казбеги и вино" },
];

/** Поездки пользователя для «Мои поездки». ДЕМО: даты считаются от сегодняшнего дня, статусы — тестовые. */
export interface MyTrip { tripId: string; title: string; start: string; end: string; status?: "prep" | "confirmed"; img: string }

function isoFromToday(days: number): string {
  const d = new Date();
  d.setHours(12, 0, 0, 0);
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export const MY_TRIPS: MyTrip[] = [
  { tripId: "italy", title: "Италия: Рим и Амальфи", start: isoFromToday(42), end: isoFromToday(49), status: "confirmed", img: IMG + "italy-cover.jpg" },
  { tripId: "greece", title: "Санторини и Афины", start: isoFromToday(20), end: isoFromToday(26), status: "prep", img: IMG + "hero.jpg" },
  { tripId: "bali", title: "Бали", start: isoFromToday(-190), end: isoFromToday(-180), img: IMG + "bali-cover.jpg" },
];
