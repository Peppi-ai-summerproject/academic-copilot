from unittest.mock import Mock

from app.services.report_service import ReportService


def test_generate_report_returns_complete_academic_summary() -> None:
    student = {
        "id": 1,
        "student_number": "S001",
        "name": "Mikael Virtanen",
        "group_name": "TT21A",
        "programme": "Business IT",
        "start_date": "2021-09-01",
        "status": "ACTIVE",
        "programme_code": "DIN2024S",
    }

    progress = {
        "student_id": 1,
        "student_number": "S001",
        "student_name": "Mikael Virtanen",
        "programme": "Business IT",
        "current_semester": 4,
        "completed_ects": 90,
        "expected_ects": 120,
        "difference_ects": -30,
        "remaining_to_expected_ects": 30,
        "progress_percentage": 75.0,
        "status": "BEHIND",
    }

    study_right = {
        "id": 1,
        "student_id": 1,
        "start_date": "2021-09-01",
        "end_date": "2025-08-31",
        "status": "ACTIVE",
        "extension_count": 0,
        "expiration_date": "2025-08-31",
        "is_expiring_soon": False,
    }

    curriculum = {
        "programme": "Business IT",
        "semesters": [
            {"semester": 1, "expected_ects": 30},
            {"semester": 2, "expected_ects": 60},
            {"semester": 3, "expected_ects": 90},
            {"semester": 4, "expected_ects": 120},
        ],
        "total_expected_ects": 120,
    }

    student_service = Mock()
    progress_service = Mock()
    study_right_service = Mock()
    curriculum_service = Mock()
    event_service = Mock()

    student_service.get_student.return_value = {
        "success": True,
        "student": student,
    }
    progress_service.get_progress.return_value = {
        "success": True,
        "progress": progress,
    }
    study_right_service.get_study_right.return_value = {
        "success": True,
        "study_right": study_right,
    }
    curriculum_service.get_curriculum.return_value = {
        "success": True,
        "curriculum": curriculum,
    }
    event_service.get_upcoming_events.return_value = {
        "success": True,
        "events": [
            {
                "id": 42,
                "event_name": "Tutoring session",
                "event_type": "Workshop",
                "event_date": "2026-09-01",
                "end_date": None,
                "academic_year": "2026",
                "semester": 1,
                "description": "Orientation meeting.",
                "affects_all_students": True,
            }
        ],
    }

    service = ReportService(
        student_service=student_service,
        progress_service=progress_service,
        study_right_service=study_right_service,
        curriculum_service=curriculum_service,
        event_service=event_service,
    )

    result = service.generate_report(1)

    assert result["success"] is True
    assert result["report"]["report_type"] == "academic_summary"
    assert result["report"]["student"]["id"] == 1
    assert result["report"]["academic_progress"]["status"] == "BEHIND"
    assert result["report"]["study_right"]["status"] == "ACTIVE"
    assert result["report"]["curriculum"]["programme"] == "Business IT"
    assert result["report"]["upcoming_events"][0]["event_name"] == "Tutoring session"
    assert result["report"]["risk_assessment"] is None
    assert result["report"]["summary"]["overall_status"] == "UNKNOWN"
    assert "Risk assessment is unavailable." in result["report"]["summary"]["warnings"]
    assert "Student is behind expected progress by 30 ECTS." in result["report"]["summary"]["key_findings"]


def test_generate_report_returns_student_not_found() -> None:
    student_service = Mock()
    student_service.get_student.return_value = {
        "success": False,
        "error": "STUDENT_NOT_FOUND",
        "message": "Student with ID 999 was not found.",
    }

    service = ReportService(
        student_service=student_service,
        progress_service=Mock(),
        study_right_service=Mock(),
        curriculum_service=Mock(),
        event_service=Mock(),
    )

    result = service.generate_report(999)

    assert result == {
        "success": False,
        "error": "STUDENT_NOT_FOUND",
        "message": "Student with ID 999 was not found.",
    }


