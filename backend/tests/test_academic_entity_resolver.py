import asyncio
from app.services.academic_entity_resolver import AcademicEntityResolver

class Gateway:
    async def search_students(self, **kwargs): return {"success": True, "students": self.students}
    async def search_courses(self, **kwargs): return {"success": True, "courses": self.courses}
    async def search_teachers(self, **kwargs): return {"success": True, "teachers": self.teachers}
    async def search_student_groups(self, **kwargs): return {"success": True, "groups": self.groups}
    students=[]; courses=[]; teachers=[]; groups=[]

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
