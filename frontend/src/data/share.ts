// «Поделиться» вариантом: ссылка на страницу поездки. Системное меню (телефон) → иначе копирование в буфер.
import type { Trip } from "./types";

export type ShareResult = "shared" | "copied" | "cancelled" | "failed";

export const tripUrl = (t: Pick<Trip, "id">) => `${window.location.origin}/trip/${encodeURIComponent(t.id)}`;

export async function shareTrip(t: Trip): Promise<ShareResult> {
  const url = tripUrl(t);
  try {
    if (navigator.share) { await navigator.share({ title: t.title, text: `${t.title} — вариант путешествия в GoGlobe`, url }); return "shared"; }
    await navigator.clipboard.writeText(url);
    return "copied";
  } catch (e) {
    return (e as DOMException)?.name === "AbortError" ? "cancelled" : "failed"; // отмена в системном меню — не ошибка
  }
}

export const SHARE_TEXT: Record<ShareResult, string | null> = { shared: null, copied: "Ссылка скопирована", cancelled: null, failed: "Не удалось поделиться — скопируйте ссылку из адресной строки" };
