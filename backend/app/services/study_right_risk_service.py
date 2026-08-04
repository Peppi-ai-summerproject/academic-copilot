"""Study Right Risk Detection Service — Issue #94.

Identifies students whose study rights are approaching expiration
or require immediate attention.

Detection Rules (confirmed from risk_policy.py and study_rights table):
    The project uses persisted status values as the authoritative risk signal.
    No numeric day thresholds exist in the codebase — the database status
    field encodes the administrative decision about expiration urgency.

    Status-based risk classification:
        EXPIRED       → risk_status = EXPIRED,        requires_attention = True
        EXPIRES_SOON  → risk_status = EXPIRING_SOON,  requires_attention = True
        EXTENDED      → risk_status = EXTENDED,        requires_attention = True
        ACTIVE        → risk_status = SAFE,            requires_attention = False
        GRADUATED     → risk_status = SAFE,            requires_attention = False
        other/unknown → risk_status = UNKNOWN,         requires_attention = False

    Date-based analysis (using explicit as_of_date):
        days_until_expiration = end_date - as_of_date
        Negative value means already expired.
        Provided alongside status for downstream consumers (#95, Agents).

    Alert generation:
        An alert is a structured dict returned by the service.
        Alerts are NOT persisted. Alerts are NOT sent externally.
        Alerts are NOT Telegram messages, emails, or notifications.

Architecture:
    Database
        ↓
    StudyRightRepository
        ↓
    StudyRightService (existing)
        ↓
    StudyRightRiskService  ← this file
        ↓
    Future: #95 Risk Scoring, MCP tools, Agents, APIs

Out of scope:
    Numeric day thresholds (#94 uses persisted status — no thresholds to invent)
    Risk score (#95)
    Academic Health Score (#96)
    Recommendations
    External notifications
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.services.study_right_service import StudyRightService
from app.services.student_service import StudentService


# ── Risk status codes ─────────────────────────────────────────────────────────
# Machine-readable classification codes used in alert results.

RISK_STATUS_EXPIRED = "EXPIRED"
RISK_STATUS_EXPIRING_SOON = "EXPIRING_SOON"
RISK_STATUS_EXTENDED = "EXTENDED"
RISK_STATUS_SAFE = "SAFE"
RISK_STATUS_UNKNOWN = "UNKNOWN"

# Alert codes (machine-readable, stable identifiers for downstream consumers)
ALERT_CODE_EXPIRED = "STUDY_RIGHT_EXPIRED"
ALERT_CODE_EXPIRING_SOON = "STUDY_RIGHT_EXPIRING_SOON"
ALERT_CODE_EXTENDED = "STUDY_RIGHT_EXTENDED"

# Statuses that require attention
_AT_RISK_STATUSES = frozenset({"EXPIRED", "EXPIRES_SOON", "EXTENDED"})
_SAFE_STATUSES = frozenset({"ACTIVE", "GRADUATED"})


# ── Pure date analysis ────────────────────────────────────────────────────────

def analyze_study_right_expiration(
    end_date: date | None,
    as_of_date: date,
) -> dict[str, Any]:
    """Analyze study right expiration date relative to a reference date.

    Pure deterministic function — no database access, no side effects.
    Accepts an explicit as_of_date for deterministic testing.

    Args:
        end_date: The study right expiration date from the database.
                  None if the expiration date is missing or unknown.
        as_of_date: The reference date for the calculation.

    Returns:
        Dict with:
        - has_end_date (bool): False if end_date is None.
        - days_until_expiration (int | None): end_date - as_of_date in days.
          Negative when already expired. None when end_date is missing.
        - is_date_expired (bool): True if end_date < as_of_date.
        - is_date_expiring_today (bool): True if end_date == as_of_date.
    """
    if end_date is None:
        return {
            "has_end_date": False,
            "days_until_expiration": None,
            "is_date_expired": False,
            "is_date_expiring_today": False,
        }

    days_until = (end_date - as_of_date).days

    return {
        "has_end_date": True,
        "days_until_expiration": days_until,
        "is_date_expired": days_until < 0,
        "is_date_expiring_today": days_until == 0,
    }


# ── Pure risk classification ───────────────────────────────────────────────────

def classify_study_right_risk(
    status: str | None,
    date_analysis: dict[str, Any],
) -> dict[str, Any]:
    """Classify study right risk from persisted status and date analysis.

    Uses the project's established pattern: persisted status is the
    authoritative risk signal. Date analysis provides supporting evidence.

    No numeric day thresholds are used — none exist in the project.

    Args:
        status: Persisted study right status from the database.
        date_analysis: Result from analyze_study_right_expiration().

    Returns:
        Dict with:
        - risk_status (str): Machine-readable risk classification.
        - requires_attention (bool): True if the student needs action.
        - alert_code (str | None): Machine-readable alert code, or None.
        - alert_message (str): Human-readable explanation.
    """
    normalized = (status or "").upper().strip()

    if normalized == "EXPIRED":
        days = date_analysis.get("days_until_expiration")
        overdue = abs(days) if days is not None and days < 0 else None
        overdue_str = f" ({overdue} days overdue)" if overdue is not None else ""
        return {
            "risk_status": RISK_STATUS_EXPIRED,
            "requires_attention": True,
            "alert_code": ALERT_CODE_EXPIRED,
            "alert_message": f"Study right has expired{overdue_str}. Immediate administrative action required.",
        }

    if normalized == "EXPIRES_SOON":
        days = date_analysis.get("days_until_expiration")
        days_str = f" ({days} days remaining)" if days is not None else ""
        return {
            "risk_status": RISK_STATUS_EXPIRING_SOON,
            "requires_attention": True,
            "alert_code": ALERT_CODE_EXPIRING_SOON,
            "alert_message": f"Study right is expiring soon{days_str}. Student should be contacted urgently.",
        }

    if normalized == "EXTENDED":
        return {
            "risk_status": RISK_STATUS_EXTENDED,
            "requires_attention": True,
            "alert_code": ALERT_CODE_EXTENDED,
            "alert_message": "Study right has been extended. Monitor progress closely.",
        }

    if normalized in _SAFE_STATUSES:
        return {
            "risk_status": RISK_STATUS_SAFE,
            "requires_attention": False,
            "alert_code": None,
            "alert_message": "Study right is active. No expiration risk detected.",
        }

    # Unknown or missing status
    return {
        "risk_status": RISK_STATUS_UNKNOWN,
        "requires_attention": False,
        "alert_code": None,
        "alert_message": f"Study right status is unknown or unrecognised: '{status}'.",
    }


# ── Service layer ─────────────────────────────────────────────────────────────

class StudyRightRiskService:
    """Detects study right expiration risks for students.

    Composes StudyRightService (existing) to retrieve study right data,
    then applies deterministic risk classification.

    Does NOT call any LLM.
    Does NOT send external notifications.
    Does NOT persist alert records.
    Does NOT implement Risk Scoring (#95).
    Does NOT combine with ECTS delay risk (#93).

    Alerts are structured dicts returned to the caller.

    Args:
        study_right_service: Existing StudyRightService instance.
        student_service: Existing StudentService instance.
    """

    def __init__(
        self,
        study_right_service: StudyRightService,
        student_service: StudentService,
    ) -> None:
        self._study_right_service = study_right_service
        self._student_service = student_service

    def detect_study_right_risk(
        self,
        student_id: int,
        as_of_date: date | None = None,
    ) -> dict[str, Any]:
        """Detect study right expiration risk for a single student.

        Args:
            student_id: The numeric database ID of the student.
            as_of_date: Reference date for expiration calculation.
                        Defaults to today if not provided.
                        Provide explicitly for deterministic tests.

        Returns:
            A dict with:
            - success (bool): True on success.
            - risk (dict): Risk analysis containing:
                - student_id (int)
                - student_name (str)
                - programme (str)
                - as_of_date (str): ISO format reference date.
                - study_right_id (int | None)
                - status (str): Persisted status from database.
                - expiration_date (str | None): ISO format end date.
                - days_until_expiration (int | None): Signed day count.
                - is_date_expired (bool)
                - is_date_expiring_today (bool)
                - risk_status (str): Machine-readable risk classification.
                - requires_attention (bool)
                - alert_code (str | None)
                - alert_message (str)
                - extension_count (int)
                - alert (dict | None): Structured alert if requires_attention.

            Returns error dict with success=False on failure.
        """
        if not isinstance(student_id, int) or student_id <= 0:
            return {
                "success": False,
                "error": "INVALID_STUDENT_ID",
                "message": "Student ID must be a positive integer.",
            }

        effective_date = as_of_date or date.today()

        # Verify student exists
        student_result = self._student_service.get_student(student_id)
        if not student_result.get("success"):
            return student_result

        student = student_result["student"]
        student_name = student.get("name", "")
        programme = student.get("programme", "")

        # Get study right
        study_right_result = self._study_right_service.get_study_right(student_id)
        if not study_right_result.get("success"):
            error = study_right_result.get("error")
            if error == "STUDY_RIGHT_NOT_FOUND":
                return {
                    "success": True,
                    "risk": {
                        "student_id": student_id,
                        "student_name": student_name,
                        "programme": programme,
                        "as_of_date": effective_date.isoformat(),
                        "study_right_id": None,
                        "status": None,
                        "expiration_date": None,
                        "days_until_expiration": None,
                        "is_date_expired": False,
                        "is_date_expiring_today": False,
                        "risk_status": RISK_STATUS_UNKNOWN,
                        "requires_attention": False,
                        "alert_code": None,
                        "alert_message": "No study right record found for this student.",
                        "extension_count": 0,
                        "alert": None,
                    },
                }
            return study_right_result

        study_right = study_right_result["study_right"]
        status = study_right.get("status")
        extension_count = int(study_right.get("extension_count", 0) or 0)
        study_right_id = study_right.get("id")

        # Get end date
        end_date_raw = study_right.get("end_date") or study_right.get("expiration_date")
        end_date = _parse_date(end_date_raw)

        # Date analysis
        date_analysis = analyze_study_right_expiration(
            end_date=end_date,
            as_of_date=effective_date,
        )

        # Risk classification
        classification = classify_study_right_risk(
            status=status,
            date_analysis=date_analysis,
        )

        # Build structured alert (only when attention required)
        alert = None
        if classification["requires_attention"] and classification["alert_code"]:
            alert = {
                "student_id": student_id,
                "student_name": student_name,
                "study_right_id": study_right_id,
                "alert_code": classification["alert_code"],
                "alert_message": classification["alert_message"],
                "risk_status": classification["risk_status"],
                "expiration_date": end_date.isoformat() if end_date else None,
                "days_until_expiration": date_analysis.get("days_until_expiration"),
                "extension_count": extension_count,
                "as_of_date": effective_date.isoformat(),
            }

        return {
            "success": True,
            "risk": {
                "student_id": student_id,
                "student_name": student_name,
                "programme": programme,
                "as_of_date": effective_date.isoformat(),
                "study_right_id": study_right_id,
                "status": status,
                "expiration_date": end_date.isoformat() if end_date else None,
                "days_until_expiration": date_analysis.get("days_until_expiration"),
                "is_date_expired": date_analysis["is_date_expired"],
                "is_date_expiring_today": date_analysis["is_date_expiring_today"],
                "risk_status": classification["risk_status"],
                "requires_attention": classification["requires_attention"],
                "alert_code": classification["alert_code"],
                "alert_message": classification["alert_message"],
                "extension_count": extension_count,
                "alert": alert,
            },
        }


def _parse_date(value: Any) -> date | None:
    """Parse a date value from various input types."""
    from datetime import datetime
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None
