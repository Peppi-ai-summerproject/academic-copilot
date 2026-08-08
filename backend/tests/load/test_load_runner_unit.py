from __future__ import annotations

import asyncio

from backend.tests.load.runner import (
    HEALTH,
    ROOT,
    Scenario,
    _percentile,
    run_all,
)


def test_percentile_interpolates_ordered_latency_values() -> None:
    assert _percentile([40.0, 10.0, 30.0, 20.0], 0.5) == 25.0
    assert _percentile([40.0, 10.0, 30.0, 20.0], 0.95) == 38.5


def test_smoke_run_counts_requests_and_validates_responses() -> None:
    scenario = Scenario(
        "unit-smoke",
        (ROOT, HEALTH),
        concurrency=2,
        request_count=6,
        warmup_count=1,
    )

    result = asyncio.run(run_all((scenario,)))[0]

    assert result.requests == 6
    assert result.successful == 6
    assert result.failed == 0
    assert result.error_rate == 0
    assert result.duration_seconds > 0
    assert result.requests_per_second > 0
    assert result.post_load_healthy is True
    assert result.minimum_ms <= result.p50_ms <= result.p95_ms
    assert result.p95_ms <= result.p99_ms <= result.maximum_ms
