# Telegram Response Design System

**Status:** Authoritative presentation specification  
**Scope:** Tutor-facing Telegram responses and autonomous notifications  
**Implementation status:** Design target; renderer adoption is deferred to follow-up UX issues

This document is the single source of truth for how Academic Copilot content
should be presented in Telegram. It governs presentation only. Academic facts,
calculations, risk classifications, recommendations, evidence availability,
authorization, and delivery decisions continue to come from their owning
services and workflows.

## Design objective

Telegram should feel like a compact professional dashboard for university
staff: direct, calm, evidence-led, and easy to scan on a phone. Visual hierarchy
must come primarily from typography and structure—not decoration.

Every response should help a tutor answer, in order:

1. What is the result?
2. What is its status or level of risk?
3. Which verified facts support it?
4. What should I consider doing next?
5. What information was unavailable or uncertain?

## Core principles

- Lead with the conclusion. Do not begin with conversational filler.
- Preserve authoritative terminology and values exactly, including grade zero,
  ECTS, dates, and canonical risk levels.
- Separate verified facts from interpretation and advisory recommendations.
- Make incomplete evidence prominent. Missing information never means no risk.
- Prefer short labels, short sections, whitespace, and stable ordering.
- Use one idea per line where practical.
- Use plain language for tutors; do not expose internal routes, payloads, reason
  codes, stack traces, model behavior, or architecture in a normal response.
- Keep emojis minimal and optional. A response must retain its complete meaning
  and hierarchy with every emoji removed.

## Standard response anatomy

Use only the sections that add information, in this order:

1. **Title**—the subject or task, such as `Student progress`.
2. **Identity/scope**—student, group, course, tutor, or reporting period.
3. **Status line**—the conclusion, risk label, or availability state.
4. **Key facts**—the smallest useful evidence set.
5. **Factors/details**—only when they clarify the result.
6. **Recommended actions**—advisory, prioritized, and evidence-linked.
7. **Warnings / availability**—limitations and missing evidence.
8. **Next step**—one short prompt only when it materially helps the tutor.

The first screen should normally contain the title, identity, status, and most
important facts. Do not force a tutor to read background before the result.

## Typography and headings

Telegram has no semantic heading element. In the target rich-text presentation,
use bold text to create hierarchy:

- **Primary heading:** short, specific, sentence case; normally 2–5 words.
- **Section heading:** bold, sentence case; normally 1–3 words.
- **Labels:** bold label followed by a value on the same line.
- **Status and risk:** bold label and bold controlled value where prominence is
  needed, for example **Risk: MEDIUM** or **Assessment: PARTIAL**.

Do not use Markdown `#` headings, all-caps prose, ASCII boxes, tables, or code
formatting as decorative typography. Reserve uppercase for controlled states,
risk levels, academic result states, and compact operational labels.

Recommended target pattern:

```text
<b>Student progress</b>
Matias Multiple · DEMO25204

<b>Status: BEHIND</b>

<b>Key facts</b>
• Completed: 5 ECTS
• Expected: 30 ECTS
• Difference: 25 ECTS behind
```

The tags above show the intended HTML source. Telegram displays the enclosed
text as bold; users must not see the tags.

## Spacing, separators, and grouping

- Put one blank line between logical sections.
- Do not put blank lines between a section heading and its first item.
- Keep closely related label/value lines together.
- Prefer 2–5 items in one group. Split larger groups under short headings.
- Avoid more than two consecutive blank lines.
- Use `—` as a textual separator only when a visible boundary is useful in an
  unusually long response. Prefer whitespace for ordinary responses.
- Use `·` only for compact same-level identity metadata, such as
  `Matias Multiple · DEMO25204`. Do not build long delimiter chains.
- Do not imitate cards with repeated punctuation such as `====`, `*****`, or
  rows of hyphens.

## Lists and concise labels

- Use bullets for facts, factors, warnings, and unordered options.
- Use numbered lists only for actions that have an intended order or priority.
- Keep a bullet to one sentence where possible.
- Start comparable bullets with consistent labels, such as `Completed`,
  `Expected`, and `Difference`.
- Use explicit units and dates. Prefer ISO dates (`2026-08-24`) where locale is
  not otherwise established.
- Do not nest beyond one sub-level. If deeper nesting seems necessary, create a
  new section.

## Risk and status presentation

