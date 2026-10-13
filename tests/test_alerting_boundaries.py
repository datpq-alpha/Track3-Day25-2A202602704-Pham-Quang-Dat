"""Additional boundaries for prefix sums, episodes and exhausted budgets."""

import pytest

from gameday_lab.slo.alerting import AlertRule, BurnRateAlerter, WindowSums, error_budget_report


def test_exact_burn_threshold_fires_and_episode_flushes_at_end() -> None:
    rules = (AlertRule("boundary", "page", 3, 1, 14.4),)
    events = BurnRateAlerter(rules=rules).evaluate([1000] * 3, [72] * 3)
    assert len(events) == 1
    assert events[0].start_min == 0 and events[0].end_min == 3


def test_separate_episodes_are_not_emitted_once_per_minute() -> None:
    rules = (AlertRule("episodes", "page", 1, 1, 1.0),)
    events = BurnRateAlerter(rules=rules).evaluate([1000] * 6, [10, 10, 0, 0, 10, 10])
    assert [(event.start_min, event.end_min) for event in events] == [(0, 2), (4, 6)]


def test_zero_traffic_and_empty_data_do_not_alert_or_freeze() -> None:
    assert BurnRateAlerter().evaluate([0] * 10, [0] * 10) == []
    assert BurnRateAlerter().evaluate([], []) == []
    budget = error_budget_report([], [])
    assert budget["availability"] == 1.0 and budget["budget_consumed"] == 0.0
    assert budget["freeze_releases"] is False


def test_exactly_exhausted_budget_freezes_despite_float_rounding() -> None:
    budget = error_budget_report([100000], [500])
    assert budget["budget_remaining"] == 0.0 and budget["freeze_releases"] is True


def test_small_positive_unrounded_budget_does_not_freeze() -> None:
    budget = error_budget_report([1000000000], [4999999])
    assert budget["freeze_releases"] is False


def test_prefix_windows_clip_both_ends_and_reject_empty_length() -> None:
    sums = WindowSums([1, 2, 3])
    assert sums.sum(-1, 10) == 0
    assert sums.sum(5, 6) == 6
    assert sums.sum(5, 1) == 0
    with pytest.raises(ValueError):
        sums.sum(2, 0)


def test_mismatched_series_are_rejected() -> None:
    with pytest.raises(ValueError):
        BurnRateAlerter().evaluate([100], [])
    with pytest.raises(ValueError):
        error_budget_report([100], [])
