"""Weather flags on planned outdoor sessions (backlog 1.12)."""

from __future__ import annotations

import json
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from httpx import Response

from intervals_icu_mcp.coaching.athlete_state import get_athlete_state
from intervals_icu_mcp.coaching.coach_brief import build_coach_brief
from intervals_icu_mcp.coaching.weather import day_flags, weather_block, weather_flag_lines
from intervals_icu_mcp.models import Event

TODAY = date(2026, 11, 24)  # Tuesday


def _day(day: str, *, rain=0.0, snow=0.0, tmin=4.0, tmax=10.0, feels=7.0, gust=6.0, desc=""):
    return {
        "id": day,
        "rain": rain,
        "snow": snow,
        "wind_gust": gust,
        "temp": {"min": tmin, "max": tmax, "day": tmax, "night": tmin, "eve": tmax, "morn": tmin},
        "feels_like": {"day": feels, "night": feels, "eve": feels, "morn": feels},
        "weather": [{"description": desc or ("moderate rain" if rain else "clear sky")}],
        "sunrise": "07:31",
        "sunset": "17:18",
    }


def _slot(stamp: str, rain=0.0):
    return {
        "id": stamp,
        "rain": rain,
        "snow": 0.0,
        "wind_gust": 5.0,
        "feels_like": 6.0,
        "mins": 180,
    }


def _payload(**overrides: Any) -> dict[str, Any]:
    forecast = {
        "id": 1,
        "provider": "OPEN_WEATHER",
        "location": "Leeds,England,GB",
        "label": "Leeds",
        "enabled": True,
        "error": None,
        "daily": [
            _day("2026-11-24"),
            _day("2026-11-25"),
            _day("2026-11-26", rain=36.3, gust=11.5),
            _day("2026-11-27", rain=8.0),
            _day("2026-11-28"),
            _day("2026-11-29", rain=10.7),
            _day("2026-12-07", rain=24.9, gust=18.7),
        ],
        "hourly": [
            _slot("2026-11-26 06:00", rain=2.0),
            _slot("2026-11-26 09:00"),
            _slot("2026-11-26 12:00", rain=5.0),
            _slot("2026-11-26 18:00"),
        ],
    }
    forecast.update(overrides)
    return {"forecasts": [forecast]}


def _workout(event_id: int, day: str, sport: str, name: str, **extra: Any) -> Event:
    return Event.model_validate(
        {
            "id": event_id,
            "start_date_local": f"{day}T00:00:00",
            "category": "WORKOUT",
            "type": sport,
            "name": name,
            **extra,
        }
    )


EVENTS = [
    _workout(1, "2026-11-26", "Ride", "Long ride"),
    _workout(2, "2026-11-27", "Run", "Easy run"),
    _workout(3, "2026-11-26", "Ride", "Trainer intervals", indoor=True),
    _workout(4, "2026-11-28", "Ride", "Endurance"),
    _workout(5, "2026-12-07", "Ride", "Club ride"),
    _workout(6, "2026-11-26", "WeightTraining", "Gym"),
]


class TestDayFlags:
    def _measures(self, **day: Any) -> dict[str, Any]:
        from intervals_icu_mcp.coaching.weather import (
            _day_measures,  # pyright: ignore[reportPrivateUsage]
        )

        return _day_measures(_day("2026-11-24", **day))

    def test_rain_threshold_differs_for_rides_and_runs(self):
        measures = self._measures(rain=8.0)
        assert day_flags(measures, on_foot=False) == ["wet"]
        assert day_flags(measures, on_foot=True) == []

    def test_ice_needs_precipitation_and_freezing_air(self):
        assert "ice_risk" in day_flags(self._measures(rain=2.0, tmin=0.5), on_foot=True)
        assert "ice_risk" not in day_flags(self._measures(rain=0.0, tmin=-5.0), on_foot=True)

    def test_heat_cold_frostbite_and_wind(self):
        assert day_flags(self._measures(feels=30.0, tmax=29.0), on_foot=False) == ["heat"]
        assert day_flags(self._measures(feels=-12.0), on_foot=False) == ["cold"]
        assert day_flags(self._measures(feels=-30.0), on_foot=False) == ["frostbite_risk"]
        assert day_flags(self._measures(gust=14.0), on_foot=False) == ["windy"]


