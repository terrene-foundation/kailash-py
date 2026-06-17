"""Tier-1 unit tests for CrossChannelSession TTL semantics (#1336 / parity #1349).

Covers the three capabilities the gateway-parity assessment flagged:
  - remaining_ttl() accessor (both expires_at and idle modes)
  - sliding-TTL on access (touch / get_session re-slide when ttl configured)
  - backward-compat (no-window sessions unchanged; fixed-deadline not slid)

Pure logic; uses a controlled clock via monkeypatching time.time so the
sliding behavior is asserted deterministically without real sleeps.
"""

import pytest

from kailash.channels.session import CrossChannelSession, SessionManager, SessionStatus


class _Clock:
    """Deterministic monotonic clock the tests advance explicitly."""

    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    # Patch the time.time symbol the session module resolves at call time.
    monkeypatch.setattr("kailash.channels.session.time.time", c)
    return c


# --------------------------------------------------------------------------- #
# remaining_ttl() — expires_at (fixed deadline) mode
# --------------------------------------------------------------------------- #


def test_remaining_ttl_expires_at_mode(clock):
    s = CrossChannelSession(session_id="s1")
    s.expires_at = clock.now + 600  # 10-minute fixed deadline
    assert s.remaining_ttl() == pytest.approx(600.0)

    clock.advance(250)
    assert s.remaining_ttl() == pytest.approx(350.0)


def test_remaining_ttl_floors_at_zero_when_past_deadline(clock):
    s = CrossChannelSession(session_id="s1")
    s.expires_at = clock.now + 100
    clock.advance(500)  # well past the deadline
    assert s.remaining_ttl() == 0.0
    # Agreement contract: remaining_ttl == 0 iff is_expired is True.
    assert s.is_expired() is True


# --------------------------------------------------------------------------- #
# remaining_ttl() — idle mode (no expires_at)
# --------------------------------------------------------------------------- #


def test_remaining_ttl_idle_mode(clock):
    s = CrossChannelSession(session_id="s1")  # no expires_at
    # Baseline last_activity onto the controlled clock (the dataclass
    # default_factory captures the real builtin at construction).
    s.last_activity = clock.now
    assert s.remaining_ttl(timeout=3600) == pytest.approx(3600.0)

    clock.advance(1000)
    assert s.remaining_ttl(timeout=3600) == pytest.approx(2600.0)


def test_remaining_ttl_idle_agrees_with_is_expired(clock):
    s = CrossChannelSession(session_id="s1")
    s.last_activity = clock.now
    clock.advance(4000)  # past the 3600 idle timeout
    assert s.remaining_ttl(timeout=3600) == 0.0
    assert s.is_expired(timeout=3600) is True


# --------------------------------------------------------------------------- #
# Sliding-TTL on access — touch() re-slides when ttl configured
# --------------------------------------------------------------------------- #


def test_touch_reslides_expires_at_when_ttl_set(clock):
    s = CrossChannelSession(session_id="s1", ttl=300)
    s.expires_at = clock.now + 300
    assert s.remaining_ttl() == pytest.approx(300.0)

    clock.advance(200)  # 100s left without sliding
    assert s.remaining_ttl() == pytest.approx(100.0)

    s.touch()  # access re-slides the deadline to now + ttl
    assert s.remaining_ttl() == pytest.approx(300.0)
    assert s.expires_at == pytest.approx(clock.now + 300)


def test_mutation_reslides_via_touch(clock):
    s = CrossChannelSession(session_id="s1", ttl=300)
    s.expires_at = clock.now + 300
    clock.advance(250)
    s.set_shared_data("k", "v")  # mutator calls touch()
    assert s.remaining_ttl() == pytest.approx(300.0)


def test_get_session_reslides_ttl_session(clock):
    mgr = SessionManager(default_timeout=3600)
    s = mgr.create_session(session_id="s1", sliding_ttl=300)
    assert s.ttl == 300
    assert s.remaining_ttl() == pytest.approx(300.0)

    clock.advance(250)  # 50s left
    fetched = mgr.get_session("s1")
    assert fetched is not None
    # Access re-slid the window back to the full 300s.
    assert fetched.remaining_ttl() == pytest.approx(300.0)


def test_sliding_session_expires_without_access(clock):
    mgr = SessionManager(default_timeout=3600)
    mgr.create_session(session_id="s1", sliding_ttl=300)
    clock.advance(400)  # no access within the window
    assert mgr.get_session("s1") is None  # expired + evicted


# --------------------------------------------------------------------------- #
# Backward-compat — fixed-deadline + idle sessions are NOT silently slid
# --------------------------------------------------------------------------- #


def test_fixed_deadline_does_not_slide_on_touch(clock):
    # create_session(timeout=...) is the existing fixed-deadline API: ttl stays None.
    mgr = SessionManager()
    s = mgr.create_session(session_id="s1", timeout=300)
    assert s.ttl is None
    deadline = s.expires_at

    clock.advance(200)
    s.touch()  # touch MUST NOT move a fixed deadline
    assert s.expires_at == deadline
    assert s.remaining_ttl() == pytest.approx(100.0)


def test_get_session_does_not_slide_fixed_deadline(clock):
    mgr = SessionManager()
    mgr.create_session(session_id="s1", timeout=300)
    clock.advance(200)
    s = mgr.get_session("s1")
    assert s is not None
    assert s.remaining_ttl() == pytest.approx(100.0)  # not re-slid to 300


def test_idle_session_unaffected_by_ttl_logic(clock):
    s = CrossChannelSession(session_id="s1")  # no expires_at, no ttl
    clock.advance(100)
    s.touch()  # updates last_activity only; no expires_at materialized
    assert s.expires_at is None
    assert s.ttl is None
    assert s.remaining_ttl(timeout=3600) == pytest.approx(3600.0)


def test_create_session_rejects_both_timeout_and_sliding_ttl():
    mgr = SessionManager()
    with pytest.raises(ValueError, match="not both"):
        mgr.create_session(session_id="s1", timeout=300, sliding_ttl=300)


def test_to_dict_includes_ttl(clock):
    mgr = SessionManager()
    s = mgr.create_session(session_id="s1", sliding_ttl=120)
    d = s.to_dict()
    assert d["ttl"] == 120
    assert d["expires_at"] == pytest.approx(clock.now + 120)


def test_status_active_after_touch_reslide(clock):
    s = CrossChannelSession(session_id="s1", ttl=300)
    s.expires_at = clock.now + 300
    s.status = SessionStatus.IDLE
    s.touch()
    assert s.status == SessionStatus.ACTIVE
