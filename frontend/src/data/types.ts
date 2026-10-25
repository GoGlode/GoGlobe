// Модель данных UI (то, что рисуют макеты). Пока наполняется моками (data/trips.ts);
// на этапе интеграции API-ответ (api/types.ts: Offer) приводится к Trip адаптером в data/api.ts.
import type { IconName } from "../ui";

export interface Money { amount: number; currency: string } // как в API-контракте; известные валюты форматируются в data/format.ts

export interface Hotel {
  id: string; city: string; name: string; rating?: number; reviews?: number; stars?: number; location: string;
  photo: string; photoPos?: string; amenities: { icon: IconName; label: string }[]; pricePerNight?: Money; priceNote?: string; tags: ("boutique" | "stars45" | "view")[];
}
export interface Flight {
  id: string; airline: string; code: string; logoColor: string; depart: string; arrive: string; from: string; fromCity: string;
  to: string; toCity: string; duration: string; stops: string; carryOn: string; baggage: string; meal: string; pricePerPerson: Money;
}
export interface ItineraryDay { day: number; date: string; title: string; photo: string; photoPos?: string; items: { icon: IconName; label: string }[] }
export interface Stop { city: string; days: string; photo: string; photoPos?: string; x: number; y: number }

/** Объяснение варианта — зеркало api/types.ts#Explanation. По контракту поля обязательны: так реализован принцип «ИИ ничего не выдумывает». */
export interface TripExplanation {
  why: string[]; pros: string[]; cons: string[]; sources: string[];
  /** confirmed — данные подтверждены источником; estimated — оценка */
  confidence: "confirmed" | "estimated";
}

export interface Trip {
  id: string; country: string; title: string; summary: string; why: string;
  days: number; dates: string; dateRange: [string, string]; travelers: number; price: Money;
  tags: { icon: IconName; label: string }[];
  hero: string; heroPos?: string; photos: { src: string; label: string; pos?: string }[];
  includes: { icon: IconName; title: string; sub: string }[];
  reasons: { icon: IconName; text: string }[];
  itinerary: ItineraryDay[]; hotels: Hotel[]; cities: string[]; flights: Flight[]; stops: Stop[];
  /** Из контракта (Offer): объяснение, свежесть данных, ссылка на бронирование. */
  explanation: TripExplanation;
  /** Offer.data_freshness — когда получены данные (ISO-дата/время) */
  dataFreshness: string;
  /** Offer.booking_url; у демо-данных его нет */
  bookingUrl?: string;
  /** Для фильтров выдачи: звёзды лучшего отеля и наличие прямого рейса */
  stars?: number; direct?: boolean;
  /** Демо-данные (не из API) */
  demo?: boolean;
  /** Подложка карты (public/assets/maps/*); нет — рисуется схематичная карта. Координаты остановок x/y — в процентах картинки */
  mapImage?: string;
}

export interface SearchParamsUI { dates?: string; travelers?: string; budget?: string }
