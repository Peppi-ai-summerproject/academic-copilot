# Issue #252 — Realistic academic demo dataset

DIN24 is the canonical student group. Course results remain authoritative
`course_completions`; enrollment without a completion remains a distinct
IN_PROGRESS/NO_RESULT state. Existing Elina, Oskari, and Sofia records are not
overwritten by migration 010.

## Personas

| Student number | Fictional student | Profile | Deterministic progress characteristic |
|---|---|---|---|
| DEMO22101 | Elina Demo | Existing mixed record; DII101 5 and DBS24 4 | 10 passed ECTS, semester 2, behind |
| DEMO22102 | Oskari Example | Existing multiple failures | 0 passed ECTS, DII101/DBS24 grade 0 |
| DEMO22103 | Sofia Sample | Enrolled without DBS24 completion | No DBS24 result |
| DEMO25201 | Aava Achiever | Excellent | 60 ECTS at semester 2, ON_TRACK |
| DEMO25202 | Niko Normal | Normal | 30 ECTS at semester 1, ON_TRACK |
| DEMO25203 | Petra Partial | One failed course | 25 ECTS, DBS24 FAILED, LOW progress risk |
| DEMO25204 | Matias Multiple | Multiple failures and low credits | 5 ECTS, DBS24/WEB24 FAILED, LOW progress risk |
| DEMO25205 | Liisa Delayed | Outstanding enrollments | 15 ECTS, LOW progress risk, remaining courses have no result |
| DEMO25206 | Eero Mixed | Mixed performance | 55 ECTS at semester 2, WEB24 FAILED, LOW progress risk |

Risk descriptions above cover the progress dimension only. The current risk
algorithm does not score failure count directly, and complete overall academic
health also depends on study-right, meeting, and event evidence.

## Key course-result matrix

| Student | DII101 | DBS24 | WEB24 |
|---|---|---|---|
| Elina | PASSED 5 | PASSED 4 | no seeded completion |
| Oskari | FAILED 0 | FAILED 0 | no seeded completion |
| Sofia | no completion | enrollment, no completion | no seeded completion |
| Aava | PASSED 5 | PASSED 5 | PASSED 5 |
| Niko | PASSED 3 | no completion | no completion |
| Petra | PASSED 3 | FAILED 0 | no completion |
| Matias | PASSED 2 | FAILED 0 | FAILED 0 |
| Liisa | PASSED 3 | no completion | no completion |
| Eero | PASSED 4 | PASSED 4 | FAILED 0 |

Supporting five-credit courses make the progress personas deterministic:
BUS101, PRG101, UXD101, NET101, PRJ101, DAT102, API102, SEC102, and CLD102.

## Demonstration queries

- `Which students are in DIN24?`
- `Who passed Database Systems in DIN24?` returns multiple students, including Elina, Aava, and Eero.
- `Who failed Database Systems in DIN24?` returns multiple students, including Oskari, Petra, and Matias.
- `Who passed DII101 in DIN24?`
- `Who failed DII101 in DIN24?`
- `Who passed Web Application Development in DIN24?`
- Individual progress and risk questions demonstrate ON_TRACK and BEHIND profiles.

Migration 010 inserts only absent canonical identities and relationships. Any
pre-existing conflicting student, course, enrollment, or completion remains
authoritative and is not updated or deleted.
