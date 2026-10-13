"""Additional Part C coverage for budgets, cooldown waits and deadlines.

These supplement the provided tests without changing them.
"""

from __future__ import annotations

import pytest

from gameday_lab.client import ResilientClient
from gameday_lab.sim.contracts import Attempt, CallContext, GiveUp, ProviderError, ProviderInfo, Send


def make_client(*, single_provider: bool = False, **settings: object) -> ResilientClient:
    names = ["primary"] if single_provider else ["primary", "backup"]
    providers = {name: ProviderInfo(name, name, "us", True, 1.0) for name in names}
    return ResilientClient(providers, names, settings, seed=7)


def start(client: ResilientClient, *, now: float = 0.0, deadline: float = 30.0) -> tuple[CallContext, Send]:
    call = CallContext(1, 1, "tool", now, deadline)
    send = client.start(call, now)
    assert isinstance(send, Send)
    return call, send


def fail(client: ResilientClient, call: CallContext, send: Send, *, now: float = 0.1,
         status: int = 500, code: str = "api_error", retry_after: float | None = None,
         number: int = 1) -> Send | GiveUp:
    action = client.on_error(
        Attempt(call, send.provider, number, now, send.tag),
        ProviderError(send.provider, status, code, retry_after=retry_after), now,
    )
    assert isinstance(action, (Send, GiveUp))
    return action


def test_empty_budget_fails_over_without_charging_the_first_attempt() -> None:
    client = make_client(retry_budget_ratio=0.0, retry_budget_min_per_s=0.0, retry_budget_max_tokens=0.0)
    call, send = start(client)
    action = fail(client, call, send)
    assert isinstance(action, Send) and action.provider == "backup" and action.delay_s == 0.0
    assert client.budget.tokens == 0.0


def test_attempt_limit_is_per_provider_not_global_attempt_number() -> None:
    client = make_client()
    call, first = start(client)
    retry = fail(client, call, first)
    assert isinstance(retry, Send) and retry.provider == "primary"
    backup = fail(client, call, retry, now=0.5, number=2)
    assert isinstance(backup, Send) and backup.provider == "backup"
    backup_retry = fail(client, call, backup, now=0.6, number=3)
    assert isinstance(backup_retry, Send) and backup_retry.provider == "backup"


def test_short_rate_limit_wait_respects_header_budget_and_attempt_limit() -> None:
    client = make_client(single_provider=True, retry_budget_ratio=0.0, retry_budget_min_per_s=0.0)
    call, send = start(client)
    tokens = client.budget.tokens
    action = fail(client, call, send, status=429, code="rate_limit_exceeded", retry_after=2.0)
    assert isinstance(action, Send) and action.provider == "primary"
    assert action.delay_s >= 2.0
    assert 0.1 + action.delay_s + action.timeout_s <= call.deadline
    assert client.budget.tokens == tokens - 1
    exhausted = fail(client, call, action, now=2.2, status=429, code="rate_limit_exceeded", retry_after=2.0)
    assert isinstance(exhausted, GiveUp)


@pytest.mark.parametrize("retry_after, deadline", [(6.0, 30.0), (2.0, 2.5)])
def test_rate_limit_wait_is_rejected_if_too_long_or_past_deadline(retry_after: float, deadline: float) -> None:
    client = make_client(single_provider=True)
    call, send = start(client, deadline=deadline)
    action = fail(client, call, send, status=429, code="rate_limit_exceeded", retry_after=retry_after)
    assert isinstance(action, GiveUp)


def test_rate_limit_wait_also_requires_retry_budget() -> None:
    client = make_client(single_provider=True, retry_budget_ratio=0.0,
                         retry_budget_min_per_s=0.0, retry_budget_max_tokens=0.0)
    call, send = start(client)
    action = fail(client, call, send, status=429, code="rate_limit_exceeded", retry_after=2.0)
    assert isinstance(action, GiveUp)


def test_quota_cooldown_is_not_treated_as_short_rate_limit_wait_near_expiry() -> None:
    client = make_client(single_provider=True)
    call, send = start(client)
    action = fail(client, call, send, status=429, code="insufficient_quota")
    assert isinstance(action, GiveUp)
    second = CallContext(2, 2, "tool", 298.0, 328.0)
    assert isinstance(client.start(second, 298.0), GiveUp)
    restored = CallContext(3, 3, "tool", 301.0, 331.0)
    assert isinstance(client.start(restored, 301.0), Send)


def test_concurrent_rate_limit_results_do_not_shorten_shared_cooldown() -> None:
    client = make_client()
    call, send = start(client)
    second, second_send = start(client)
    fail(client, call, send, status=429, code="rate_limit_exceeded", retry_after=4.0)
    fail(client, second, second_send, now=0.2, status=429, code="rate_limit_exceeded", retry_after=1.0)
    assert client.cooldown_until["primary"] == pytest.approx(4.1)
    third = CallContext(3, 3, "tool", 2.0, 32.0)
    action = client.start(third, 2.0)
    assert isinstance(action, Send) and action.provider == "backup"


def test_retry_that_cannot_fit_falls_over_immediately_without_spending_budget() -> None:
    client = make_client(backoff_base_s=10.0, backoff_cap_s=10.0)
    call, send = start(client, deadline=2.0)
    tokens = client.budget.tokens
    action = fail(client, call, send, now=0.1)
    assert isinstance(action, Send) and action.provider == "backup" and action.delay_s == 0.0
    assert 0.1 + action.timeout_s <= call.deadline
    assert client.budget.tokens == tokens
