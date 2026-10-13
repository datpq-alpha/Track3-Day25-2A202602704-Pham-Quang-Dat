"""Additional cache boundaries and invalidation-during-request checks."""

from __future__ import annotations

from gameday_lab.cache import CachingClient, SemanticCache
from gameday_lab.sim.contracts import (
    Action,
    Answer,
    Attempt,
    BaseClient,
    CallContext,
    GiveUp,
    ProviderError,
    Request,
    Send,
    Serve,
)


def request(version: str = "v1") -> Request:
    return Request("Shared FAQ", "user", False, version, (1.0, 0.0))


def answer(number: int = 1, version: str = "v1") -> Answer:
    return Answer(number, version, ("shared/source",), 0.0)


class Inner(BaseClient):
    def __init__(self) -> None:
        self.action: Action = Send("provider", 1.0)
        self.updates: list[str] = []

    def start(self, call: CallContext, now: float) -> Action:
        return self.action

    def on_error(self, attempt: Attempt, err: ProviderError, now: float) -> Action:
        return self.action

    def on_content_update(self, source: str, now: float) -> None:
        self.updates.append(source)


def running_request() -> tuple[CachingClient, Inner, CallContext, Attempt]:
    inner = Inner()
    cache = SemanticCache(ttl_s=1.0, max_stale_s=10.0)
    cache.store(request(), answer(), 0.0)
    client = CachingClient(inner, cache)
    call = CallContext(1, 1, "chat", 2.0, 32.0, request=request())
    assert isinstance(client.start(call, 2.0), Send)
    inner.action = GiveUp("no_provider_available")
    return client, inner, call, Attempt(call, "provider", 1, 2.0, None)


def test_invalidation_during_provider_attempt_is_rechecked_before_stale_serve() -> None:
    client, inner, _, attempt = running_request()
    client.on_content_update("shared/source", 2.5)
    result = client.on_error(attempt, ProviderError("provider", 503, "service_unavailable"), 3.0)
    assert isinstance(result, GiveUp)
    assert inner.updates == ["shared/source"]


def test_stale_entry_that_expires_during_provider_attempt_is_not_served() -> None:
    client, _, _, attempt = running_request()
    result = client.on_error(attempt, ProviderError("provider", 503, "service_unavailable"), 11.1)
    assert isinstance(result, GiveUp)
    assert client.cache.entries == []


def test_concurrent_refresh_is_rechecked_and_served_as_fresh() -> None:
    client, _, _, attempt = running_request()
    fresh_answer = answer(2)
    client.cache.store(request(), fresh_answer, 3.0)
    result = client.on_error(attempt, ProviderError("provider", 503, "service_unavailable"), 3.5)
    assert isinstance(result, Serve) and result.answer == fresh_answer and not result.stale


def test_hits_update_lru_but_do_not_extend_ttl_or_stale_lifetime() -> None:
    cache = SemanticCache(ttl_s=10.0, max_stale_s=10.0)
    cache.store(request(), answer(), 0.0)
    assert cache.lookup(request(), 9.0) is not None
    stale = cache.lookup(request(), 11.0)
    assert stale is not None and not stale.fresh and stale.age_s == 11.0
    assert cache.lookup(request(), 20.0) is not None
    assert cache.lookup(request(), 20.1) is None


def test_store_keeps_prompt_scopes_separate_and_rejects_mismatched_answer() -> None:
    cache = SemanticCache()
    v1, v2 = answer(1), answer(2, "v2")
    cache.store(request(), v1, 0.0)
    cache.store(request("v2"), v2, 1.0)
    cache.store(request("v2"), answer(3, "v1"), 2.0)
    assert len(cache.entries) == 2
    hit_v1, hit_v2 = cache.lookup(request(), 3.0), cache.lookup(request("v2"), 3.0)
    assert hit_v1 is not None and hit_v1.answer == v1
    assert hit_v2 is not None and hit_v2.answer == v2


def test_source_invalidation_removes_fresh_and_stale_entries_in_all_scopes() -> None:
    cache = SemanticCache(ttl_s=2.0, max_stale_s=20.0)
    cache.store(request(), answer(), 0.0)
    cache.store(request("v2"), answer(2, "v2"), 4.0)
    assert cache.invalidate("shared/source", 5.0) == 2
    assert cache.entries == []
    assert cache.invalidate("shared/source", 6.0) == 0