Risk must be textual, prominent, and never communicated by color or emoji alone.
Use the exact risk level returned by the owning risk model:

- **Risk: LOW**
- **Risk: MEDIUM**
- **Risk: HIGH**
- **Risk: CRITICAL**

Immediately follow the risk line with concise evidence. Name the relevant model
or scope when confusion is possible, for example `Individual progress risk` or
`Overall academic risk`. Never present a failed course, an attention shortlist,
or an operational attention signal as an overall risk classification.

Academic/result states such as `PASSED`, `FAILED`, `BEHIND`, and `ON_TRACK`
follow the same pattern: controlled uppercase value, paired with the evidence
needed to interpret it.

### Availability states

Every response that depends on multiple sources must expose one of these
presentation states when availability needs to be communicated:

| State | Meaning | Required presentation |
|---|---|---|
| **COMPLETE** | All required evidence for the stated conclusion was verified. | Show when the completeness itself matters; do not add a redundant availability section. |
| **PARTIAL** | A useful conclusion is supported, but one or more requested or optional dimensions were unavailable. | Put **Assessment: PARTIAL** near the conclusion and name unavailable dimensions under **Availability**. Qualify affected claims. |
| **UNAVAILABLE** | Required evidence is missing, invalid, or inaccessible, so the requested conclusion cannot be made safely. | Put **Assessment: UNAVAILABLE** near the top, say what could not be determined, list the missing requirement, and give a safe retry/escalation action. |

These are presentation states, not permission to rename internal result or
delivery statuses. Renderers must map structured source status deliberately.
They must not convert transport states such as `FAILED`, `NOT_SENT`, or
`NO_DESTINATION` into an academic assessment.

Approved patterns:

```text
<b>Assessment: PARTIAL</b>
Verified progress indicates MEDIUM risk. Study-right evidence was unavailable.

<b>Availability</b>
• Study right: unavailable
• Progress: verified
```

```text
<b>Assessment: UNAVAILABLE</b>
Academic risk could not be determined safely.

<b>Required information</b>
• Current progress data was unavailable.

<b>Next step</b>
Retry after the academic data service is available.
```

Do not use `N/A`, `unknown`, silence, or an empty section when the distinction
between no evidence and no concern matters.

## Recommendations

Recommendations are tutor decision support, not automated decisions.

- Use the heading **Recommended actions (advisory)**.
- Use a numbered list when order or priority matters.
- Put the most urgent or highest-value action first.
- Include priority only when it is provided by the recommendation source:
  `1. MEDIUM priority — Schedule a tutor meeting.`
- Tie actions to verified evidence in a short phrase when useful.
- Do not invent policy support. If policy retrieval is unavailable, retain the
  deterministic recommendation and disclose the missing enrichment under
  **Availability**.
- Do not recommend punitive or irreversible action from incomplete evidence.

## Warnings and errors

Warnings must be calm, specific, and actionable. Use **Warning** for a condition
that changes how the response should be interpreted and **Availability** for
missing evidence.

```text
<b>Warning</b>
This result is based on incomplete evidence. Do not interpret missing data as
confirmation that the student has no academic risk.
```

For service or delivery failures:

- state what the tutor could not obtain;
- avoid blaming the user;
- never expose exceptions, credentials, internal endpoints, IDs, or retry
  internals;
- give one safe next step;
- do not claim that a calculation failed if only Telegram delivery failed.

An emoji such as `⚠️` may optionally precede **Warning**, but the word itself is
mandatory and carries the meaning.

## Emoji policy

Emojis are optional, never structural, and normally omitted. At most one
semantic emoji should appear in a response unless a separately reviewed use
case justifies more. Acceptable uses include a single warning marker or a single
calendar marker. Do not use emoji as bullets, status scales, risk colors,
section decoration, celebrations, or substitutes for labels.

## Long-message rules

Telegram text messages have a 4,096-character limit. Design for substantially
less: a normal interactive response should target one screen and usually stay
below 1,500 characters.

When all necessary content does not fit:

1. Remove repetition, conversational filler, and lower-value explanation.
2. Preserve, in order, the conclusion, identity, risk/status, critical evidence,
   warnings/availability, and recommended actions.
3. Split by complete top-level section; never split a label from its value, a
   heading from its first item, or a warning from the claim it qualifies.
