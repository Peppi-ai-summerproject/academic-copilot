"""Resolve tutor-supplied entity text through the academic gateway only."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Literal, Protocol

EntityType = Literal["STUDENT", "COURSE", "TEACHER"]
ResolutionStatus = Literal["RESOLVED", "AMBIGUOUS", "NOT_FOUND", "INVALID"]

class SearchGateway(Protocol):
    async def search_students(self, **kwargs: Any) -> dict[str, Any]: ...
    async def search_courses(self, **kwargs: Any) -> dict[str, Any]: ...
    async def search_teachers(self, **kwargs: Any) -> dict[str, Any]: ...

@dataclass(frozen=True)
class ResolvedAcademicEntity:
    entity_type: EntityType
    input: str
    status: ResolutionStatus
    canonical_id: int | None = None
    display_name: str | None = None
    candidates: tuple[dict[str, Any], ...] = ()
    def as_dict(self) -> dict[str, Any]:
        return {"entity_type": self.entity_type, "input": self.input, "status": self.status, "canonical_id": self.canonical_id, "display_name": self.display_name, "candidates": list(self.candidates)}

class AcademicEntityResolver:
    def __init__(self, gateway: SearchGateway) -> None: self._gateway = gateway
    async def resolve(self, entity_type: EntityType, text: str) -> ResolvedAcademicEntity:
        normalized = " ".join(text.split()) if isinstance(text, str) else ""
        if not normalized: return ResolvedAcademicEntity(entity_type, str(text), "INVALID")
        response = await {"STUDENT": self._gateway.search_students, "COURSE": self._gateway.search_courses, "TEACHER": self._gateway.search_teachers}[entity_type](query=normalized)
        key = {"STUDENT": "students", "COURSE": "courses", "TEACHER": "teachers"}[entity_type]
        rows = response.get(key, []) if response.get("success") else []
        exact = [r for r in rows if self._exact(entity_type, r, normalized)]
        candidates = exact or rows
        safe = tuple(self._safe(entity_type, row) for row in candidates)
        if not candidates: return ResolvedAcademicEntity(entity_type, normalized, "NOT_FOUND")
        if len(candidates) != 1: return ResolvedAcademicEntity(entity_type, normalized, "AMBIGUOUS", candidates=safe)
        row = candidates[0]; identifier = int(row["id"])
        return ResolvedAcademicEntity(entity_type, normalized, "RESOLVED", identifier, self._name(entity_type, row), safe)
    @staticmethod
    def _exact(kind: EntityType, row: dict[str, Any], text: str) -> bool:
        value = {"STUDENT": row.get("student_number") or row.get("name"), "COURSE": row.get("course_code") or row.get("course_name"), "TEACHER": row.get("display_name")}[kind]
        return isinstance(value, str) and value.casefold() == text.casefold()
    @staticmethod
    def _name(kind: EntityType, row: dict[str, Any]) -> str:
        return str({"STUDENT": row.get("name"), "COURSE": row.get("course_name"), "TEACHER": row.get("display_name")}[kind])
    @staticmethod
    def _safe(kind: EntityType, row: dict[str, Any]) -> dict[str, Any]:
        if kind == "STUDENT": return {"student_id": row.get("id"), "student_number": row.get("student_number"), "name": row.get("name"), "programme": row.get("programme")}
        if kind == "COURSE": return {"course_id": row.get("id"), "course_code": row.get("course_code"), "course_name": row.get("course_name")}
        return {"teacher_id": row.get("id"), "name": row.get("display_name")}
