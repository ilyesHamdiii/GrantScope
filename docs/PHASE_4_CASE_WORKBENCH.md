# GrantScope Phase 4: Case Workbench

## Goal

Turn related findings into an analyst-ready investigation case packet.

## Case grouping rule

GrantScope groups findings by:

- `subject_type`
- `subject_external_id`
- `import_run_id`

For the demo tenant, this produces three cases:

1. Provisioning Bridge
2. CloudSync Assistant
3. Directory Administration Integration

## Case contents

Each case includes:

- Highest severity and confidence across related findings
- Grouped findings
- Deduplicated evidence index
- Chronological timeline
- Missing-data notes
- “What would make this benign?” checklist
- Recommended human review actions
- Markdown and HTML report exports

## Design limitation

Case generation is currently idempotent and regenerates machine-generated cases for one import run. Analyst-editable case state and manual annotations will be added later.