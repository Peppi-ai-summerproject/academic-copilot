"""Structural UX validation separate from academic-semantic scenario tests."""

from app.agents.risk_detection_agent import RiskDetectionAgent
from app.telegram.formatting import format_telegram_html


def test_unavailable_risk_is_prominent_truthful_and_human_readable():
    plain = RiskDetectionAgent._build_summary(
        student_name="Alice <student>",
        risk_level="LOW",
        factors=[],
        complete=False,
        unavailable=["progress", "study_right"],
    )

    rendered = format_telegram_html(plain)

    assert rendered.startswith("<b>Academic risk</b>\n<b>Alice &lt;student&gt;</b>")
    assert "Risk level: <b>UNAVAILABLE</b>" in rendered
    assert "Assessment: <b>UNAVAILABLE</b>" in rendered
    assert "Risk level: <b>LOW</b>" not in rendered
    assert "Sufficient academic evidence was unavailable" in rendered
    assert "Academic progress information" in rendered
    assert "Study-right information" in rendered
    assert "Missing information is not interpreted as no risk." in rendered
    assert "study_right" not in rendered
