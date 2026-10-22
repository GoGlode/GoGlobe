// Единая точка получения поездок для UI. Сейчас — демо-данные с имитацией задержки (стабильно, без сети).
// TODO(интеграция): вызвать api/client.ts#search и привести Offer[] к Trip[] (docs/api-contract.md).
import { TRIPS } from "./trips";
import type { SearchParamsUI, Trip } from "./types";

export const SEARCH_STEPS = ["Разбираю запрос…", "Ищу перелёты…", "Ищу отели…", "Проверяю бюджет и даты…", "Ранжирую и объясняю варианты…"];

export async function searchTrips(_query: string, _params: SearchParamsUI, onStep?: (i: number) => void): Promise<Trip[]> {
  for (let i = 0; i < SEARCH_STEPS.length; i++) {
    onStep?.(i);
    await new Promise((r) => setTimeout(r, 650));
  }
  return TRIPS;
}
