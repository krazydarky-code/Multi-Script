# Forge: game art that becomes working Roblox UI and effects

## How to use it

Just ask in the chat, in normal words. You never type tool names.

- "Make me a cartoon shop UI with coins, gems and rarity slots."
- "Give my game a neon sci-fi HUD with health and XP bars."
- "Copy the colours from C:\Users\me\Pictures\my-ui.png and make an inventory."
- "Add a sparkly explosion when a pet hatches, and a fire effect on the torches."
- "Make a 16:9 thumbnail background, sunset style."

Roblox Studio should be open with its MCP server switched on, so Forge can upload the art and install it.

## What happens in that one step

1. The extension draws the art in your browser (no extra programs or Python add-ons).
2. The bridge saves the pictures on this computer.
3. Studio uploads them to your Roblox account (they go through Roblox moderation).
4. A uniquely named ModuleScript is written into ReplicatedStorage, preserving existing modules and files:
   - `ForgeKit_<generation>` for native UI builders; only selected artwork is drawn/uploaded, with complete states for that pack.
   - `ForgeVFX_<generation>` for effects whose textures returned upload IDs.
5. A preview is opt-in (`demo=true`), with a fresh generation name. An actual screenshot/playtest is a separate verification step. Existing scenes are preserved.
6. The AI builds the requested screens/effects using the returned module path. Source installation and returned asset IDs do not prove moderation, asset loading, input behavior or performance; verify these in Studio.

## Styles and packs

Styles: simulator, cartoon, glossy, candy, anime, glass, neon, fantasy, scifi, minimal, horror, pixel.

Packs keep uploads focused: hud, shop, inventory, settings, leaderboard, dialogue, rewards, essentials (the default) or explicit full. An `elements` prefix list can narrow artwork further. Selection happens before drawing; no required states are silently discarded to meet an arbitrary image cap.

## Without Studio

Forge still draws the art and keeps it in `runtime/generated/forge/<name>/`. You can import the files in Studio (Asset Manager, Bulk Import) and ask the AI to bind them.
