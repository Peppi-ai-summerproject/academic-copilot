from telegram.error import BadRequest, Forbidden

from app.telegram.formatting import (
    bold_telegram_html,
    escape_telegram_html,
    format_telegram_html,
    is_telegram_formatting_error,
    telegram_html_to_plain,
)


def test_dynamic_values_are_escaped_and_supported_markup_is_controlled():
    source = 'Student overview\nAlice <b>Admin</b> & "Tutor"\nStatus: FAILED'

    rendered = format_telegram_html(source)

    assert rendered == (
        '<b>Student overview</b>\n'
        '<b>Alice &lt;b&gt;Admin&lt;/b&gt; &amp; &quot;Tutor&quot;</b>\n'
        'Status: <b>FAILED</b>'
    )
    assert bold_telegram_html("Databases & APIs") == "<b>Databases &amp; APIs</b>"
    assert escape_telegram_html("<student>") == "&lt;student&gt;"


def test_all_academic_dynamic_value_categories_are_neutralized():
    source = "\n".join(
        [
            "Student: Alice <b>Admin</b>",
            "Course: Databases & APIs",
            "Tutor: <script>alert(1)</script>",
            "Event: Registration <Deadline>",
            "Recommendation: Review A&B study plan",
            "Programme: ICT 'International'",
            "Email: tutor<a@example.test>",
            "Student: Åsa Öster",
        ]
    )

    rendered = format_telegram_html(source)

    assert "Alice &lt;b&gt;Admin&lt;/b&gt;" in rendered
    assert "Databases &amp; APIs" in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert "Registration &lt;Deadline&gt;" in rendered
    assert "Review A&amp;B study plan" in rendered
    assert "ICT &#x27;International&#x27;" in rendered
    assert "tutor&lt;a@example.test&gt;" in rendered
    assert "Åsa Öster" in rendered


def test_html_fallback_restores_literal_dynamic_values_without_markup():
    rendered = format_telegram_html("Academic risk\nAlice <b>Admin</b> & O'Neil")

    fallback = telegram_html_to_plain(rendered)

    assert fallback == "Academic risk\nAlice <b>Admin</b> & O'Neil"
    assert fallback.count("<b>") == 1
    assert "<b>Academic risk</b>" not in fallback


def test_only_explicit_telegram_formatting_rejections_are_retryable():
    assert is_telegram_formatting_error(BadRequest("Can't parse entities")) is True
    assert is_telegram_formatting_error(BadRequest("Chat not found")) is False
    assert is_telegram_formatting_error(Forbidden("Forbidden")) is False