4. Prefix each part with a plain sequence label such as **Part 1 of 2**.
5. Repeat enough identity context in later parts to prevent misattribution.
6. Keep every transmitted part at or below 4,096 characters after HTML escaping,
   tags, and the part label are included.
7. Preserve rich-text validity independently in every part. Close all tags
   before a split and reopen them in the next part if needed.
8. Never truncate verified facts silently. If a complete response cannot be
   delivered, state that explicitly and direct the tutor to a narrower query.

Splitters must operate on logical sections and on the final encoded text. The
existing generic plain-text splitter is a safe transport fallback, but it is
not the target structured splitting behavior.

## Telegram rich-text rules

### Target mode

Use Telegram **HTML parse mode** for future renderer adoption. HTML is selected
as the design-system target because its small supported tag set maps directly
to the required hierarchy and avoids MarkdownV2's pervasive punctuation
escaping. This issue does not enable it in production.

Use only Telegram-supported constructs needed by this system:

- `<b>...</b>` for headings, labels, and prominent status values;
- `<i>...</i>` sparingly for a short advisory qualifier, never core facts;
- `<code>...</code>` only for literal commands or identifiers when monospace
  materially improves clarity;
- `<a href="...">...</a>` only for approved, safe, useful destinations.

Bullets and numbered lists remain ordinary Unicode/text characters; Telegram
HTML has no list tags. Do not use unsupported HTML, CSS, tables, heading tags,
or raw Markdown syntax in HTML mode.

### Escaping and safety

- Escape dynamic text for HTML before interpolation: `&` → `&amp;`, `<` →
  `&lt;`, and `>` → `&gt;`; escape quotes in link attributes.
- Treat student names, course names, recommendations, retrieved policy text,
  event names, and all other external values as untrusted presentation data.
- Add formatting tags only in the renderer. Never allow data values to supply
  markup.
- Build and validate links from approved schemes and destinations; do not place
  untrusted text directly in `href`.
- Do not parse model-generated HTML without sanitization and an allowlist.
- Test reserved characters, Unicode names, literal grade `0`, long values, and
  part boundaries before enabling parse mode.
- On formatting rejection, use an intentional escaped plain-text fallback and
  record a safe operational failure; do not drop the response silently.

## Current parse-mode behavior

Audit date: 2026-08-23. The repository uses `python-telegram-bot==22.8`.

Current behavior is plain text throughout the reviewed production paths:

- `app.telegram.handlers.handle_message` calls `reply_text(reply)` without
  `parse_mode`.
- Command handlers call `reply_text(...)` without `parse_mode`.
- `TelegramApplicationSender` calls `application.bot.send_message(chat_id=...,
  text=...)` without `parse_mode`.
- `create_bot()` does not configure application-level defaults for parse mode.
- `CommunicationAgent` explicitly produces a plain-text payload; its contract
  test asserts that `parse_mode` is absent.
- Academic alert and Monday/weekly briefing renderers generate plain text.

Therefore strings such as `**Risk**`, `<b>Risk</b>`, and `_Risk_` are currently
displayed literally rather than formatted by these call sites. There is no
shared rich-text escaping layer.

Long-message handling is also uneven:

- Academic alerts use `split_telegram_text`, enforce the 4,096-character limit,
  prefer newline/space boundaries, and prefix multiple chunks as `(n/total)`.
- Interactive replies, command replies, and Monday briefing delivery do not use
  that splitter at their send boundary.

Follow-up renderer work must introduce HTML parse mode and escaping atomically
for each delivery path, add structure-aware chunking, and preserve a safe
plain-text fallback. Setting a global parse mode before every existing string
is escaped would risk malformed messages and is prohibited.

## Realistic before/after examples

The **Before** examples reflect the current plain-text presentation style. The
**After** examples are target designs shown as Telegram-rendered text (bold is
represented with Markdown in this document). They do not change scenario data,
risk logic, or recommendation logic.

### Demo Scenario #127 — Student academic progress

Tutor: `How is he progressing?`

**Before**

```text
Matias Multiple has completed 5 ECTS. Expected progress is 30 ECTS. The student
is 25 ECTS behind expected progress (16.7% of expected progress), status BEHIND.
```

**After**

> **Student progress**  
> Matias Multiple · DEMO25204
>
> **Status: BEHIND**
>
> **Key facts**  
> • Completed: 5 ECTS  
> • Expected: 30 ECTS  
> • Difference: 25 ECTS behind  
> • Progress: 16.7% of expected

