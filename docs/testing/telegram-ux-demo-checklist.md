# Real Telegram UX Demo Checklist

**Purpose:** Reproducible live validation of Issues #261–#266 for the final
demo recording. Automated tests validate structure and semantics; this checklist
records the visual result in an actual Telegram client.

## Prerequisites

- [ ] The intended revision is deployed and the backend health check passes.
- [ ] The Telegram webhook is active and uses the intended bot token.
- [ ] The deterministic demo dataset for Scenarios #127–#129 is available.
- [ ] The demo Tutor has the correct administrator-provisioned Telegram mapping.
- [ ] Scenario #129 tutor assignments and destination are configured.
- [ ] Required autonomous-workflow migrations are applied.
- [ ] No demo data, mappings, or assignments are changed merely for UX validation.
- [ ] Record the revision, environment, Telegram client, tester, and date below.

| Field | Value |
|---|---|
| Revision | |
| Environment | |
| Telegram client/version | |
| Tester | |
| Date/time | |

## Scenario #127 — Student progress

- [ ] Send `Show me Matias Multiple.`
- [ ] **Student overview** is bold and Matias's identity is clear.
- [ ] Student number is `DEMO25204`; programme matches the deployed fixture.
- [ ] Send `How is he progressing?`
- [ ] **BEHIND** and **PARTIAL** are prominent.
- [ ] Completed, expected, and deficit values are 5, 30, and 25 ECTS.
- [ ] Progress is 16.7% of expected.
- [ ] Send `Did he pass DBS24?` and `Did he pass WEB24?`
- [ ] Each authoritative FAILED/PASSED result is prominent.
- [ ] Grade `0` remains visible where recorded.
- [ ] Follow-up context remains Matias while course context changes correctly.

## Scenario #128 — Risk and recommendation

- [ ] Send `Show me DIN24.`
- [ ] Send `Who failed Database Systems in DIN24?`
- [ ] The authoritative failed-student shortlist is readable and is not described
      as cohort-wide canonical risk detection.
- [ ] Send `Show me Oskari Example.`
- [ ] Send `Why is he at risk?`
- [ ] **MEDIUM** risk is prominent and the assessment state matches verified data.
- [ ] The 30 ECTS deficit is visible under the evidence heading.
- [ ] Send `What academic next steps do you recommend for this student?`
- [ ] Verified concern appears before recommended actions.
- [ ] Recommended actions are numbered and explicitly advisory.
- [ ] Missing university-policy guidance is understandable.
- [ ] No internal keys or implementation error codes appear.

## Scenario #129 — Autonomous Monday briefing

- [ ] Run `backend/scripts/run_monday_briefing.py --confirm-send` from the approved
      environment; first verify that omitting `--confirm-send` does not send.
- [ ] The message arrives through the real autonomous path at the configured Tutor.
- [ ] **Weekly tutor briefing** and section headings are bold.
- [ ] Counts are assigned 2, analysed 2, attention 1 for the deterministic fixture.
- [ ] Oskari is listed under attention; Aava is not listed there.
- [ ] Oskari's 30 ECTS deficit and the current academic event are readable.
- [ ] No tutor action or recommendation is fabricated.
- [ ] Delivery status, provider receipt, and privacy-safe execution log are present.

## Safety, fallback, and readability

- [ ] A controlled test name containing `<b>`, `&`, quotes, or Unicode displays
      literally; no supplied fragment becomes Telegram markup.
- [ ] If a formatting-rejection test is available in the environment, exactly one
      readable plain-text fallback is delivered to the same chat.
- [ ] No excessive emojis, raw application HTML tags, dictionaries, or debug keys.
- [ ] Headings, whitespace, and grouped evidence make each response easy to scan.
- [ ] COMPLETE, PARTIAL, and UNAVAILABLE labels are truthful and easy to locate.
- [ ] Missing information is never presented as proof of no risk.
- [ ] Multi-part alerts retain readable part numbering and complete content.
- [ ] No message resembles a developer log.

## Automated validation matrix

| Area | Automated evidence |
|---|---|
| Scenario #127 semantics and presentation | `test_demo_scenario_1_student_progress_over_telegram_path` |
| Scenario #128 semantics and presentation | `test_demo_scenario_2_cohort_attention_to_explanation_over_telegram_path` |
| Scenario #129 semantics and presentation | `test_demo_scenario_3_executes_logs_and_delivers_meaningful_weekly_briefing` |
| HTML escaping and fallback | `tests/telegram/test_formatting.py`, `test_handlers.py` |
| PARTIAL and long alerts | `test_notification_delivery.py` |
| UNAVAILABLE readability | `test_ux_readability.py` |
| Commands and context | `test_academic_commands.py`, scenario E2E tests |
| Destination and receipts | notification and Monday workflow tests |

## Sign-off

- [ ] All applicable checks passed in a real Telegram client.
- [ ] Any deviation is recorded with screenshot/video timestamp and issue link.
- [ ] Tester confirms that observed academic values match the deployed fixture.
