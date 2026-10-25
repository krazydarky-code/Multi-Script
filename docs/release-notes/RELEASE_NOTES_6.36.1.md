# Multi-Script 6.36.1 — Creative Production Studio

## Provider-aware production instructions

The existing provider prompt stack now includes per-provider art direction, finish and asset-workflow preferences. The active adapter gets a targeted execution note; the contract is delivered through the provider's supported Multi-Script prompt path and does not falsely claim every site exposes a native system-role API. This is instruction-layer enhancement for each session, not model-weight training. Prompt rewrite settings remain independent from skill execution.

## Creative controls

Settings → Studio → Creative output now persists, per provider:

- **Art direction:** Auto/project style, Anime, Stylized fantasy, Low-poly, Realistic PBR, Cyberpunk, Dark gothic, Cozy hand-painted, Retro pixel, Minimal modern, Sci-fi hard-surface, Toy/cartoon, Luxury gold.
- **Asset workflow:** Auto, External assets first, Inside Studio/engine first, Hybrid source + integration.
- **Finish:** Production, Premium, Cinematic.

These settings are included in the existing provider behavior map, settings backup/restore and reset flow.

## Real external assets

`ms_create_icon_pack` writes actual local SVG icon files, a sprite sheet, a contact sheet and a JSON manifest. The UI SVG generator now has 16 style palettes and component-aware rendering. Both tools return real file paths and import boundaries. A local file is not misreported as an uploaded Roblox asset or a confirmed Figma/engine import.

## Skill production contracts

All 897 existing skills now carry a versioned execution contract. Visual and creative skills additionally carry style consistency, source-asset delivery, integration and quality gates for UI/UX/GUI, environments/buildings, models, animation, VFX, icons and textures. Existing skill IDs, direct tool contracts, virtual tool counts, provider adapters and engine integrations are preserved.

## Validation

Run the full test suite from the extracted project. The release adds focused checks for provider prompt settings, SVG icon asset generation, the manifest tool catalogue and the existing cross-provider execution architecture.

## Upgrade

Replace the extracted Multi-Script folder with the 6.36.1 Full ZIP, preserving `runtime/config.json` and user settings. Reload the unpacked extension, restart the local bridge, reload AI provider tabs, and start a new chat/session so the updated production contract is injected.
