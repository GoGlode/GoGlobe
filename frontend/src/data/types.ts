// Модель данных UI (то, что рисуют макеты). Пока наполняется моками (data/trips.ts);
// на этапе интеграции API-ответ (api/types.ts: Offer) приводится к Trip адаптером в data/api.ts.
import type { IconName } from "../ui";

export interface Money { amount: number; currency: "USD" | "RUB" | "EUR" }

export interface Hotel {
  id: string; city: string; name: string; rating: number; reviews: number; location: string;
  photo: string; photoPos?: string; amenities: { icon: IconName; label: string }[]; pricePerNight: Money; tags: ("boutique" | "stars45" | "view")[];
}
export interface Flight {
  id: string; airline: string; code: string; logoColor: string; depart: string; arrive: string; from: string; fromCity: string;
  to: string; toCity: string; duration: string; stops: string; carryOn: string; baggage: string; meal: string; pricePerPerson: Money;
}
export interface ItineraryDay { day: number; date: string; title: string; photo: string; photoPos?: string; items: { icon: IconName; label: string }[] }
export interface Stop { city: string; days: string; photo: string; photoPos?: string; x: number; y: number }

export interface Trip {
  id: string; country: string; title: string; summary: string; why: string;
  days: number; dates: string; dateRange: [string, string]; travelers: number; price: Money;
  tags: { icon: IconName; label: string }[];
  hero: string; heroPos?: string; photos: { src: string; label: string; pos?: string }[];
  includes: { icon: IconName; title: string; sub: string }[];
  reasons: { icon: IconName; text: string }[];
  itinerary: ItineraryDay[]; hotels: Hotel[]; cities: string[]; flights: Flight[]; stops: Stop[];
}

export interface SearchParamsUI { dates?: string; travelers?: string; budget?: string }
