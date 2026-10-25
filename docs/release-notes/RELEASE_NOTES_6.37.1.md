# Multi-Script 6.37.1

The chatbar now has one labeled Studio control instead of four tiny symbol buttons. New idea and Critic have larger SVG icons, readable descriptions and 60 px action rows in a contextual menu. Sandbox/Ask appears inside this menu only while opened. The menu closes on selection, click-away, Escape, focus leaving, resize and external scrolling; keyboard arrow navigation and focus restoration are supported. Studio actions can be hidden in Look → Chat bar options.

The redundant provider name on the Settings button was removed and long status text is capped at 180 px, with its full text available in the tooltip. The contextual menu stays above the composer rather than covering its input when the bar is docked below it.

Ultra remains the sixth position on the Agent reasoning slider. The extra reasoning shortcut was removed from the chatbar. Live chatbar themes continue to run on their own scene layer.

Crax registration, popup support detection, site links and provider diagnostics now use crax.gpt.lol. Browser navigation still failed DNS here, so live support remains unverified. The role-based transport is tested in local browser fixtures.

This revision includes the full 6.37 studio/runtime changes in both Dev and Public packages. See the included QA report for verification and limitations.