def test_generate_report_handles_empty_course_completions() -> None:
    student = {
        "id": 2,
        "student_number": "S002",
        "name": "Aino Niemi",
        "group_name": "TT21B",
        "programme": "Business IT",
        "start_date": "2022-09-01",
        "status": "ACTIVE",
        "programme_code": "DIN2024S",
    }

    student_service = Mock()
    progress_service = Mock()
    study_right_service = Mock()
    curriculum_service = Mock()
    event_service = Mock()

    student_service.get_student.return_value = {
        "success": True,
        "student": student,
    }
    progress_service.get_progress.return_value = {
        "success": True,
        "progress": {
            "student_id": 2,
            "student_number": "S002",
            "student_name": "Aino Niemi",
            "programme": "Business IT",
            "current_semester": 1,
            "completed_ects": 0,
            "expected_ects": 30,
            "difference_ects": -30,
            "remaining_to_expected_ects": 30,
            "progress_percentage": 0.0,
            "status": "BEHIND",
        },
    }
    study_right_service.get_study_right.return_value = {
        "success": False,
        "error": "STUDY_RIGHT_NOT_FOUND",
        "message": "Study right for student with ID 2 was not found.",
    }
    curriculum_service.get_curriculum.return_value = {
        "success": True,
        "curriculum": {
            "programme": "Business IT",
            "semesters": [{"semester": 1, "expected_ects": 30}],
            "total_expected_ects": 30,
        },
    }
    event_service.get_upcoming_events.return_value = {
        "success": True,
        "events": [],
    }

    service = ReportService(
        student_service=student_service,
        progress_service=progress_service,
        study_right_service=study_right_service,
        curriculum_service=curriculum_service,
        event_service=event_service,
    )

    result = service.generate_report(2)

    assert result["success"] is True
    assert result["report"]["academic_progress"]["completed_ects"] == 0
    assert result["report"]["study_right"] is None
    assert result["report"]["curriculum"]["programme"] == "Business IT"
    assert result["report"]["summary"]["overall_status"] == "UNKNOWN"
    assert "Study right information was not found." in result["report"]["summary"]["warnings"]


def test_generate_report_handles_missing_curriculum() -> None:
    student = {
        "id": 3,
        "student_number": "S003",
        "name": "Olli Laine",
        "group_name": "TT21C",
        "programme": "Business IT",
        "start_date": "2020-09-01",
        "status": "ACTIVE",
        "programme_code": "DIN2024S",
    }

    student_service = Mock()
    progress_service = Mock()
    study_right_service = Mock()
    curriculum_service = Mock()
    event_service = Mock()

    student_service.get_student.return_value = {
        "success": True,
        "student": student,
    }
    progress_service.get_progress.return_value = {
        "success": True,
        "progress": {
            "student_id": 3,
            "student_number": "S003",
            "student_name": "Olli Laine",
            "programme": "Business IT",
            "current_semester": 5,
            "completed_ects": 120,
            "expected_ects": 150,
            "difference_ects": -30,
            "remaining_to_expected_ects": 30,
            "progress_percentage": 80.0,
            "status": "BEHIND",
        },
    }
    study_right_service.get_study_right.return_value = {
        "success": True,
        "study_right": {
            "id": 2,
            "student_id": 3,
            "start_date": "2020-09-01",
            "end_date": "2024-08-31",
            "status": "ACTIVE",
            "extension_count": 1,
            "expiration_date": "2024-08-31",
            "is_expiring_soon": False,
        },
    }
    curriculum_service.get_curriculum.return_value = {
        "success": False,
        "error": "CURRICULUM_NOT_FOUND",
        "message": "Curriculum data was not found for programme 'Business IT'.",
    }
    event_service.get_upcoming_events.return_value = {
        "success": True,
        "events": [],
    }

    service = ReportService(
        student_service=student_service,
        progress_service=progress_service,
        study_right_service=study_right_service,
        curriculum_service=curriculum_service,
        event_service=event_service,
    )

    result = service.generate_report(3)

    assert result["success"] is True
    assert result["report"]["curriculum"] is None
    assert "Curriculum information was not found." in result["report"]["summary"]["warnings"]
    assert result["report"]["summary"]["overall_status"] == "UNKNOWN"


