# Check Suite

Two strict standards are built in as skills (241 skills in total):

- `check-clean-ui`: the cartoon/simulator UI standard (menus, HUDs, buttons).
- `check-props`: the standard for props, buildings, trees, rocks and machines built in Studio from Parts, unions and Luau.

Retrieve either with `ms_get_skill`. Both are `general` engine skills in the `check-suite-expansion` pack.

## Private checks

The AI runs every check itself in Studio and fixes failures before replying. It does not show the user check codes, rule numbers, specs, prop names or ids, colour values or asset ids unless asked. The user gets a short plain message about what was made and where it is, plus only anything they need to look at or do. The AI never claims the visual look or a playtest is confirmed.

## Small prompt

Paste into custom instructions if you want the AI to use the suite without being asked:

> Roblox build rules. Before building any menu, HUD or button, load `check-clean-ui`. Before building any prop, building, tree, rock or machine in Studio, load `check-props`. Follow them exactly; they override your defaults. Do all the checks yourself in Studio and fix every failure before replying. Keep all of this private: don't mention the skills, rules, check codes, ids or specs to the user unless they ask. Reply with a short plain message about what you made and where it is, plus only anything they need to look at or do. Never say it works or looks good unless you measured it.

## Notes

- `check-clean-ui` resolves three contradictions in its source standard with stated defaults (state buttons use the iconless recipe, windows use the 4-point damier fade and buttons the 2-point fade, Skip is an iconless button).
- The damier texture id (`rbxassetid://385956923`) and any other asset ids must be confirmed to load in the experience; the skill falls back to a plain fill.
- `check-props` is condensed from the longer UltraLab Check-Props; numbers marked (design) are starting values to replace with measured ones.
