"""Delayed Student Detection Service — Issue #93.

Identifies students whose completed ECTS credits fall below their
expected academic progress milestone.

Detection Rule (confirmed from risk_policy.py and progress_service.py):
    is_delayed = completed_ects < expected_ects
    delay_ects = max(expected_ects - completed_ects, 0)

    Equality (completed == expected) → NOT delayed (ON_TRACK).
    Ahead (completed > expected)     → NOT delayed, delay_ects = 0.
    No tolerance threshold — any deficit triggers delayed status.

Sign convention:
    difference_ects = completed_ects - expected_ects  (signed, project standard)
    delay_ects      = max(expected_ects - completed_ects, 0)  (non-negative, #93)

Dependencies:
    #91 EctsAnalyticsService  → authoritative completed_ects
    #92 ExpectedProgressService → authoritative expected_ects

Both are consumed via ProgressService which returns them together in one call,
avoiding N+1 queries.

Architecture:
    Database
        ↓
    ProgressRepository
        ↓
    ProgressService  (#91 completed, #92 expected — single call)
        ↓
    DelayDetectionService  ← this file
        ↓
    Future MCP / Agents / #94 Study Right Risk / #95 Risk Scoring

Out of scope:
    Risk levels (LOW/MEDIUM/HIGH) → #95
    Academic Health Score         → #96
    Recommendations               → later issues
    Study right risk              → #94
"""

from __future__ import annotations

from typing import Any

from app.services.progress_service import ProgressService


# ── Pure detection rule ───────────────────────────────────────────────────────

def detect_delay(
    completed_ects: int,
    expected_ects: int,
) -> dict[str, Any]:
    """Apply the delay detection rule to pre-calculated ECTS values.

    This is a pure, deterministic function with no database access.
    It can be unit-tested in complete isolation.

    Confirmed rule (from risk_policy.py and progress_service.py):
        is_delayed = completed_ects < expected_ects
        delay_ects = max(expected_ects - completed_ects, 0)

    Args:
        completed_ects: Student's total completed ECTS (from #91).
        expected_ects: Expected ECTS milestone for current semester (from #92).

    Returns:
        Dict with:
        - is_delayed (bool): True if completed < expected.
        - delay_ects (int): Non-negative ECTS deficit. Zero if not delayed.
        - difference_ects (int): Signed difference (completed - expected).
          Negative when delayed, positive when ahead, zero when on track.
    """
    difference_ects = completed_ects - expected_ects
    is_delayed = completed_ects < expected_ects
    delay_ects = max(expected_ects - completed_ects, 0)

    return {
        "is_delayed": is_delayed,
        "delay_ects": delay_ects,
        "difference_ects": difference_ects,
    }


# ── Service layer ─────────────────────────────────────────────────────────────

class DelayDetectionService:
    """Orchestrates delayed-student detection for a student.

    Consumes ProgressService which provides both completed_ects (#91)
    and expected_ects (#92) in a single database call, then applies
    the approved detection rule.

    Does NOT recalculate completed_ects or expected_ects independently.
    Does NOT add risk levels, risk scores, or recommendations.
    Does NOT access the database directly.

    Args:
        progress_service: ProgressService instance providing combined
                          completed and expected ECTS data.
    """

    def __init__(self, progress_service: ProgressService) -> None:
        self._progress_service = progress_service

    def detect_student_delay(self, student_id: int) -> dict[str, Any]:
        """Detect whether a student is behind expected academic progress.

        Retrieves combined progress data (completed + expected ECTS) via
        ProgressService, then applies the deterministic detection rule.

        Args:
            student_id: The numeric database ID of the student.

        Returns:
            A dict with:
            - success (bool): True on success.
            - delay (dict): Detection result containing:
                - student_id (int)
                - student_number (str)
                - student_name (str)
                - programme (str)
                - current_semester (int)
                - completed_ects (int): from #91 via ProgressService
                - expected_ects (int): from #92 via ProgressService
                - is_delayed (bool): True if completed < expected
                - delay_ects (int): max(expected - completed, 0)
                - difference_ects (int): completed - expected (signed)

            Returns error dict with success=False on failure.

        Error codes (propagated from ProgressService):
            INVALID_STUDENT_ID     — student_id <= 0
            STUDENT_NOT_FOUND      — no student row exists
            CURRICULUM_NOT_FOUND   — no curriculum rows for programme
        """
        # ProgressService already validates student_id
        progress_result = self._progress_service.get_progress(student_id)

        if not progress_result.get("success"):
            return progress_result

        progress = progress_result["progress"]
        completed_ects = int(progress.get("completed_ects", 0) or 0)
        expected_ects = int(progress.get("expected_ects", 0) or 0)

        # Apply pure detection rule
        detection = detect_delay(
            completed_ects=completed_ects,
            expected_ects=expected_ects,
        )

        return {
            "success": True,
            "delay": {
                "student_id": progress.get("student_id"),
                "student_number": progress.get("student_number", ""),
                "student_name": progress.get("student_name", ""),
                "programme": progress.get("programme", ""),
                "current_semester": progress.get("current_semester"),
                "completed_ects": completed_ects,
                "expected_ects": expected_ects,
                "is_delayed": detection["is_delayed"],
                "delay_ects": detection["delay_ects"],
                "difference_ects": detection["difference_ects"],
            },
        }
