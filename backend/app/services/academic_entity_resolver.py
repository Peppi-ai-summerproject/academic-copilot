"""Resolve tutor-supplied entity text through the academic gateway only."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Literal, Protocol

EntityType = Literal["STUDENT", "COURSE", "TEACHER", "STUDENT_GROUP"]
ResolvableEntityType = Literal["STUDENT", "COURSE", "TEACHER", "STUDENT_GROUP", "ACADEMIC_CODE"]
ResolutionStatus = Literal["RESOLVED", "AMBIGUOUS", "NOT_FOUND", "INVALID"]

class SearchGateway(Protocol):
    async def search_students(self, **kwargs: Any) -> dict[str, Any]: ...
    async def search_courses(self, **kwargs: Any) -> dict[str, Any]: ...
    async def search_teachers(self, **kwargs: Any) -> dict[str, Any]: ...
    async def search_student_groups(self, **kwargs: Any) -> dict[str, Any]: ...
    async def get_student_group_courses(self, group_id: int) -> dict[str, Any]: ...

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
    async def resolve(self, entity_type: ResolvableEntityType, text: str) -> ResolvedAcademicEntity:
        normalized = " ".join(text.split()) if isinstance(text, str) else ""
        if entity_type == "ACADEMIC_CODE":
            group = await self.resolve("STUDENT_GROUP", normalized)
            course = await self.resolve("COURSE", normalized)
            resolved = [item for item in (group, course) if item.status == "RESOLVED"]
            if len(resolved) == 1:
                return resolved[0]
            if len(resolved) > 1:
                return ResolvedAcademicEntity("STUDENT_GROUP", normalized, "AMBIGUOUS", candidates=tuple(group.candidates + course.candidates))
            return group if group.status == "AMBIGUOUS" else course if course.status == "AMBIGUOUS" else ResolvedAcademicEntity("STUDENT_GROUP", normalized, "NOT_FOUND")
        if not normalized: return ResolvedAcademicEntity(entity_type, str(text), "INVALID")
        operation = {
            "STUDENT": "search_students",
            "COURSE": "search_courses",
            "TEACHER": "search_teachers",
            "STUDENT_GROUP": "search_student_groups",
        }[entity_type]
        response = await getattr(self._gateway, operation)(query=normalized)
        key = {"STUDENT": "students", "COURSE": "courses", "TEACHER": "teachers", "STUDENT_GROUP": "groups"}[entity_type]
        rows = response.get(key, []) if response.get("success") else []
        exact = [r for r in rows if self._exact(entity_type, r, normalized)]
        candidates = exact or rows
        safe = tuple(self._safe(entity_type, row) for row in candidates)
        if not candidates: return ResolvedAcademicEntity(entity_type, normalized, "NOT_FOUND")
        if len(candidates) != 1: return ResolvedAcademicEntity(entity_type, normalized, "AMBIGUOUS", candidates=safe)
        row = candidates[0]; identifier = int(row["id"])
        return ResolvedAcademicEntity(entity_type, normalized, "RESOLVED", identifier, self._name(entity_type, row), safe)

    async def narrow_ambiguous_course_to_group(
        self, resolution: ResolvedAcademicEntity, group_id: int
    ) -> ResolvedAcademicEntity:
        """Narrow an ambiguous global course match using canonical group membership."""
        if resolution.entity_type != "COURSE" or resolution.status != "AMBIGUOUS":
            return resolution
        response = await self._gateway.get_student_group_courses(group_id)
        if not response.get("success"):
            return resolution
        group_course_ids = {
            row.get("id") for row in response.get("courses", []) if isinstance(row, dict)
        }
        candidates = tuple(
            row for row in resolution.candidates
            if row.get("course_id") in group_course_ids
        )
        if len(candidates) == 1:
            candidate = candidates[0]
            return ResolvedAcademicEntity(
                "COURSE",
                resolution.input,
                "RESOLVED",
                int(candidate["course_id"]),
                str(candidate.get("course_name") or candidate.get("course_code")),
                candidates,
            )
        if len(candidates) > 1:
            return ResolvedAcademicEntity(
                "COURSE", resolution.input, "AMBIGUOUS", candidates=candidates
            )
        return resolution
    @staticmethod
    def _exact(kind: EntityType, row: dict[str, Any], text: str) -> bool:
        value = {"STUDENT": row.get("student_number") or row.get("name"), "COURSE": row.get("course_code") or row.get("course_name"), "TEACHER": row.get("display_name"), "STUDENT_GROUP": row.get("group_code") or row.get("group_name")}[kind]
        return isinstance(value, str) and value.casefold() == text.casefold()
    @staticmethod
    def _name(kind: EntityType, row: dict[str, Any]) -> str:
        return str({"STUDENT": row.get("name"), "COURSE": row.get("course_name"), "TEACHER": row.get("display_name"), "STUDENT_GROUP": row.get("group_code")}[kind])
    @staticmethod
    def _safe(kind: EntityType, row: dict[str, Any]) -> dict[str, Any]:
        if kind == "STUDENT": return {"student_id": row.get("id"), "student_number": row.get("student_number"), "name": row.get("name"), "programme": row.get("programme")}
        if kind == "COURSE": return {"course_id": row.get("id"), "course_code": row.get("course_code"), "course_name": row.get("course_name")}
        if kind == "STUDENT_GROUP": return {"group_id": row.get("id"), "group_code": row.get("group_code"), "group_name": row.get("group_name"), "programme_code": row.get("programme_code")}
        return {"teacher_id": row.get("id"), "name": row.get("display_name")}
