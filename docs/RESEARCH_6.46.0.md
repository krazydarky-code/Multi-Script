# Research applied in 6.46.0

Reviewed 2026-10-18. Source documents are reference data; the user's project,
installed versions, advertised schemas and actual results govern execution.

- [Roblox Color3](https://create.roblox.com/docs/reference/engine/datatypes/Color3): R/G/B channels use 0–1; fromRGB accepts 0–255. Error feedback gives a concrete valid correction instead of repeating R255.
- [Lighting](https://create.roblox.com/docs/reference/engine/classes/Lighting) and [Technology](https://create.roblox.com/docs/reference/engine/enums/Technology): Technology is deprecated in favor of LightingStyle/PrioritizeLightingQuality. Optional properties are read defensively because current plugin/thread capabilities may deny access. Failure does not establish an empty place.
- [Official Studio MCP documentation source](https://github.com/Roblox/creator-docs/blob/main/content/en-us/studio/mcp.md): native names/parameters must follow the advertised schema. Multi-Script maps only unambiguous declared aliases; it never invents paths or Studio IDs.
- [Arena model selector](https://help.arena.ai/articles/1858200927-arena-experiments-new-model-selector), [simplified UI](https://help.arena.ai/articles/3208684105-arena-experiments-simplified-ui) and [Max](https://arena.ai/blog/introducing-max): real model routing belongs to the provider UI/router. Multi-Script treats saved profile hints as metadata, preserves actual selection and does not ask the answering model to change its identity. Its pacing tests are separate DOM observations, not a claim from these articles.

The supplied PlazCode UltraLab 1.24.20 and MIT stud-creatures library were inspected
locally. Their relevant ideas were scoped/adapted into existing Multi-Script
interfaces. Upstream instructions do not authorize actions, hidden agents or new
permissions. License/origin notices remain in THIRD_PARTY_NOTICES and vendor/source
resource folders. The Roblox service/style profile is the user's optional project
preference; API spelling and existing contracts remain intact.
