"""Resolve tutor-supplied entity text through the academic gateway only."""
from __future__ import annotations
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Literal, Protocol
import unicodedata

EntityType = Literal["STUDENT", "COURSE", "TEACHER", "STUDENT_GROUP"]
ResolvableEntityType = Literal["STUDENT", "COURSE", "TEACHER", "STUDENT_GROUP", "ACADEMIC_CODE"]
ResolutionStatus = Literal["RESOLVED", "AMBIGUOUS", "SUGGESTED", "NOT_FOUND", "INVALID"]

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
        if entity_type == "STUDENT":
            return await self._resolve_student(normalized, rows)
        exact = [r for r in rows if self._exact(entity_type, r, normalized)]
        candidates = exact or rows
        safe = tuple(self._safe(entity_type, row) for row in candidates)
        if not candidates: return ResolvedAcademicEntity(entity_type, normalized, "NOT_FOUND")
        if len(candidates) != 1: return ResolvedAcademicEntity(entity_type, normalized, "AMBIGUOUS", candidates=safe)
        row = candidates[0]; identifier = int(row["id"])
        return ResolvedAcademicEntity(entity_type, normalized, "RESOLVED", identifier, self._name(entity_type, row), safe)

    async def _resolve_student(
        self, normalized: str, rows: list[dict[str, Any]]
    ) -> ResolvedAcademicEntity:
        exact = [row for row in rows if self._exact("STUDENT", row, normalized)]
        if exact:
            return self._student_candidates(normalized, exact)

        partial = [row for row in rows if _token_partial(normalized, row.get("name"))]
        if partial:
            return self._student_candidates(normalized, partial)

        pool = list(rows)
        if not pool:
            pool = await self._student_suggestion_pool(normalized)
        ranked = _rank_student_suggestions(normalized, pool)
        if not ranked:
            return ResolvedAcademicEntity("STUDENT", normalized, "NOT_FOUND")
        best_score = ranked[0][0]
        plausible = [row for score, row in ranked if score >= 0.82]
        if best_score < 0.88:
            if len(plausible) > 1:
                return ResolvedAcademicEntity(
                    "STUDENT", normalized, "AMBIGUOUS",
                    candidates=tuple(self._safe("STUDENT", row) for row in plausible),
                )
            return ResolvedAcademicEntity("STUDENT", normalized, "NOT_FOUND")
        if len(ranked) > 1 and ranked[1][0] >= 0.88:
            close = [row for score, row in ranked if score >= 0.88]
            return ResolvedAcademicEntity(
                "STUDENT", normalized, "AMBIGUOUS",
                candidates=tuple(self._safe("STUDENT", row) for row in close),
            )
        candidate = ranked[0][1]
        return ResolvedAcademicEntity(
            "STUDENT", normalized, "SUGGESTED",
            display_name=self._name("STUDENT", candidate),
            candidates=(self._safe("STUDENT", candidate),),
        )

    def _student_candidates(
        self, normalized: str, candidates: list[dict[str, Any]]
    ) -> ResolvedAcademicEntity:
        safe = tuple(self._safe("STUDENT", row) for row in candidates)
        if len(candidates) != 1:
            return ResolvedAcademicEntity("STUDENT", normalized, "AMBIGUOUS", candidates=safe)
        row = candidates[0]
        return ResolvedAcademicEntity(
            "STUDENT", normalized, "RESOLVED", int(row["id"]),
            self._name("STUDENT", row), safe,
        )

    async def _student_suggestion_pool(self, normalized: str) -> list[dict[str, Any]]:
        candidates: dict[Any, dict[str, Any]] = {}
        terms = _normalized_name(normalized).split()
        queries = dict.fromkeys(
            query for term in terms for query in (term, term[:2]) if len(query) >= 2
        )
        for query in queries:
            response = await self._gateway.search_students(query=query)
            if not response.get("success"):
                continue
            for row in response.get("students", []):
                if isinstance(row, dict) and row.get("id") is not None:
                    candidates[row["id"]] = row
        return list(candidates.values())

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


def _normalized_name(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _token_partial(query: str, name: Any) -> bool:
    query_words = _normalized_name(query).split()
    name_words = _normalized_name(name).split()
    if not query_words or not name_words:
        return False
    width = len(query_words)
    return any(name_words[index:index + width] == query_words for index in range(len(name_words) - width + 1))


def _rank_student_suggestions(
    query: str, rows: list[dict[str, Any]]
) -> list[tuple[float, dict[str, Any]]]:
    needle = _normalized_name(query)
    ranked = [
        (SequenceMatcher(None, needle, _normalized_name(row.get("name"))).ratio(), row)
        for row in rows
        if _normalized_name(row.get("name"))
    ]
    return sorted(ranked, key=lambda item: (-item[0], str(item[1].get("name") or ""), str(item[1].get("id") or "")))
