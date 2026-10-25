# Multi-Script 6.9.0 — Engine Schema Assurance

- Added recursive live-MCP parameter validation for nested objects/arrays, composition, local references, defaults, nullability, strict integers, patterns, bounds, enums/const, uniqueness, and forbidden unknown parameters.
- Bound engine-named direct specialists to their declared engine.
- Added runtime compatibility and recovery contracts to all 800 skills and 300 virtual specialists.
- Added `ms_mcp_schema_audit`, bringing the direct catalogue to 210 tools. It assigns deterministic heuristic risk estimates to currently advertised native schemas without mutating projects.
- Added an explicit compatibility risk model. Probabilities are prioritization estimates, not guarantees or observed universal failure rates.
- Preserved live-schema-only execution, exact server routing, schema refresh, bounded transient retry, and native read-back requirements.
