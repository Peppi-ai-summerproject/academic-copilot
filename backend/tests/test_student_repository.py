from unittest.mock import Mock

from app.repositories.student_repository import StudentRepository


def test_get_by_id_returns_student_mapping() -> None:
    session = Mock()

    row = {
        "id": 1,
        "student_number": "S001",
        "name": "Mikael Virtanen",
        "group_name": "TT21A",
        "programme": "Business IT",
        "start_date": "2021-09-01",
        "status": "ACTIVE",
        "programme_code": "DIN2024S",
    }

    session.execute.return_value.mappings.return_value.first.return_value = row

    repository = StudentRepository(session)

    result = repository.get_by_id(1)

    assert result == row
    session.execute.assert_called_once()


def test_get_by_id_returns_none_when_student_is_missing() -> None:
    session = Mock()
    session.execute.return_value.mappings.return_value.first.return_value = None

    repository = StudentRepository(session)

    result = repository.get_by_id(999)

    assert result is None


# ── search_students tests ─────────────────────────────────────────────────────

def _make_session_with_rows(rows: list[dict], total: int) -> "Mock":
    from unittest.mock import Mock
    session = Mock()

    count_result = Mock()
    count_result.scalar.return_value = total

    rows_result = Mock()
    rows_result.mappings.return_value.all.return_value = rows

    session.execute.side_effect = [count_result, rows_result]
    return session


def test_search_students_returns_matching_rows() -> None:
    from unittest.mock import Mock
    rows = [
        {
            "id": 1,
            "student_number": "S001",
            "name": "Mikael Virtanen",
            "group_name": "TT21A",
            "programme": "Business IT",
            "start_date": "2021-09-01",
            "status": "ACTIVE",
            "programme_code": "DIN2024S",
        }
    ]
    session = _make_session_with_rows(rows, total=1)
    repository = StudentRepository(session)

    result, total = repository.search_students(query="mikael")

    assert total == 1
    assert len(result) == 1
    assert result[0]["name"] == "Mikael Virtanen"


def test_search_students_returns_empty_list_when_no_match() -> None:
    session = _make_session_with_rows([], total=0)
    repository = StudentRepository(session)

    result, total = repository.search_students(query="zzznonexistent")

    assert total == 0
    assert result == []


def test_search_students_no_query_returns_all_students() -> None:
    rows = [
        {"id": 1, "student_number": "S001", "name": "Aino Mäkinen",
         "group_name": "TT21A", "programme": "Business IT",
         "start_date": "2021-09-01", "status": "ACTIVE", "programme_code": "DIN2024S"},
        {"id": 2, "student_number": "S002", "name": "Mikael Virtanen",
         "group_name": "TT21A", "programme": "Business IT",
         "start_date": "2021-09-01", "status": "ACTIVE", "programme_code": "DIN2024S"},
    ]
    session = _make_session_with_rows(rows, total=2)
    repository = StudentRepository(session)

    result, total = repository.search_students()

    assert total == 2
    assert len(result) == 2


def test_search_students_programme_code_filter() -> None:
    rows = [
        {"id": 3, "student_number": "S003", "name": "Liisa Järvinen",
         "group_name": "DE22A", "programme": "Data Engineering",
         "start_date": "2022-09-01", "status": "ACTIVE", "programme_code": "DE2022"}
    ]
    session = _make_session_with_rows(rows, total=1)
    repository = StudentRepository(session)

    result, total = repository.search_students(programme_code="DE2022")

    assert total == 1
    assert result[0]["programme_code"] == "DE2022"
    call_args = str(session.execute.call_args_list)
    assert "programme_code" in call_args


def test_search_students_group_name_filter() -> None:
    rows = [
        {"id": 1, "student_number": "S001", "name": "Mikael Virtanen",
         "group_name": "TT21A", "programme": "Business IT",
         "start_date": "2021-09-01", "status": "ACTIVE", "programme_code": "DIN2024S"}
    ]
    session = _make_session_with_rows(rows, total=1)
    repository = StudentRepository(session)

    result, total = repository.search_students(group_name="TT21A")

    assert total == 1
    assert result[0]["group_name"] == "TT21A"


def test_search_students_limit_and_offset_passed() -> None:
    session = _make_session_with_rows([], total=0)
    repository = StudentRepository(session)

    repository.search_students(limit=5, offset=10)

    call_args = str(session.execute.call_args_list)
    assert "5" in call_args
    assert "10" in call_args


def test_search_students_execute_called_twice() -> None:
    """Repository makes two queries: count then rows."""
    session = _make_session_with_rows([], total=0)
    repository = StudentRepository(session)

    repository.search_students(query="test")

    assert session.execute.call_count == 2


def test_search_students_returns_list_of_dicts() -> None:
    rows = [
        {"id": 1, "student_number": "S001", "name": "Mikael Virtanen",
         "group_name": "TT21A", "programme": "Business IT",
         "start_date": "2021-09-01", "status": "ACTIVE", "programme_code": "DIN2024S"}
    ]
    session = _make_session_with_rows(rows, total=1)
    repository = StudentRepository(session)

    result, _ = repository.search_students()

    assert isinstance(result, list)
    assert isinstance(result[0], dict)


def test_list_active_student_ids_uses_canonical_active_status_and_id_order() -> None:
    session = Mock()
    session.execute.return_value.mappings.return_value.all.return_value = [
        {"id": 2},
        {"id": 5},
    ]
    repository = StudentRepository(session)

    result = repository.list_active_student_ids()

    assert result == [2, 5]
    _, parameters = session.execute.call_args.args
    assert parameters == {"active_status": "ACTIVE"}
    assert "status = :active_status" in str(session.execute.call_args.args[0])


def test_list_active_student_ids_intersects_requested_ids_with_active_students() -> None:
    session = Mock()
    session.execute.return_value.mappings.return_value.all.return_value = [{"id": 3}]
    repository = StudentRepository(session)

    result = repository.list_active_student_ids([9, 3, 3, 0, True])

    assert result == [3]
    _, parameters = session.execute.call_args.args
    assert parameters == {"active_status": "ACTIVE", "student_ids": [3, 9]}

