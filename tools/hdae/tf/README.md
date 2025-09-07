# H-DAE Task Functions (TFs)

- Location: this directory (`tools/hdae/tf`).
- Format: YAML files validated against `tools/hdae/schema/tf.schema.json`.
- Status field:
  - `active`: participates in scan/apply.
  - `stub`: placeholder (metadata present, not executed).
  - `disabled`: excluded from pipeline.

Loader notes:
- The CLI uses a minimal, stdlib-only YAML subset loader compatible with these files.
- Keep values simple (scalars and flat lists) to preserve determinism and portability.

