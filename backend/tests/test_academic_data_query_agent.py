import asyncio
from app.agents.academic_data_query_agent import AcademicDataQueryAgent
from app.agents.state import create_initial_state

class Gateway:
    async def get_course_results(self, **kwargs): return {"success": True, "results": []}
    async def get_course_completion_analytics(self, **kwargs): return {"success": True, "analytics": {}}
    async def get_course_roster(self, **kwargs): return {"success": True, "students": []}
    async def get_student_enrollments(self, **kwargs): return {"success": True, "enrollments": []}

def test_dispatches_course_results_through_gateway():
    state=create_initial_state(user_message="results", parameters={"academic_operation":"course_results", "course_code":"DIN24"})
    result=asyncio.run(AcademicDataQueryAgent(Gateway()).run(state))
    assert result.status == "SUCCESS"

def test_rejects_unsupported_operation():
    state=create_initial_state(user_message="unknown", parameters={"academic_operation":"unknown"})
    assert asyncio.run(AcademicDataQueryAgent(Gateway()).run(state)).status == "FAILED"