Tutor: `What academic next steps do you recommend for this student?`

> **Recommended actions (advisory)**  
> Matias Multiple · DEMO25204
>
> 1. Review the student's study plan.
>
> **Basis**  
> • Progress is 25 ECTS behind the semester expectation.
>
> **Assessment: PARTIAL**  
> Policy evidence was unavailable. The action above is based on verified
> academic progress.

The PARTIAL block is included only when the optional policy evidence is actually
unavailable.

### Demo Scenario #128 — Risk detection and explanation

Tutor: `Why is he at risk?`

**Before**

```text
Oskari Example has MEDIUM academic risk because the student is 30 ECTS behind
expected progress. Completed: 0 ECTS. Expected: 30 ECTS. Status: BEHIND.
```

**After**

> **Academic risk**  
> Oskari Example · DEMO22102
>
> **Individual progress risk: MEDIUM**
>
> **Verified evidence**  
> • Completed: 0 ECTS  
> • Expected: 30 ECTS  
> • Difference: 30 ECTS behind  
> • Progress status: BEHIND
>
> **Interpretation**  
> The 30 ECTS progress deficit meets the current MEDIUM boundary.

Tutor: `What academic next steps do you recommend for this student?`

> **Recommended actions (advisory)**  
> Oskari Example · DEMO22102
>
> 1. MEDIUM priority — Review the student's study plan.  
> 2. MEDIUM priority — Schedule a tutor meeting.
>
> **Basis**  
> • Verified progress deficit: 30 ECTS.

This wording deliberately does not turn the DBS24 failed result into an overall
risk score. The course-result shortlist and the individual progress risk remain
separate concepts.

### Demo Scenario #129 — Autonomous weekly tutor briefing

**Before**

```text
Monday briefing for Demo Tutor
Week: 2026-08-24 to 2026-08-30
Assigned students: 7
Students needing attention: 1

Priority students
- Oskari Example; 30 ECTS below expected

Availability notes
- Study-right evidence was unavailable for one or more students.
```

**After**

> **Monday tutor briefing**  
> Demo Tutor · 2026-08-24 to 2026-08-30
>
> **Assessment: PARTIAL**
>
> **Overview**  
> • Assigned students: 7  
> • Students needing attention: 1
>
> **Priority student**  
> **Oskari Example**  
> • Progress: 30 ECTS below expected
>
> **Availability**  
> • Study-right evidence was unavailable for one or more students.  
> • Missing evidence is not interpreted as no risk.

The date, tutor, assignment count, attention count, events, and availability
notes must always come from the current workflow result. `PARTIAL` appears only
when the underlying evidence is incomplete. The operational “needs attention”
signal must not be relabeled as a canonical MEDIUM/HIGH/CRITICAL risk result.

## Adoption requirements for follow-up UX issues

Production adoption is intentionally out of scope here. Each renderer migration
must nevertheless satisfy this specification and include:

1. a documented mapping from structured domain/delivery states to presentation;
2. centralized HTML escaping and a restricted formatting API;
3. explicit `parse_mode=HTML` at the migrated send boundary;
4. section-aware splitting measured on final encoded messages;
5. plain-text fallback behavior;
6. unit tests for COMPLETE, PARTIAL, UNAVAILABLE, all risk levels, escaping,
   Unicode, long messages, and formatter failure;
7. integration tests proving Telegram receives the intended parse mode and
   content without changing academic results.

Renderer changes must not move or duplicate academic calculations, risk logic,
recommendation logic, data access, or authorization into presentation code.

## Review checklist

Before approving any Telegram response or renderer:

- [ ] The conclusion appears before supporting detail.
- [ ] The identity and scope are unambiguous.
- [ ] Risk/status uses an explicit textual label.
- [ ] Verified facts, interpretation, and recommendations are separated.
- [ ] COMPLETE/PARTIAL/UNAVAILABLE is truthful and visible when relevant.
- [ ] Missing information is not presented as safety or success.
- [ ] Recommendations are clearly advisory.
- [ ] Warnings are specific and actionable.
- [ ] Formatting remains professional with all emojis removed.
- [ ] Dynamic content is escaped for the selected parse mode.
- [ ] Each final message part is at most 4,096 characters and independently valid.
- [ ] No internal/debug/security-sensitive information is exposed.
- [ ] Academic and business logic remain outside the renderer.

