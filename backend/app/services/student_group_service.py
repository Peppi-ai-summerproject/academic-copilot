"""Canonical student-group query contracts."""

from typing import Any

from app.repositories.student_group_repository import StudentGroupRepository


class StudentGroupService:
    def __init__(self, repository: StudentGroupRepository) -> None:
        self._repository = repository

    def search_groups(self, query: str | None = None) -> dict[str, Any]:
        normalized = query.strip() if isinstance(query, str) and query.strip() else None
        groups = self._repository.search(normalized)
        return {"success": True, "groups": groups, "group_count": len(groups)}

    def get_group(self, group_id: int) -> dict[str, Any]:
        if not isinstance(group_id, int) or isinstance(group_id, bool) or group_id <= 0:
            return {"success": False, "error": "INVALID_STUDENT_GROUP_ID"}
        group = self._repository.get_by_id(group_id)
        return ({"success": True, "group": group} if group else {"success": False, "error": "STUDENT_GROUP_NOT_FOUND"})

    def get_students(self, group_id: int) -> dict[str, Any]:
        group = self.get_group(group_id)
        if not group["success"]:
            return group
        students = self._repository.list_students(group_id)
        return {"success": True, "group": group["group"], "students": students, "student_count": len(students)}

    def get_courses(self, group_id: int) -> dict[str, Any]:
        group = self.get_group(group_id)
        if not group["success"]:
            return group
        courses = self._repository.list_courses(group_id)
        return {"success": True, "group": group["group"], "courses": courses, "course_count": len(courses)}