class TestWeatherBlock:
    def test_names_the_city_and_how_to_change_it(self):
        block = weather_block(_payload(), EVENTS, TODAY)
        assert block is not None
        assert block["status"] == "ok"
        assert block["city"] == "Leeds"
        assert "Leeds" in block["say_city"]
        assert "Options -> Weather" in block["how_to_change_location"]
        assert [d["date"] for d in block["days"]] == [
            "2026-11-24",
            "2026-11-25",
            "2026-11-26",
            "2026-11-27",
            "2026-11-28",
        ]

    def test_flags_only_outdoor_sessions_that_need_it(self):
        block = weather_block(_payload(), EVENTS, TODAY)
        assert block is not None
        flagged = {s["id"]: s for s in block["flagged_sessions"]}
        # Indoor ride, gym, a run under the run threshold and a dry day are left alone.
        assert set(flagged) == {1, 5}
        long_ride = flagged[1]
        assert long_ride["flags"] == ["wet"]
        assert long_ride["act"] == "offer_move_or_indoor"
        assert long_ride["indoor_version"] is True
        assert [d["weekday"] for d in long_ride["clear_days_this_week"]] == ["Tue", "Wed", "Sat"]
        saturday = long_ride["clear_days_this_week"][-1]
        assert saturday["already_planned"] == ["Endurance"]
        # 06:00 is wet, 12:00 wet, 18:00 after sunset.
        assert long_ride["clear_hours_that_day"] == ["09:00"]
        assert flagged[5]["act"] == "heads_up_only"
        assert "clear_days_this_week" not in flagged[5]

    def test_no_location_and_errors_do_not_guess(self):
        empty = weather_block({"forecasts": []}, EVENTS, TODAY)
        assert empty is not None and empty["status"] == "no_forecast"
        assert "Options -> Weather" in empty["how_to_set_location"]
        errored = weather_block(_payload(error="provider down", daily=[]), EVENTS, TODAY)
        assert errored is not None and errored["status"] == "no_forecast"
        failed = weather_block(RuntimeError("boom"), EVENTS, TODAY)
        assert failed is not None and failed["status"] == "unavailable"
        assert weather_block(None, EVENTS, TODAY) is None

    def test_other_enabled_locations_are_listed(self):
        payload = _payload()
        payload["forecasts"].append(
            {"id": 2, "label": "Girona", "location": "Girona,ES", "enabled": True, "daily": []}
        )
        block = weather_block(payload, EVENTS, TODAY)
        assert block is not None
        assert block["city"] == "Leeds"
        assert block["other_enabled_locations"] == ["Girona"]


class TestBriefIntegration:
    def _brief(self, payload: dict[str, Any]) -> dict[str, Any]:
        return build_coach_brief(
            today=TODAY,
            events=EVENTS,
            activities=[],
            phase_context={},
            current_fitness={},
            tolerance={},
            constraints={},
            readiness_state=None,
            weather=weather_block(payload, EVENTS, TODAY),
        )

    def test_next_action_and_provenance_name_the_city(self):
        brief = self._brief(_payload())
        assert brief["weather"]["city"] == "Leeds"
        assert any("Weather in Leeds" in a for a in brief["next_actions"])
        assert brief["provenance"]["values"]["weather"]["rule_id"] == "weather_flags.v1"

    def test_flag_lines_cover_the_next_two_days_only(self):
        block = weather_block(_payload(), EVENTS, TODAY)
        assert weather_flag_lines(block, TODAY) == []
        wednesday = date(2026, 11, 25)
        lines = weather_flag_lines(weather_block(_payload(), EVENTS, wednesday), wednesday)
        assert lines == [
            "Long ride (Thu): wet forecast in Leeds; clear days this week: Wed, Sat; "
            "or the indoor version."
        ]

    def test_several_locations_ask_where_first(self):
        payload = _payload()
        payload["forecasts"].append({"id": 2, "label": "Girona", "enabled": True, "daily": []})
        brief = self._brief(payload)
        assert any("ask where they will be" in a for a in brief["next_actions"])


def _ctx(config):
    ctx = MagicMock()
    ctx.get_state = AsyncMock(return_value=config)
    return ctx


def _mock_state(respx_mock, forecast: Response) -> None:
    respx_mock.get("/athlete/i123456").mock(return_value=Response(200, json={}))
    for path in ("wellness", "activities", "sport-settings"):
        respx_mock.get(f"/athlete/i123456/{path}").mock(return_value=Response(200, json=[]))
    respx_mock.get("/athlete/i123456/events").mock(
        return_value=Response(200, json=[e.model_dump(exclude_none=True) for e in EVENTS])
    )
    respx_mock.get("/athlete/i123456/power-curves").mock(
        return_value=Response(200, json={"list": []})
    )
    respx_mock.get("/athlete/i123456/weather-forecast").mock(return_value=forecast)


class TestAthleteStateWeather:
    async def test_state_carries_weather(self, mock_config, respx_mock, monkeypatch):
        monkeypatch.setattr(
            "intervals_icu_mcp.coaching.athlete_state._athlete_today",
            AsyncMock(return_value=(TODAY, "Europe/London")),
        )
        _mock_state(respx_mock, Response(200, json=_payload()))
        response = json.loads(await get_athlete_state(ctx=_ctx(mock_config)))
        weather = response["analysis"]["coach_brief"]["weather"]
        assert weather["city"] == "Leeds"
        assert [s["id"] for s in weather["flagged_sessions"]] == [1, 5]
        assert "partial_errors" not in response["metadata"]

    async def test_forecast_failure_is_not_a_guess(self, mock_config, respx_mock, monkeypatch):
        monkeypatch.setattr(
            "intervals_icu_mcp.coaching.athlete_state._athlete_today",
            AsyncMock(return_value=(TODAY, "Europe/London")),
        )
        _mock_state(respx_mock, Response(403, json={"error": "premium only"}))
        response = json.loads(await get_athlete_state(ctx=_ctx(mock_config)))
        assert response["analysis"]["coach_brief"]["weather"]["status"] == "unavailable"

    async def test_no_calendar_no_forecast_call(self, mock_config, respx_mock, monkeypatch):
        monkeypatch.setattr(
            "intervals_icu_mcp.coaching.athlete_state._athlete_today",
            AsyncMock(return_value=(TODAY, "Europe/London")),
        )
        _mock_state(respx_mock, Response(200, json=_payload()))
        response = json.loads(
            await get_athlete_state(ctx=_ctx(mock_config), include=["fitness_form"])
        )
        assert "weather" not in response["analysis"]["coach_brief"]
        assert not respx_mock.routes[-1].called
