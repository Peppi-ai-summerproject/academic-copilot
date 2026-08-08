"""Safe, deterministic load runner for representative FastAPI routes.

This module always uses HTTPX's in-process ASGI transport. It cannot target a
remote host and deliberately replaces database/workflow boundaries with local
test doubles. Run it explicitly; normal pytest collection does not execute load.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path
from statistics import fmean, median
from time import perf_counter
from typing import Any, Callable

import httpx

from app.api.dependencies import (
    get_health_service,
    get_student_dashboard_service,
)
from app.main import app


BASE_URL = "http://load-test.local"


class LocalHealthService:
    def get_status(self) -> dict[str, str]:
        return {"status": "healthy"}


class LocalDashboardService:
    def get_student_dashboard(
        self,
        student_id: int,
        *,
        as_of_date: Any = None,
    ) -> dict[str, Any]:
        return {
            "success": True,
            "student_id": student_id,
            "dashboard": {
                "profile": {"student_id": student_id},
                "academic_progress": {
                    "completed_ects": 90,
                    "expected_ects": 120,
                    "status": "BEHIND",
                },
                "summary": {
                    "overall_status": "NEEDS_ATTENTION",
                    "attention_required": True,
                },
            },
        }


@dataclass(frozen=True)
class RequestSpec:
    name: str
    path: str
    validate: Callable[[httpx.Response], bool]


@dataclass(frozen=True)
class Scenario:
    name: str
    requests: tuple[RequestSpec, ...]
    concurrency: int
    request_count: int
    warmup_count: int = 3


@dataclass(frozen=True)
class Result:
    scenario: str
    requests: int
    concurrency: int
    successful: int
    failed: int
    error_rate: float
    duration_seconds: float
    requests_per_second: float
    minimum_ms: float
    average_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    maximum_ms: float
    post_load_healthy: bool
    errors: tuple[str, ...]


def _valid_root(response: httpx.Response) -> bool:
    body = response.json()
    return response.status_code == 200 and "message" in body


def _valid_health(response: httpx.Response) -> bool:
    return response.status_code == 200 and response.json() == {"status": "healthy"}


def _valid_dashboard(response: httpx.Response) -> bool:
    body = response.json()
    return (
        response.status_code == 200
        and body.get("success") is True
        and body.get("student_id") == 1
        and body.get("dashboard", {}).get("profile", {}).get("student_id") == 1
    )


ROOT = RequestSpec("root", "/", _valid_root)
HEALTH = RequestSpec("health", "/api/v1/health/health/", _valid_health)
DASHBOARD = RequestSpec(
    "progress-dashboard",
    "/api/v1/students/1/progress-dashboard",
    _valid_dashboard,
)

DEFAULT_SCENARIOS = (
    Scenario("light-root", (ROOT,), concurrency=5, request_count=100),
    Scenario("moderate-health", (HEALTH,), concurrency=10, request_count=200),
    Scenario("dashboard-route", (DASHBOARD,), concurrency=10, request_count=200),
    Scenario(
        "mixed-routes",
        (ROOT, HEALTH, DASHBOARD),
        concurrency=15,
        request_count=300,
    ),
)


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


async def _request(
    client: httpx.AsyncClient,
    spec: RequestSpec,
) -> tuple[float, str | None]:
    started = perf_counter()
    try:
        response = await client.get(spec.path)
        elapsed_ms = (perf_counter() - started) * 1_000
        if not spec.validate(response):
            return elapsed_ms, f"{spec.name}: incorrect HTTP {response.status_code} response"
        return elapsed_ms, None
    except Exception as exc:  # load runner must count transport/app failures
        elapsed_ms = (perf_counter() - started) * 1_000
        return elapsed_ms, f"{spec.name}: {type(exc).__name__}: {exc}"


async def run_scenario(
    client: httpx.AsyncClient,
    scenario: Scenario,
) -> Result:
    for index in range(scenario.warmup_count):
        await _request(client, scenario.requests[index % len(scenario.requests)])

    queue: asyncio.Queue[tuple[int, RequestSpec]] = asyncio.Queue()
    for index in range(scenario.request_count):
        queue.put_nowait((index, scenario.requests[index % len(scenario.requests)]))

    latencies: list[float] = []
    errors: list[str] = []

    async def worker() -> None:
        while not queue.empty():
            try:
                _, spec = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            latency, error = await _request(client, spec)
            latencies.append(latency)
            if error is not None:
                errors.append(error)
            queue.task_done()

    started = perf_counter()
    await asyncio.gather(
        *(worker() for _ in range(min(scenario.concurrency, scenario.request_count)))
    )
    duration = perf_counter() - started
    successful = scenario.request_count - len(errors)

    return Result(
        scenario=scenario.name,
        requests=scenario.request_count,
        concurrency=scenario.concurrency,
        successful=successful,
        failed=len(errors),
        error_rate=len(errors) / scenario.request_count,
        duration_seconds=duration,
        requests_per_second=scenario.request_count / duration,
        minimum_ms=min(latencies),
        average_ms=fmean(latencies),
        p50_ms=median(latencies),
        p95_ms=_percentile(latencies, 0.95),
        p99_ms=_percentile(latencies, 0.99),
        maximum_ms=max(latencies),
        post_load_healthy=False,
        errors=tuple(errors[:10]),
    )


async def run_all(
    scenarios: tuple[Scenario, ...] = DEFAULT_SCENARIOS,
) -> list[Result]:
    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_health_service] = LocalHealthService
    app.dependency_overrides[get_student_dashboard_service] = LocalDashboardService
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(
            transport=transport,
            base_url=BASE_URL,
            timeout=10.0,
        ) as client:
            results = []
            for scenario in scenarios:
                result = await run_scenario(client, scenario)
                post_load_response = await client.get(HEALTH.path)
                post_load_healthy = HEALTH.validate(post_load_response)
                results.append(replace(result, post_load_healthy=post_load_healthy))
            return results
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run 12 mixed requests at concurrency 3.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON results path.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    scenarios = (
        Scenario(
            "smoke",
            (ROOT, HEALTH, DASHBOARD),
            concurrency=3,
            request_count=12,
            warmup_count=1,
        ),
    ) if args.smoke else DEFAULT_SCENARIOS
    payload = [asdict(result) for result in asyncio.run(run_all(scenarios))]
    rendered = json.dumps(payload, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
