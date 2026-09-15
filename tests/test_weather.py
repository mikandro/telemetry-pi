"""Tests for the TTL-cached outdoor weather source (no real network)."""

from collector.weather import OutdoorSource


def test_returns_fetched_value():
    src = OutdoorSource(fetch_fn=lambda lat, lon: (6.0, 82.0))
    assert src.current() == (6.0, 82.0)


def test_caches_within_ttl():
    calls = {"n": 0}

    def fetch(lat, lon):
        calls["n"] += 1
        return (10.0, 50.0)

    src = OutdoorSource(ttl_s=600, fetch_fn=fetch)
    src.current()
    src.current()
    assert calls["n"] == 1  # second call served from cache


def test_refetches_after_ttl():
    calls = {"n": 0}

    def fetch(lat, lon):
        calls["n"] += 1
        return (calls["n"], 50.0)

    src = OutdoorSource(ttl_s=0.0, fetch_fn=fetch)
    src.current()
    src.current()
    assert calls["n"] == 2  # TTL 0 -> refetch every call


def test_failure_returns_none_without_prior_value():
    def boom(lat, lon):
        raise OSError("network down")

    assert OutdoorSource(fetch_fn=boom).current() is None


def test_failure_keeps_last_good_value():
    state = {"ok": True}

    def flaky(lat, lon):
        if state["ok"]:
            return (7.0, 70.0)
        raise OSError("network down")

    src = OutdoorSource(ttl_s=0.0, fetch_fn=flaky)
    assert src.current() == (7.0, 70.0)
    state["ok"] = False
    assert src.current() == (7.0, 70.0)  # kept last good value on failure
