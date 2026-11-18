"""Data-quality sentinel findings and exclusion policy."""

from intervals_icu_mcp.data_quality import data_quality_report, stream_sensor_issues
from intervals_icu_mcp.models import ActivityStream, ActivitySummary, SportSettings, Wellness


def _activity(activity_id: str, **overrides) -> ActivitySummary:
    data = {
        "id": activity_id,
        "start_date_local": "2026-11-10T08:00:00",
        "name": "Ride",
        "type": "Ride",
        "distance": 50000,
        "moving_time": 7200,
        "icu_training_load": 100,
        "average_watts": 200,
        "average_heartrate": 145,
    }
    data.update(overrides)
    return ActivitySummary.model_validate(data)


def _ride_settings(**overrides) -> SportSettings:
    data = {"id": 1, "types": ["Ride"], "ftp": 250, "lthr": 165, "max_hr": 190}
    data.update(overrides)
    return SportSettings.model_validate(data)


def test_strava_missing_power_duplicates_and_streams_use_existing_gap_shape():
    activities = [
        _activity("keep"),
        _activity("duplicate"),
        _activity(
            "no-power",
            start_date_local="2026-11-11T08:00:00",
            average_watts=None,
            normalized_power=None,
        ),
        _activity(
            "strava",
            start_date_local="2026-11-12T08:00:00",
            source="STRAVA",
            distance=None,
            moving_time=None,
            icu_training_load=None,
            average_watts=None,
            average_heartrate=None,
        ),
    ]

    report = data_quality_report(
        activities=activities,
        wellness=[],
        settings=[_ride_settings()],
        stream_issues={"keep": ["power_spike"]},
    )

    fields = {gap["field"] for gap in report["gaps"]}
    assert fields == {
        "activities.duplicates",
        "activities.power",
        "activities.source",
        "activities.streams",
    }
    assert all(set(gap) == {"field", "severity", "message", "prompt"} for gap in report["gaps"])
    assert report["excluded_activity_ids"] == ["keep", "no-power", "strava"]
    assert all(
        "Excluded from coach models" in gap["message"]
        for gap in report["gaps"]
        if gap["field"].startswith("activities.")
    )


def test_threshold_and_daily_load_mismatches_are_reported():
    activity = _activity("run", type="Run", average_watts=None)
    wellness = [
        Wellness.model_validate({"id": "2026-11-10", "ctlLoad": 0}),
        Wellness.model_validate({"id": "2026-11-09", "ctlLoad": 50}),
    ]
    settings = [SportSettings.model_validate({"id": 2, "types": ["Run"]})]

    report = data_quality_report(
        activities=[activity],
        wellness=wellness,
        settings=settings,
    )

    by_field = {gap["field"]: gap for gap in report["gaps"]}
    assert "Run" in by_field["sport_settings.thresholds"]["message"]
    assert "load but no activity on 2026-11-09" in by_field["fitness.daily_load"]["message"]
    assert "activity but no daily load on 2026-11-10" in by_field["fitness.daily_load"]["message"]
    assert report["excluded_activity_ids"] == ["run"]


def test_stream_detector_finds_dropouts_and_implausible_spikes():
    streams = [
        ActivityStream(type="watts", data=[200] * 10 + [0] * 120 + [3000]),
        ActivityStream(type="heartrate", data=[150] * 10 + [0] * 10 + [220] + [150] * 110),
        ActivityStream(type="cadence", data=[90] * 131),
    ]

    assert stream_sensor_issues(streams, ftp=250, max_hr=190) == [
        "power_dropout",
        "power_spike",
        "heart_rate_dropout",
        "heart_rate_spike",
    ]
