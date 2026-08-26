from __future__ import annotations

import random
from dataclasses import replace

import pytest

from tests.conftest import AlwaysFocusedGuard, FakeClock, FakeMeter, FakeSource, NeverFocusedGuard
from wow_ez_fishing.bot import FishingBot, State
from wow_ez_fishing.config import AppConfig
from wow_ez_fishing.detector import DetectionEvent
from wow_ez_fishing.input import Actions, DryRunKeyboard

SAMPLE_RATE = 1000
HOP_SIZE = 100


class FakeDetector:
    def __init__(self, schedule: dict[int, list[DetectionEvent]] | None = None) -> None:
        self.schedule = schedule or {}
        self.calls = 0
        self.frames_seen = 0
        self.primed = False

    def prime(self, ambient: object) -> float:
        self.primed = True
        return -50.0

    def push(self, frame: object) -> list[DetectionEvent]:
        self.calls += 1
        self.frames_seen += 1
        return self.schedule.get(self.calls, [])


def make_cfg(**overrides: object) -> AppConfig:
    cfg = AppConfig()
    backend = overrides.pop("backend", "loopback")
    require_focus = overrides.pop("require_focus", True)
    max_casts = overrides.pop("max_casts", 1)
    max_wait_s = overrides.pop("max_wait_s", 0.3)
    stop_after_minutes = overrides.pop("stop_after_minutes", 0)

    cfg = replace(cfg, audio=replace(cfg.audio, backend=backend))
    cfg = replace(
        cfg,
        input=replace(
            cfg.input,
            cast_key="1",
            loot_key="3",
            key_hold_ms=1,
            loot_delay_ms=100,
            cast_to_arm_s=0.3,
            post_loot_s=0.1,
            recast_delay_s=0.2,
            jitter_ms=0,
            rng_seed=1,
        ),
    )
    cfg = replace(cfg, detection=replace(cfg.detection, calibration_seconds=0.05))
    cfg = replace(
        cfg,
        bot=replace(
            cfg.bot,
            require_focus=require_focus,
            max_casts=max_casts,
            max_wait_s=max_wait_s,
            stop_after_minutes=stop_after_minutes,
        ),
    )
    return cfg


def _make_bot(
    cfg: AppConfig,
    guard: object,
    detector: FakeDetector,
    meter: FakeMeter,
) -> tuple[FishingBot, DryRunKeyboard, FakeClock]:
    clock = FakeClock()
    source = FakeSource(clock, sample_rate=SAMPLE_RATE, hop_size=HOP_SIZE)
    kb = DryRunKeyboard(clock=clock)
    actions = Actions(kb, guard, cfg.input, rng=random.Random(cfg.input.rng_seed))
    bot = FishingBot(source, detector, actions, guard, meter, cfg, clock=clock)
    return bot, kb, clock


def test_bot_cast_arm_listen_loot_sequence() -> None:
    event = DetectionEvent(t=0.0, band_db=0.0, baseline_db=0.0, flux_db=0.0)
    detector = FakeDetector(schedule={6: [event]})
    guard = AlwaysFocusedGuard()
    meter = FakeMeter(available=False)
    cfg = make_cfg()

    bot, kb, _clock = _make_bot(cfg, guard, detector, meter)
    stats = bot.run()

    assert stats["casts"] == 1
    assert stats["catches"] == 1
    assert len(kb.presses) == 2
    (t1, k1), (t2, k2) = kb.presses
    assert k1 == "1"
    assert k2 == "3"
    assert t1 == pytest.approx(0.3)
    assert t2 == pytest.approx(0.8)


def test_bot_ignores_detection_during_arming() -> None:
    event = DetectionEvent(t=0.0, band_db=0.0, baseline_db=0.0, flux_db=0.0)
    detector = FakeDetector(schedule={4: [event]})
    guard = AlwaysFocusedGuard()
    meter = FakeMeter(available=False)
    cfg = make_cfg()

    bot, kb, _clock = _make_bot(cfg, guard, detector, meter)
    stats = bot.run()

    assert stats["catches"] == 0
    assert stats["misses"] == 1
    assert len(kb.presses) == 1


def test_bot_recasts_after_timeout() -> None:
    detector = FakeDetector()
    guard = AlwaysFocusedGuard()
    meter = FakeMeter(available=False)
    cfg = make_cfg(max_casts=2)

    bot, kb, _clock = _make_bot(cfg, guard, detector, meter)
    stats = bot.run()

    assert stats["casts"] == 2
    assert stats["misses"] == 2
    assert stats["catches"] == 0
    cast_presses = [p for p in kb.presses if p[1] == cfg.input.cast_key]
    assert len(cast_presses) == 2


def test_bot_sends_no_input_when_unfocused() -> None:
    detector = FakeDetector()
    guard = NeverFocusedGuard()
    meter = FakeMeter(available=False)
    cfg = make_cfg()

    bot, kb, clock = _make_bot(cfg, guard, detector, meter)
    bot._start_t = clock()
    bot.calibrate()
    result = bot._tick(State.IDLE)

    assert result is None
    assert bot.state == State.BLOCKED
    assert kb.presses == []
    assert detector.frames_seen > 0


def test_bot_detection_continues_during_key_sequence() -> None:
    event1 = DetectionEvent(t=0.0, band_db=0.0, baseline_db=0.0, flux_db=0.0)
    spurious = DetectionEvent(t=0.0, band_db=0.0, baseline_db=0.0, flux_db=0.0)
    event2 = DetectionEvent(t=0.0, band_db=0.0, baseline_db=0.0, flux_db=0.0)
    detector = FakeDetector(schedule={6: [event1], 7: [spurious], 14: [event2]})
    guard = AlwaysFocusedGuard()
    meter = FakeMeter(available=False)
    cfg = make_cfg(max_casts=2)

    bot, _kb, _clock = _make_bot(cfg, guard, detector, meter)
    stats = bot.run()

    assert stats["catches"] == 2
    assert stats["casts"] == 2
    assert stats["misses"] == 0
    assert stats["dropped_frames"] == 0
    assert detector.frames_seen >= 14


def test_hybrid_gate_rejects_when_process_silent() -> None:
    event = DetectionEvent(t=0.0, band_db=0.0, baseline_db=0.0, flux_db=0.0)
    detector = FakeDetector(schedule={6: [event]})
    guard = AlwaysFocusedGuard()
    meter = FakeMeter(available=True, peak=0.0)
    cfg = make_cfg(backend="hybrid")

    bot, _kb, _clock = _make_bot(cfg, guard, detector, meter)
    stats = bot.run()

    assert stats["gated"] == 1
    assert stats["catches"] == 0
    assert stats["misses"] == 1


def test_hybrid_gate_noop_when_meter_unavailable() -> None:
    event = DetectionEvent(t=0.0, band_db=0.0, baseline_db=0.0, flux_db=0.0)
    detector = FakeDetector(schedule={6: [event]})
    guard = AlwaysFocusedGuard()
    meter = FakeMeter(available=False, peak=0.0)
    cfg = make_cfg(backend="hybrid")

    bot, _kb, _clock = _make_bot(cfg, guard, detector, meter)
    stats = bot.run()

    assert stats["gated"] == 0
    assert stats["catches"] == 1
