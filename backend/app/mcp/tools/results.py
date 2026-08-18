from typing import Any
from app.db.database import SessionLocal
from app.repositories.academic_record_repository import AcademicRecordRepository
from app.repositories.course_repository import CourseRepository
from app.repositories.student_repository import StudentRepository
from app.services.course_results_service import CourseResultsService
def _service(session): return CourseResultsService(AcademicRecordRepository(session), CourseRepository(session), StudentRepository(session))
def get_course_results(course_code: str, status: str | None = None) -> dict[str, Any]: return _run(lambda s: _service(s).course_results(course_code, status))
def get_student_results(student_id: int, status: str | None = None) -> dict[str, Any]: return _run(lambda s: _service(s).student_results(student_id, status))
def get_course_completion_analytics(course_code: str) -> dict[str, Any]: return _run(lambda s: _service(s).analytics(course_code))
def _run(fn):
    session = SessionLocal()
    try: return fn(session)
    except Exception: return {"success": False, "error": "DATABASE_ERROR", "message": "Course results could not be retrieved."}
    finally: session.close()
