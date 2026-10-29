"""Cached Aviasales fares; intentionally separate from FlightOffer segments."""
import os
from datetime import UTC, datetime

import httpx

_IATA = {"москва": "MOW", "rome": "ROM", "рим": "ROM", "санкт-петербург": "LED"}


def iata(city: str | None) -> str | None:
    return _IATA.get((city or "").strip().casefold())


async def cached_fares(origin: str | None, destination: str | None, departure: str | None, return_date: str | None) -> dict:
    token = os.getenv("TRAVELPAYOUTS_TOKEN")
    source = {"name": "Aviasales Data API", "checked_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
    origin_iata, destination_iata = iata(origin), iata(destination)
    if not token or not origin_iata or not destination_iata or not departure:
        return {"status": "empty", "items": [], "source": source, "checked_at": source["checked_at"], "warnings": [{"code": "CACHED_FARES_UNAVAILABLE", "message": "Недостаточно подтверждённых данных для кэшированных тарифов."}]}
    params = {"origin": origin_iata, "destination": destination_iata, "departure_at": departure, "currency": "rub", "limit": 20}
    if return_date:
        params["return_at"] = return_date
    try:
        async with httpx.AsyncClient(timeout=8, trust_env=False) as client:
            response = await client.get("https://api.travelpayouts.com/aviasales/v3/prices_for_dates", params=params, headers={"X-Access-Token": token, "Accept": "application/json"})
            response.raise_for_status(); payload = response.json()
        items = []
        for row in payload.get("data", [])[:20]:
            if not isinstance(row, dict) or type(row.get("price")) not in {int, float} or row["price"] < 0:
                continue
            items.append({"origin_iata": row.get("origin", origin_iata), "destination_iata": row.get("destination", destination_iata), "departure_date": row.get("departure_at"), "return_date": row.get("return_at"), "airline": row.get("airline"), "transfers": row.get("transfers"), "price": {"amount": row["price"], "currency": "RUB"}, "booking_url": None})
        return {"status": "ok" if items else "empty", "items": items, "source": source, "checked_at": source["checked_at"], "warnings": []}
    except (httpx.HTTPError, ValueError, TypeError):
        return {"status": "unavailable", "items": [], "source": source, "checked_at": source["checked_at"], "warnings": [{"code": "CACHED_FARES_UNAVAILABLE", "message": "Кэшированные тарифы временно недоступны."}]}
