import asyncio
from app.services.academic_entity_resolver import AcademicEntityResolver

class Gateway:
    async def search_students(self, **kwargs): return {"success": True, "students": self.students}
    async def search_courses(self, **kwargs): return {"success": True, "courses": self.courses}
    async def search_teachers(self, **kwargs): return {"success": True, "teachers": self.teachers}
    async def search_student_groups(self, **kwargs): return {"success": True, "groups": self.groups}
    async def get_student_group_courses(self, group_id): return {"success": True, "courses": self.group_courses}
    students=[]; courses=[]; teachers=[]; groups=[]; group_courses=[]

def test_resolves_exact_identifiers_and_names():
    g=Gateway(); g.students=[{"id": 1,"student_number":"S1","name":"Aino"}]; g.courses=[{"id":2,"course_code":"DII101","course_name":"Digital"}]
    r=AcademicEntityResolver(g)
    assert asyncio.run(r.resolve("STUDENT","s1")).canonical_id == 1
    assert asyncio.run(r.resolve("COURSE","dii101")).status == "RESOLVED"

def test_ambiguous_and_missing_never_guess():
    g=Gateway(); g.students=[{"id":1,"student_number":"S1","name":"Anna"},{"id":2,"student_number":"S2","name":"Anna"}]
    r=AcademicEntityResolver(g)
    assert asyncio.run(r.resolve("STUDENT","Anna")).status == "AMBIGUOUS"
    g.students=[]
    assert asyncio.run(r.resolve("STUDENT","Missing")).status == "NOT_FOUND"

def test_resolves_student_group_and_disambiguates_academic_codes():
    g=Gateway(); g.students=[]; g.teachers=[]
    g.groups=[{"id":24,"group_code":"DIN24","group_name":"Digital Innovation 2024"}]
    g.courses=[]
    r=AcademicEntityResolver(g)
    group=asyncio.run(r.resolve("ACADEMIC_CODE","din24"))
    g.groups=[]
    g.courses=[{"id":101,"course_code":"DII101","course_name":"Database Systems"}]
    course=asyncio.run(r.resolve("ACADEMIC_CODE","dii101"))
    assert (group.entity_type, group.canonical_id) == ("STUDENT_GROUP", 24)
    assert (course.entity_type, course.canonical_id) == ("COURSE", 101)

def test_academic_code_collision_is_ambiguous():
    g=Gateway(); g.students=[]; g.teachers=[]
    g.groups=[{"id":24,"group_code":"DIN24","group_name":"Group"}]
    g.courses=[{"id":101,"course_code":"DIN24","course_name":"Legacy course"}]
    result=asyncio.run(AcademicEntityResolver(g).resolve("ACADEMIC_CODE","DIN24"))
    assert result.status == "AMBIGUOUS"

def test_unknown_student_group_is_not_found():
    g=Gateway(); g.students=[]; g.courses=[]; g.teachers=[]; g.groups=[]
    result=asyncio.run(AcademicEntityResolver(g).resolve("STUDENT_GROUP","UNKNOWN24"))
    assert result.status == "NOT_FOUND"

def test_existing_student_course_name_and_teacher_resolution_remain_canonical():
    g=Gateway(); g.groups=[]
    g.students=[{"id":2,"student_number":"S002","name":"Aino Mäkinen"}]
    g.courses=[]; g.teachers=[]
    resolver=AcademicEntityResolver(g)
    student=asyncio.run(resolver.resolve("STUDENT","Aino Mäkinen"))
    g.students=[]; g.courses=[{"id":25,"course_code":"DBS24","course_name":"Database Systems"}]
    course=asyncio.run(resolver.resolve("COURSE","Database Systems"))
    g.courses=[]; g.teachers=[{"id":34,"display_name":"Anna Example"}]
    teacher=asyncio.run(resolver.resolve("TEACHER","Anna Example"))
    assert (student.entity_type, student.canonical_id) == ("STUDENT", 2)
    assert (course.entity_type, course.canonical_id) == ("COURSE", 25)
    assert (teacher.entity_type, teacher.canonical_id) == ("TEACHER", 34)

def test_ambiguous_course_can_be_narrowed_by_canonical_group_membership():
    g=Gateway(); g.students=[]; g.teachers=[]; g.groups=[]
    g.courses=[
        {"id":25,"course_code":"DBS24","course_name":"Database Systems"},
        {"id":103,"course_code":"DE103","course_name":"Database Systems"},
    ]
    g.group_courses=[{"id":25,"course_code":"DBS24","course_name":"Database Systems"}]
    resolver=AcademicEntityResolver(g)
    ambiguous=asyncio.run(resolver.resolve("COURSE","Database Systems"))
    narrowed=asyncio.run(resolver.narrow_ambiguous_course_to_group(ambiguous, 240))
    assert ambiguous.status == "AMBIGUOUS"
    assert (narrowed.status, narrowed.canonical_id) == ("RESOLVED", 25)

def test_group_narrowing_preserves_zero_and_multiple_candidate_ambiguity():
    g=Gateway(); g.students=[]; g.teachers=[]; g.groups=[]
    g.courses=[
        {"id":25,"course_code":"DBS24","course_name":"Database Systems"},
        {"id":103,"course_code":"DE103","course_name":"Database Systems"},
    ]
    resolver=AcademicEntityResolver(g)
    ambiguous=asyncio.run(resolver.resolve("COURSE","Database Systems"))
    g.group_courses=[]
    assert asyncio.run(resolver.narrow_ambiguous_course_to_group(ambiguous, 240)).status == "AMBIGUOUS"
    g.group_courses=[{"id":25}, {"id":103}]
    still_ambiguous=asyncio.run(resolver.narrow_ambiguous_course_to_group(ambiguous, 240))
    assert still_ambiguous.status == "AMBIGUOUS"
    assert len(still_ambiguous.candidates) == 2
