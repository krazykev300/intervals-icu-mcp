"""Unit tests for the local workout-syntax linter."""

from intervals_icu_mcp.workout_parser import (
    lint_workout_description,
    looks_like_workout_syntax,
)


class TestLooksLikeWorkoutSyntax:
    def test_step_line(self):
        assert looks_like_workout_syntax("Easy\n- 10m Z2")

    def test_repeat_header(self):
        assert looks_like_workout_syntax("Main 3x")

    def test_duration_range_step(self):
        assert looks_like_workout_syntax("- 3-4h Z2")

    def test_prose_is_not_syntax(self):
        assert not looks_like_workout_syntax("Nice and easy run for half an hour.")


class TestDurationRanges:
    def test_hour_range_is_an_error(self):
        lint = lint_workout_description("Main\n- 3-4h Z2")
        assert lint.errors
        assert "3-4h" in lint.errors[0]
        assert "single" in lint.errors[0].lower()

    def test_minute_range_is_an_error(self):
        lint = lint_workout_description("- 15-20m 90%")
        assert any("15-20m" in e for e in lint.errors)

    def test_distance_range_is_an_error(self):
        lint = lint_workout_description("- 400-800mtr Z2 pace")
        assert any("400-800mtr" in e for e in lint.errors)

    def test_both_units_range_is_an_error(self):
        lint = lint_workout_description("- 3h-4h Z2")
        assert lint.errors

    def test_power_range_is_not_a_duration_range(self):
        lint = lint_workout_description("Main\n- 10m 88-94%")
        assert lint.errors == []
        assert lint.total_duration_seconds == 600

    def test_watt_range_is_not_a_duration_range(self):
        lint = lint_workout_description("- 5m 240-260w")
        assert lint.errors == []
        assert lint.total_duration_seconds == 300

    def test_hr_range_is_not_a_duration_range(self):
        lint = lint_workout_description("- 10m 70-80% HR")
        assert lint.errors == []


class TestRepeatWhitespace:
    def test_header_directly_followed_by_steps_applies_repeat(self):
        lint = lint_workout_description("Main 3x\n- 15m 90%\n- 5m Z2")
        assert lint.errors == []
        assert lint.warnings == []
        assert lint.total_duration_seconds == 3 * (15 * 60 + 5 * 60)
        assert lint.steps[0]["reps"] == 3
        assert not lint.rewritten

    def test_blank_line_after_header_warns_and_still_applies_repeat(self):
        original = "Main 3x\n\n- 15m 90%\n- 5m Z2"
        lint = lint_workout_description(original)
        assert lint.errors == []
        assert lint.warnings
        assert "blank line" in lint.warnings[0].lower()
        assert "1x" in lint.warnings[0]
        assert lint.total_duration_seconds == 3 * (15 * 60 + 5 * 60)
        assert lint.rewritten
        assert lint.normalized_description == "Main 3x\n- 15m 90%\n- 5m Z2"

    def test_blank_line_after_last_step_before_next_section_is_fine(self):
        lint = lint_workout_description(
            "Warmup\n- 10m 50%\n\nMain 3x\n- 15m 90%\n- 5m Z2\n\nCooldown\n- 10m 50%"
        )
        assert not any("blank line" in w.lower() for w in lint.warnings)
        assert lint.steps[1]["reps"] == 3
        assert not lint.rewritten

    def test_blank_line_before_header_is_fine(self):
        lint = lint_workout_description("Warmup\n- 10m 50%\n\nMain 3x\n- 15m 90%")
        assert not any("blank line" in w.lower() for w in lint.warnings)
        assert lint.total_duration_seconds == 10 * 60 + 3 * 15 * 60
        assert not lint.rewritten

    def test_standalone_nx_header(self):
        lint = lint_workout_description("5x\n- 30s 120%\n- 30s 50%")
        assert lint.total_duration_seconds == 5 * 60
        assert lint.steps[0]["reps"] == 5

    def test_header_with_no_steps_warns(self):
        lint = lint_workout_description("Main 3x\n\nCooldown")
        assert any("no steps" in w.lower() for w in lint.warnings)


class TestDurationMath:
    def test_combined_hours_and_minutes(self):
        lint = lint_workout_description("- 1h30m 60%")
        assert lint.total_duration_seconds == 5400

    def test_minutes_and_seconds(self):
        lint = lint_workout_description("- 5m30s 90%")
        assert lint.total_duration_seconds == 330

    def test_clock_duration(self):
        lint = lint_workout_description("- 5:00 90%")
        assert lint.total_duration_seconds == 300

    def test_inline_repeat(self):
        lint = lint_workout_description("- 3x 1m 80%")
        assert lint.total_duration_seconds == 180
        assert lint.steps[0]["reps"] == 3

    def test_rest_appended_to_distance_step(self):
        lint = lint_workout_description("- 200mtr 95% pace 30s rest")
        assert lint.steps[0]["distance_meters"] == 200
        assert lint.steps[0]["rest_seconds"] == 30
        assert lint.total_duration_seconds == 30

    def test_distance_does_not_invent_time(self):
        lint = lint_workout_description("- 400mtr Z2 pace")
        assert lint.steps[0]["distance_meters"] == 400
        assert lint.total_duration_seconds == 0

    def test_pace_is_not_counted_as_clock_duration(self):
        lint = lint_workout_description("- 5m 5:00/km pace")
        assert lint.total_duration_seconds == 300


class TestSilentDropWarnings:
    def test_bare_pace_warns(self):
        lint = lint_workout_description("- 5m 5:00/km")
        assert any("pace" in w.lower() and "dropped" in w.lower() for w in lint.warnings)

    def test_css_token_warns(self):
        lint = lint_workout_description("- 200mtr CSS")
        assert any("CSS" in w for w in lint.warnings)

    def test_target_before_duration_warns(self):
        lint = lint_workout_description("- Z5 3m")
        assert any("before duration" in w.lower() for w in lint.warnings)

    def test_bare_m_track_distance_warns(self):
        lint = lint_workout_description("- 400m Z2")
        assert any("not meters" in w for w in lint.warnings)
        # Still parsed as 400 minutes, matching Intervals.icu.
        assert lint.total_duration_seconds == 400 * 60

    def test_ten_minutes_is_not_a_track_distance(self):
        lint = lint_workout_description("- 10m Z2")
        assert not any("not meters" in w for w in lint.warnings)

    def test_unparsed_prose_warns(self):
        lint = lint_workout_description("Just go for a ride.")
        assert any("No steps parsed" in w for w in lint.warnings)
        assert lint.total_duration_seconds == 0
