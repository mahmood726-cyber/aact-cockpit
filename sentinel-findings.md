# sentinel-findings.md

*Written by Sentinel — WARN-tier findings.*

## [WARN] P1-unpopulated-placeholder
- **Location:** `src/aact_engine/audits.py:22`
- **Detail:** pattern matched: _OLDER = f"{_FIRST_YEAR} IS NOT NULL AND {_FIRST_YEAR} <= {{cut}}"
- **Fix hint:** Populate the placeholder or escape it before shipping. If the braces are intentional template syntax in a non-template file, exclude the file path via the rule's exclude list.

- **Source:** html-apps.md#safety-checks
- **When:** 2026-06-01T09:39:21.644140+00:00

## [WARN] P1-aact-field-semantics
- **Location:** `src/aact_engine/audits.py:263`
- **Detail:** filters on AACT field 'is_us_export', which means a product EXPORTED from the US for study abroad — NOT whether the trial has US sites or US nexus (~3% of trials) — confirm this is the intended semantics
- **Fix hint:** verify the field's AACT data-dictionary meaning; if intended, document it (e.g. a FLAG_META-style note) and add sentinel:skip-file
- **Source:** C:\Users\mahmo\.claude\projects\C--Users-mahmo\memory\aactcockpit_project.md
- **When:** 2026-06-01T09:39:22.014979+00:00
