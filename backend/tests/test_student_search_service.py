"""Unit tests for StudentSearchService — Issue #76."""

from unittest.mock import Mock

import pytest

from app.services.student_search_service import StudentSearchService


def _make_service(rows=None, total=0):
    repository = Mock()
    repository.search_students.return_value = (rows or [], total)
    return StudentSearchService(repository), repository


def _student_row(**kwargs):
    defaults = {
        "id": 1, "student_number": "S001", "name": "Mikael Virtanen",
        "group_name": "TT21A", "programme": "Business IT",
        "start_date": "2021-09-01", "status": "ACTIVE",
        "programme_code": "DIN2024S",
    }
    return {**defaults, **kwargs}


# ── Input normalization ───────────────────────────────────────────────────────

def test_whitespace_query_is_normalized_to_none() -> None:
    service, repo = _make_service()
    service.search_students(query="   ")
    repo.search_students.assert_called_once()
    call_kwargs = repo.search_students.call_args.kwargs
    assert call_kwargs["query"] is None


def test_query_is_stripped() -> None:
    service, repo = _make_service()
    service.search_students(query="  anna  ")
    call_kwargs = repo.search_students.call_args.kwargs
    assert call_kwargs["query"] == "anna"


def test_none_query_passed_as_none() -> None:
    service, repo = _make_service()
    service.search_students(query=None)
    call_kwargs = repo.search_students.call_args.kwargs
    assert call_kwargs["query"] is None


def test_programme_code_is_stripped() -> None:
    service, repo = _make_service()
    service.search_students(programme_code="  DIN2024S  ")
    call_kwargs = repo.search_students.call_args.kwargs
    assert call_kwargs["programme_code"] == "DIN2024S"


def test_empty_programme_code_becomes_none() -> None:
    service, repo = _make_service()
    service.search_students(programme_code="  ")
    call_kwargs = repo.search_students.call_args.kwargs
    assert call_kwargs["programme_code"] is None


def test_group_name_is_stripped() -> None:
    service, repo = _make_service()
    service.search_students(group_name="  TT21A  ")
    call_kwargs = repo.search_students.call_args.kwargs
    assert call_kwargs["group_name"] == "TT21A"


# ── Validation ────────────────────────────────────────────────────────────────

def test_limit_zero_returns_error() -> None:
    service, _ = _make_service()
    result = service.search_students(limit=0)
    assert result["success"] is False
    assert result["error"] == "INVALID_SEARCH_PARAMETERS"
    assert "limit" in result["message"]


def test_negative_limit_returns_error() -> None:
    service, _ = _make_service()
    result = service.search_students(limit=-1)
    assert result["success"] is False
    assert result["error"] == "INVALID_SEARCH_PARAMETERS"


def test_limit_above_max_is_clamped_to_100() -> None:
    service, repo = _make_service()
    service.search_students(limit=999)
    call_kwargs = repo.search_students.call_args.kwargs
    assert call_kwargs["limit"] == 100


def test_negative_offset_returns_error() -> None:
    service, _ = _make_service()
    result = service.search_students(offset=-1)
    assert result["success"] is False
    assert result["error"] == "INVALID_SEARCH_PARAMETERS"
    assert "offset" in result["message"]


# ── Response structure ────────────────────────────────────────────────────────

def test_success_response_structure() -> None:
    row = _student_row()
    service, _ = _make_service(rows=[row], total=1)
    result = service.search_students(query="mikael")
    assert result["success"] is True
    assert "query" in result
    assert "pagination" in result
    assert "students" in result


def test_query_metadata_in_response() -> None:
    service, _ = _make_service()
    result = service.search_students(query="anna", programme_code="DIN2024S", limit=10, offset=5)
    assert result["query"]["text"] == "anna"
    assert result["query"]["programme_code"] == "DIN2024S"
    assert result["query"]["limit"] == 10
    assert result["query"]["offset"] == 5


def test_pagination_metadata_correct() -> None:
    rows = [_student_row(id=i, student_number=f"S{i:03d}") for i in range(1, 6)]
    service, _ = _make_service(rows=rows, total=20)
    result = service.search_students(limit=5, offset=0)
    pag = result["pagination"]
    assert pag["returned"] == 5
    assert pag["total"] == 20
    assert pag["has_more"] is True
    assert pag["limit"] == 5
    assert pag["offset"] == 0


def test_has_more_false_when_last_page() -> None:
    rows = [_student_row()]
    service, _ = _make_service(rows=rows, total=1)
    result = service.search_students(limit=20, offset=0)
    assert result["pagination"]["has_more"] is False


def test_empty_result_returns_success() -> None:
    service, _ = _make_service(rows=[], total=0)
    result = service.search_students(query="zzznonexistent")
    assert result["success"] is True
    assert result["students"] == []
    assert result["pagination"]["total"] == 0
    assert result["pagination"]["returned"] == 0
    assert result["pagination"]["has_more"] is False


def test_students_list_contains_expected_fields() -> None:
    row = _student_row()
    service, _ = _make_service(rows=[row], total=1)
    result = service.search_students()
    student = result["students"][0]
    assert "id" in student
    assert "student_number" in student
    assert "name" in student
    assert "group_name" in student
    assert "status" in student


def test_default_limit_is_20() -> None:
    service, repo = _make_service()
    service.search_students()
    call_kwargs = repo.search_students.call_args.kwargs
    assert call_kwargs["limit"] == 20


def test_default_offset_is_0() -> None:
    service, repo = _make_service()
    service.search_students()
    call_kwargs = repo.search_students.call_args.kwargs
    assert call_kwargs["offset"] == 0
