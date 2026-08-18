import asyncio
from app.services.academic_entity_resolver import AcademicEntityResolver

class Gateway:
    async def search_students(self, **kwargs): return {"success": True, "students": self.students}
    async def search_courses(self, **kwargs): return {"success": True, "courses": self.courses}
    async def search_teachers(self, **kwargs): return {"success": True, "teachers": self.teachers}
    students=[]; courses=[]; teachers=[]

def test_resolves_exact_identifiers_and_names():
    g=Gateway(); g.students=[{"id": 1,"student_number":"S1","name":"Aino"}]; g.courses=[{"id":2,"course_code":"DIN24","course_name":"Digital"}]
    r=AcademicEntityResolver(g)
    assert asyncio.run(r.resolve("STUDENT","s1")).canonical_id == 1
    assert asyncio.run(r.resolve("COURSE","din24")).status == "RESOLVED"

def test_ambiguous_and_missing_never_guess():
    g=Gateway(); g.students=[{"id":1,"student_number":"S1","name":"Anna"},{"id":2,"student_number":"S2","name":"Anna"}]
    r=AcademicEntityResolver(g)
    assert asyncio.run(r.resolve("STUDENT","Anna")).status == "AMBIGUOUS"
    g.students=[]
    assert asyncio.run(r.resolve("STUDENT","Missing")).status == "NOT_FOUND"
