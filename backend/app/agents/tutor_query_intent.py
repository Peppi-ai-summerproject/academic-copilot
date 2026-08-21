"""Capability-oriented detection and entity extraction for tutor data queries."""

from __future__ import annotations

from dataclasses import dataclass, field
import re


@dataclass(frozen=True)
class TutorQueryMatch:
    capability: str
    entity_references: tuple[tuple[str, str], ...] = ()
    parameters: dict[str, str] = field(default_factory=dict)


_COURSE_CODE = re.compile(r"\b[A-Za-z]{2,}\d{2,}[A-Za-z0-9-]*\b")
_STUDENT_NUMBER = re.compile(r"\b\d{6,12}\b")


def detect_tutor_query(message: str) -> TutorQueryMatch | None:
    """Return a structured academic-data capability without querying data."""
    text = " ".join(message.strip().split())
    lower = text.casefold()
    course = _course_reference(text)
    student = _student_reference(text)
    teacher = _teacher_reference(text)

    if re.search(r"\b(pass rate|failure rate|completion rate|how many .*completed)\b", lower):
        return _match("course_analytics", course)
    if re.search(r"\b(?:what grade|which grade)\b", lower):
        return _match("student_course_result", student, course)
    if re.search(r"\b(failed|didn't pass|did not pass)\b", lower):
        if student and course:
            return _match("student_course_result", student, course, result_filter="FAILED")
        return _match("course_results", course, result_filter="FAILED")
    if re.search(r"\b(passed|pass)\b", lower):
        if student or re.search(r"\b(?:she|he|they)\b", lower):
            return _match("student_course_result", student, course, result_filter="PASSED")
        return _match("course_results", course, result_filter="PASSED")
    if "result" in lower and course:
        return _match("student_course_result" if student else "course_results", student, course)
    if re.search(r"\b(who|students?|how many)\b.*\b(enrolled|taking)\b", lower):
        return _match("course_roster", course)
    if re.search(r"\b(which|what) courses?\b", lower) and re.search(r"\b(enrolled|taking)\b", lower):
        return _match("student_enrollments", student)
    if re.search(r"\b(is|has)\b.*\b(enrolled|completed)\b", lower) and student and course:
        return _match("student_course_result" if "completed" in lower else "enrollment", student, course)
    if re.search(r"\b(who teaches|who is (?:the )?teacher|who is responsible|teachers? for)\b", lower):
        role = "LEAD_TEACHER" if "responsible" in lower else None
        return _match("course_teachers", course, role=role)
    if re.search(r"\b(which|what|show).*courses?\b.*\b(teach|teaching)\b", lower) or re.search(r"\bcourses? does\b.*\bteach", lower):
        return _match("teacher_courses", teacher)
    if re.search(r"\b(email|contact)\b", lower) and (
        "teacher" in lower
        or teacher
        or re.search(r"\b(?:his|her|their)\b", lower)
    ):
        return _match("teacher_contact", teacher)
    if re.search(r"\b(find|show) teacher\b", lower):
        return _match("teacher_lookup", teacher)
    if re.search(r"\b(progress|progressing|credits?|behind schedule)\b", lower) and student:
        return _match("student_progress", student)
    if re.search(r"\b(email|contact)\b", lower) and student:
        return _match("student_lookup", student)
    if (re.search(r"\b(find|show) student\b", lower) and student) or _STUDENT_NUMBER.search(text):
        return _match("student_lookup", student)
    if re.search(r"\b(show me all courses|list (?:all )?courses)\b", lower):
        return TutorQueryMatch("course_search")
    if (
        re.search(
            r"\b(find (?:the )?.+ course|find course|what is|what about|show (?:me )?course)\b",
            lower,
        )
        or re.match(r"^show (?:me )?", lower)
    ) and course:
        return _match("course_lookup", course)
    if match := re.search(r"^(?:now\s+)?(?:find|show me|show)\s+([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+)?)\.?$", text, re.IGNORECASE):
        return _match("student_lookup", ("STUDENT", match.group(1)))
    return None


def _match(capability: str, *references, **parameters) -> TutorQueryMatch:
    refs = tuple(reference for reference in references if reference is not None)
    clean = {key: value for key, value in parameters.items() if value is not None}
    return TutorQueryMatch(capability, refs, clean)


def _course_reference(text: str) -> tuple[str, str] | None:
    if match := _COURSE_CODE.search(text):
        return ("COURSE", match.group(0))
    patterns = (
        r"(?:course|for|in)\s+(.+?)(?:[?.]|$)",
        r"find\s+(.+?)\s+course(?:[?.]|$)",
    )
    for pattern in patterns:
        if match := re.search(pattern, text, re.IGNORECASE):
            value = match.group(1).strip()
            if value and value.casefold() not in {"this course", "the course"}:
                return ("COURSE", value)
    return None


def _student_reference(text: str) -> tuple[str, str] | None:
    if match := _STUDENT_NUMBER.search(text):
        return ("STUDENT", match.group(0))
    patterns = (
        r"(?:student|has|did|is|how is)\s+([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+)?)",
        r"which courses is\s+([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+)?)",
    )
    for pattern in patterns:
        if match := re.search(pattern, text, re.IGNORECASE):
            value = match.group(1).strip()
            words = value.casefold().split()
            if words and words[0] not in {"she", "he", "they", "her", "him", "them"} and not any(
                word in {"taking", "pass", "passed", "get", "progressing"} for word in words
            ):
                return ("STUDENT", value)
    return None


def _teacher_reference(text: str) -> tuple[str, str] | None:
    patterns = (
        r"teacher\s+([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+)?)",
        r"(?:does|is)\s+([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+)?)\s+(?:teach|teaching)",
        r"show\s+([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+)?)'s courses",
        r"what is\s+([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+)?)'s email",
    )
    for pattern in patterns:
        if match := re.search(pattern, text, re.IGNORECASE):
            value = match.group(1).strip()
            if value.casefold() not in {"he", "she", "they", "him", "her", "them"}:
                return ("TEACHER", value)
    return None
