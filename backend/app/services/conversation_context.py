"""Canonical academic entity context for a single conversation."""

from __future__ import annotations

from typing import Any, Iterable


ENTITY_TYPES = ("STUDENT", "COURSE", "TEACHER", "STUDENT_GROUP")

CAPABILITY_ENTITY_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "student_lookup": ("STUDENT",),
    "student_progress": ("STUDENT",),
    "student_enrollments": ("STUDENT",),
    "course_lookup": ("COURSE",),
    "course_roster": ("COURSE",),
    "course_results": ("COURSE",),
    "course_analytics": ("COURSE",),
    "enrollment": ("STUDENT", "COURSE"),
    "student_course_result": ("STUDENT", "COURSE"),
    "teacher_lookup": ("TEACHER",),
    "teacher_contact": ("TEACHER",),
    "course_teachers": ("COURSE",),
    "teacher_courses": ("TEACHER",),
    "group_lookup": ("STUDENT_GROUP",),
    "group_students": ("STUDENT_GROUP",),
    "group_courses": ("STUDENT_GROUP",),
    "group_course_teachers": ("STUDENT_GROUP", "COURSE"),
}


def canonical_entities(entities: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return at most one safe, resolved canonical entity of each type."""
    active: dict[str, dict[str, Any]] = {}
    for entity in entities:
        kind = entity.get("entity_type")
        canonical_id = entity.get("canonical_id")
        if (
            kind in ENTITY_TYPES
            and entity.get("status") == "RESOLVED"
            and isinstance(canonical_id, int)
            and not isinstance(canonical_id, bool)
            and canonical_id > 0
        ):
            active[str(kind)] = _minimal_entity(entity)
    return [active[kind] for kind in ENTITY_TYPES if kind in active]


def merge_canonical_entities(
    stored: Iterable[dict[str, Any]],
    resolved_now: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge current resolutions over stored context without clearing other types."""
    return canonical_entities([*stored, *resolved_now])


def entity_for(
    entities: Iterable[dict[str, Any]], kind: str
) -> dict[str, Any] | None:
    return next(
        (
            entity
            for entity in canonical_entities(entities)
            if entity["entity_type"] == kind
        ),
        None,
    )


def missing_entities(
    capability: str | None, entities: Iterable[dict[str, Any]]
) -> tuple[str, ...]:
    available = {entity["entity_type"] for entity in canonical_entities(entities)}
    return tuple(
        kind for kind in CAPABILITY_ENTITY_REQUIREMENTS.get(capability or "", ())
        if kind not in available
    )


def _minimal_entity(entity: dict[str, Any]) -> dict[str, Any]:
    """Exclude records and retain only identity metadata from the #226 contract."""
    result: dict[str, Any] = {
        "entity_type": entity["entity_type"],
        "status": "RESOLVED",
        "canonical_id": entity["canonical_id"],
    }
    if isinstance(entity.get("display_name"), str):
        result["display_name"] = entity["display_name"]
    candidates = entity.get("candidates")
    if isinstance(candidates, list) and candidates:
        candidate = candidates[0]
        if isinstance(candidate, dict):
            allowed = {
                "STUDENT": ("student_number",),
                "COURSE": ("course_code",),
                "TEACHER": (),
                "STUDENT_GROUP": ("group_code",),
            }[entity["entity_type"]]
            identity = {key: candidate[key] for key in allowed if candidate.get(key) is not None}
            if identity:
                result["candidates"] = [identity]
    return result
