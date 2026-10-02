# Data-quality audit

Audit date: 2026-10-02. Database audited: `data/students.db` before the provenance migration. A byte-for-byte backup is stored at `data/students.db.pre_quality_2026-10-02.bak`.

## Findings

| Finding | Affected rows | Treatment |
|---|---:|---|
| Placeholder faculty names (`Faculty Member N`) | 20 | Preserved, labeled `synthetic_demo`; no real people were invented. |
| Placeholder course names (`Engineering Course N`) | 30 | Preserved, labeled `synthetic_demo`; replace only with a verified curriculum import. |
| Placeholder library authors (`Author N`) | 15 | Preserved, labeled `synthetic_demo`; no fabricated bibliography is presented as authentic. |
| `@college.example` student emails | 81 | Preserved for compatibility, labeled synthetic; not treated as contact data. |
| `@college.example` teacher emails | 20 | Preserved for compatibility, labeled synthetic; not treated as contact data. |
| Synthetic `910000...` student phones | 81 | Preserved for compatibility, labeled synthetic; not treated as contact data. |
| Students with NULL gender | 19 | Left NULL because gender is optional and no source can safely fill it. |
| Orphan student departments | 0 | No correction required. |
| Student marks outside 0--100 | 0 | No correction required. |
| Results above exam maximum | 0 | No correction required. |
| Duplicate enrollment keys | 0 | Existing uniqueness constraint is effective. |
| Duplicate attendance day keys | 0 | Existing uniqueness constraint is effective. |

The database contains 100 students, 20 teachers, 6 departments, 30 courses, 300 enrollments, 100 exams, 575 results, 600 attendance rows, 100 fee rows, 20 classrooms, 30 timetable rows, 15 library books, and 87 library transactions. These records are retained, but the migration records their origin as `synthetic_demo`; they are not verified real-college records.

## Authenticity decision

No student-level public dataset was imported. Public availability does not establish permission to republish personal student records or academic/financial history, and the project has no reliable source mapping for the existing rows. AISHE provides official institution-level higher-education statistics and directory information, not a license to manufacture missing student records. The India OGD platform states that its published data is under the Government Open Data License - India; its AISHE college catalog is therefore recorded as a potential source for future institution metadata, subject to dataset-level attribution and compatibility checks.

## Provenance

The `data_provenance` table stores source name, URL, terms, retrieval date, origin, and notes. Every existing operational table now has `provenance_id` and `data_origin`. New authentic imports must use `verified_public` and cite a source; synthetic rows must remain `synthetic_demo`.

## Remaining limitations

The current data still has synthetic names, contacts, courses, books, results, attendance and fees. It is suitable for testing application behavior, not for claims about a real Indian engineering college. Replacing those rows requires a verified, compatible source and a documented import, not generated filler.
