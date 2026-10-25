# Multi-Script 6.11.0 — Arena Direct Max Adaptive Router

- Added an Arena-only **Direct Max · Adaptive Studio Router** profile, separate from Notion Auto.
- The profile classifies every outgoing turn across eight capability groups and adds one compact, retry-idempotent prompt-only routing signal.
- Arena’s own legitimate router remains responsible for the backend model and may switch as task needs change. Multi-Script does not click the picker, guarantee a model, expose hidden reasoning, or bypass access controls.
- Existing fixed preferred-model Arena profiles remain optional.
- Confirmed the existing Blender delivery pipeline already exports and imports models, textures/materials, rigs and animations into the connected target engine, followed by native read-back and runtime validation. No duplicate handoff layer was added.