def test_generate_report_handles_empty_upcoming_events() -> None:
    student = {
        "id": 4,
        "student_number": "S004",
        "name": "Salla Saarinen",
        "group_name": "TT21D",
        "programme": "Business IT",
        "start_date": "2023-09-01",
        "status": "ACTIVE",
        "programme_code": "DIN2024S",
    }

    student_service = Mock()
    progress_service = Mock()
    study_right_service = Mock()
    curriculum_service = Mock()
    event_service = Mock()

    student_service.get_student.return_value = {
        "success": True,
        "student": student,
    }
    progress_service.get_progress.return_value = {
        "success": True,
        "progress": {
            "student_id": 4,
            "student_number": "S004",
            "student_name": "Salla Saarinen",
            "programme": "Business IT",
            "current_semester": 2,
            "completed_ects": 45,
            "expected_ects": 60,
            "difference_ects": -15,
            "remaining_to_expected_ects": 15,
            "progress_percentage": 75.0,
            "status": "BEHIND",
        },
    }
    study_right_service.get_study_right.return_value = {
        "success": True,
        "study_right": {
            "id": 3,
            "student_id": 4,
            "start_date": "2023-09-01",
            "end_date": "2027-08-31",
            "status": "ACTIVE",
            "extension_count": 0,
            "expiration_date": "2027-08-31",
            "is_expiring_soon": False,
        },
    }
    curriculum_service.get_curriculum.return_value = {
        "success": True,
        "curriculum": {
            "programme": "Business IT",
            "semesters": [{"semester": 1, "expected_ects": 30}],
            "total_expected_ects": 30,
        },
    }
    event_service.get_upcoming_events.return_value = {
        "success": True,
        "events": [],
    }

    service = ReportService(
        student_service=student_service,
        progress_service=progress_service,
        study_right_service=study_right_service,
        curriculum_service=curriculum_service,
        event_service=event_service,
    )

    result = service.generate_report(4)

    assert result["success"] is True
    assert result["report"]["upcoming_events"] == []
    assert "No upcoming academic events were found." in result["report"]["summary"]["key_findings"]
    assert result["report"]["summary"]["overall_status"] == "UNKNOWN"


def test_generate_report_uses_unknown_overall_status_when_risk_unavailable() -> None:
    student = {
        "id": 5,
        "student_number": "S005",
        "name": "Elina Miettinen",
        "group_name": "TT21E",
        "programme": "Business IT",
        "start_date": "2024-09-01",
        "status": "ACTIVE",
        "programme_code": "DIN2024S",
    }

    student_service = Mock()
    progress_service = Mock()
    study_right_service = Mock()
    curriculum_service = Mock()
    event_service = Mock()

    student_service.get_student.return_value = {
        "success": True,
        "student": student,
    }
    progress_service.get_progress.return_value = {
        "success": True,
        "progress": {
            "student_id": 5,
            "student_number": "S005",
            "student_name": "Elina Miettinen",
            "programme": "Business IT",
            "current_semester": 1,
            "completed_ects": 15,
            "expected_ects": 30,
            "difference_ects": -15,
            "remaining_to_expected_ects": 15,
            "progress_percentage": 50.0,
            "status": "BEHIND",
        },
    }
    study_right_service.get_study_right.return_value = {
        "success": True,
        "study_right": {
            "id": 4,
            "student_id": 5,
            "start_date": "2024-09-01",
            "end_date": "2028-08-31",
            "status": "ACTIVE",
            "extension_count": 0,
            "expiration_date": "2028-08-31",
            "is_expiring_soon": False,
        },
    }
    curriculum_service.get_curriculum.return_value = {
        "success": True,
        "curriculum": {
            "programme": "Business IT",
            "semesters": [{"semester": 1, "expected_ects": 30}],
            "total_expected_ects": 30,
        },
    }
    event_service.get_upcoming_events.return_value = {
        "success": True,
        "events": [],
    }

    service = ReportService(
        student_service=student_service,
        progress_service=progress_service,
        study_right_service=study_right_service,
        curriculum_service=curriculum_service,
        event_service=event_service,
    )

    result = service.generate_report(5)

    assert result["success"] is True
    assert result["report"]["risk_assessment"] is None
    assert result["report"]["summary"]["overall_status"] == "UNKNOWN"
    assert result["report"]["summary"]["warnings"] == [
        "Risk assessment is unavailable.",
    ]
