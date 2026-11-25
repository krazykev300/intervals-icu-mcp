"""Weather flags for planned outdoor sessions (backlog 1.12, no HTTP but the fetch).

Reads the Intervals forecast (`GET /athlete/{id}/weather-forecast`, OpenWeather
behind it) and marks planned outdoor WORKOUTs that fall on a wet, snowy, icy,
hot, cold or windy day. Inside `WEATHER["move_window_days"]` it lists dry days
in the same week and dry daylight hours; later sessions get a heads-up only.

Every result names the forecast city, so the coach can say it and the athlete
can correct it when they will be somewhere else.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, cast

from ..client import ICUClient
from ..models import Event
from .athlete_state_compute import parse_iso_date
from .methodology import WEATHER

_RIDE_TYPES = frozenset(
    {"Ride", "GravelRide", "MountainBikeRide", "EBikeRide", "EMountainBikeRide"}
)
_FOOT_TYPES = frozenset({"Run", "TrailRun", "Walk", "Hike"})
OUTDOOR_TYPES = _RIDE_TYPES | _FOOT_TYPES
# Sports with a usual indoor version (trainer, treadmill).
_INDOOR_VERSION_TYPES = frozenset({"Ride", "GravelRide", "MountainBikeRide", "Run", "TrailRun"})
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

CHANGE_LOCATION_HOW_TO = (
    "In Intervals.icu open Options -> Weather (calendar or activity view), choose Add "
    "location, then turn off or delete the old one. Several can be saved and switched "
    "on for a trip or race."
)


async def fetch_forecast(client: ICUClient, athlete_id: str) -> dict[str, Any]:
    """Raw forecast payload. Raises on HTTP errors; the caller decides what that means."""
    response = await client._request("GET", f"/athlete/{athlete_id}/weather-forecast")  # pyright: ignore[reportPrivateUsage]
    payload: Any = response.json()
    if not isinstance(payload, dict):
        return {}
    return cast(dict[str, Any], payload)


def _num(value: Any) -> float:
    return float(value) if isinstance(value, int | float) else 0.0


def _part(raw: Any, key: str) -> float | None:
    if isinstance(raw, dict):
        value = cast(dict[str, Any], raw).get(key)
        if isinstance(value, int | float):
            return float(value)
    return None


def _day_measures(day: dict[str, Any]) -> dict[str, Any]:
    temp = day.get("temp")
    feels = day.get("feels_like")
    daytime = [v for v in (_part(feels, k) for k in ("morn", "day", "eve")) if v is not None]
    highs = [v for v in (*daytime, _part(temp, "max")) if v is not None]
    weather_list = day.get("weather")
    description = ""
    if isinstance(weather_list, list) and weather_list:
        first = cast(list[Any], weather_list)[0]
        if isinstance(first, dict):
            description = str(cast(dict[str, Any], first).get("description") or "")
    return {
        "rain_mm": round(_num(day.get("rain")), 1),
        "snow_mm": round(_num(day.get("snow")), 1),
        "temp_min_c": _part(temp, "min"),
        "temp_max_c": _part(temp, "max"),
        "feels_like_low_c": min(daytime) if daytime else None,
        "feels_like_high_c": max(highs) if highs else None,
        "gust_ms": round(_num(day.get("wind_gust")), 1),
        "summary": description,
        "sunrise": day.get("sunrise"),
        "sunset": day.get("sunset"),
    }


def day_flags(measures: dict[str, Any], on_foot: bool) -> list[str]:
    """Conditions that matter for an outdoor session that day."""
    flags: list[str] = []
    rain, snow = measures["rain_mm"], measures["snow_mm"]
    wet_min = WEATHER["run_rain_mm_min"] if on_foot else WEATHER["wet_day_rain_mm_min"]
    if rain >= wet_min:
        flags.append("wet")
    if snow >= WEATHER["wet_day_rain_mm_min"]:
        flags.append("snow")
    low_temp = measures["temp_min_c"]
    if (
        rain + snow >= WEATHER["wet_day_rain_mm_min"]
        and low_temp is not None
        and low_temp <= WEATHER["ice_temp_c_max"]
    ):
        flags.append("ice_risk")
    high = measures["feels_like_high_c"]
    if high is not None and high >= WEATHER["heat_feels_like_c_min"]:
        flags.append("heat")
    low = measures["feels_like_low_c"]
    if low is not None and low <= WEATHER["frostbite_feels_like_c_max"]:
        flags.append("frostbite_risk")
    elif low is not None and low <= WEATHER["cold_feels_like_c_max"]:
        flags.append("cold")
    if measures["gust_ms"] >= WEATHER["gust_ms_min"]:
        flags.append("windy")
    return flags


def _slot_ok(slot: dict[str, Any]) -> bool:
    feels = slot.get("feels_like")
    if _num(slot.get("rain")) + _num(slot.get("snow")) > 0:
        return False
    if _num(slot.get("wind_gust")) >= WEATHER["gust_ms_min"]:
        return False
    if isinstance(feels, int | float):
        if feels >= WEATHER["heat_feels_like_c_min"]:
            return False
        if feels <= WEATHER["cold_feels_like_c_max"]:
            return False
    return True


def _clear_hours(hourly: list[dict[str, Any]], day: date, sunrise: Any, sunset: Any) -> list[str]:
    """Start times of 3-hour daylight slots with no rain, snow, heat, cold or strong gusts."""
    hours: list[str] = []
    for slot in hourly:
        stamp = slot.get("id")
        if not isinstance(stamp, str):
            continue
        try:
            when = datetime.strptime(stamp, "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        if when.date() != day:
            continue
        clock = when.strftime("%H:%M")
        if isinstance(sunrise, str) and isinstance(sunset, str):
            # A slot counts when any of its three hours is in daylight.
            slot_end = (when + timedelta(hours=3)).strftime("%H:%M")
            if slot_end <= sunrise or clock >= sunset:
                continue
        if _slot_ok(slot):
            hours.append(clock)
    return hours


def _pick_forecast(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    raw = payload.get("forecasts")
    forecasts = (
        [cast(dict[str, Any], f) for f in cast(list[Any], raw) if isinstance(f, dict)]
        if isinstance(raw, list)
        else []
    )
    usable = [f for f in forecasts if f.get("enabled", True) is not False]
    chosen = next((f for f in usable if not f.get("error") and f.get("daily")), None)
    others = [str(f.get("label") or f.get("location")) for f in usable if f is not chosen]
    return chosen, others


def weather_block(
    payload: dict[str, Any] | BaseException | None,
    events: list[Event],
    today: date,
) -> dict[str, Any] | None:
    """`coach_brief.weather`. None when the forecast was not requested."""
    if payload is None:
        return None
    if isinstance(payload, BaseException):
        return {
            "status": "unavailable",
            "why": "the Intervals forecast could not be read; do not guess the weather",
        }
    forecast, others = _pick_forecast(payload)
    if forecast is None:
        return {
            "status": "no_forecast",
            "why": "no enabled Intervals forecast location returned data; do not guess",
            "how_to_set_location": CHANGE_LOCATION_HOW_TO,
        }
    city = str(forecast.get("label") or forecast.get("location") or "the forecast location")
    daily_raw = cast(list[Any], forecast.get("daily") or [])
    hourly_raw = cast(list[Any], forecast.get("hourly") or [])
    hourly = [cast(dict[str, Any], h) for h in hourly_raw if isinstance(h, dict)]
    by_date: dict[date, dict[str, Any]] = {}
    daily = [cast(dict[str, Any], d) for d in daily_raw if isinstance(d, dict)]
    for entry in daily:
        try:
            by_date[date.fromisoformat(str(entry.get("id")))] = _day_measures(entry)
        except ValueError:
            continue

    window_end = today + timedelta(days=int(WEATHER["move_window_days"]))
    planned_by_day: dict[date, list[str]] = {}
    for event in events:
        if event.category == "WORKOUT":
            day = parse_iso_date(event.start_date_local)
            planned_by_day.setdefault(day, []).append(event.name or event.type or "session")

    days: list[dict[str, Any]] = []
    for day in sorted(by_date):
        if today <= day < window_end:
            measures = by_date[day]
            item: dict[str, Any] = {"date": day.isoformat(), "weekday": _WEEKDAYS[day.weekday()]}
            item.update({k: v for k, v in measures.items() if k not in ("sunrise", "sunset")})
            item["flags"] = day_flags(measures, on_foot=False)
            days.append(item)

    sessions: list[dict[str, Any]] = []
    for event in events:
        if event.category != "WORKOUT" or event.type not in OUTDOOR_TYPES or event.indoor:
            continue
        day = parse_iso_date(event.start_date_local)
        measures = by_date.get(day)
        if day < today or measures is None:
            continue
        on_foot = event.type in _FOOT_TYPES
        flags = day_flags(measures, on_foot=on_foot)
        if not flags:
            continue
        session: dict[str, Any] = {
            "id": event.id,
            "name": event.name,
            "type": event.type,
            "date": day.isoformat(),
            "weekday": _WEEKDAYS[day.weekday()],
            "flags": flags,
            "indoor_version": event.type in _INDOOR_VERSION_TYPES,
        }
        if day < window_end:
            session["act"] = "offer_move_or_indoor"
            week_end = day + timedelta(days=6 - day.weekday())
            dry: list[dict[str, Any]] = []
            for other in sorted(by_date):
                if other == day or not today <= other <= week_end or other >= window_end:
                    continue
                if day_flags(by_date[other], on_foot=on_foot):
                    continue
                option: dict[str, Any] = {
                    "date": other.isoformat(),
                    "weekday": _WEEKDAYS[other.weekday()],
                }
                if planned_by_day.get(other):
                    option["already_planned"] = planned_by_day[other]
                dry.append(option)
            session["clear_days_this_week"] = dry
            hours = _clear_hours(hourly, day, measures.get("sunrise"), measures.get("sunset"))
            if hourly and any(str(h.get("id", "")).startswith(day.isoformat()) for h in hourly):
                session["clear_hours_that_day"] = hours
        else:
            session["act"] = "heads_up_only"
        sessions.append(session)
    sessions.sort(key=lambda s: s["date"])

    block: dict[str, Any] = {
        "status": "ok",
        "city": city,
        "location": forecast.get("location"),
        "say_city": (
            f"Name {city} in every weather reason (e.g. 'Rain is forecast in {city} on "
            "Thursday'). If they will be elsewhere, plan that day without the forecast. "
            "To change the default: how_to_change_location."
        ),
        "how_to_change_location": CHANGE_LOCATION_HOW_TO,
        "days": days,
    }
    if others:
        block["other_enabled_locations"] = others
    if sessions:
        block["flagged_sessions"] = sessions
    return block


def weather_flag_lines(weather: dict[str, Any] | None, today: date) -> list[str]:
    """One today-flag line per flagged session in the next two days, city named."""
    if not weather or weather.get("status") != "ok":
        return []
    lines: list[str] = []
    city = weather["city"]
    horizon = (today + timedelta(days=1)).isoformat()
    for session in weather.get("flagged_sessions", []):
        if session["date"] > horizon:
            continue
        flags = ", ".join(session["flags"]).replace("_", " ")
        line = f"{session['name']} ({session['weekday']}): {flags} forecast in {city}"
        dry = [d["weekday"] for d in session.get("clear_days_this_week", [])]
        if dry:
            line += f"; clear days this week: {', '.join(dry)}"
        if session.get("indoor_version"):
            line += "; or the indoor version"
        lines.append(line + ".")
    return lines
