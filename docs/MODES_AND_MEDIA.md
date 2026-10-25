# Discord setup posts: workspaces, sounds and animation

Each section below can be copied as its own forum post.

## Studio engine: connect your real editor

Install the current Multi-Script Dev build, run Setup and start the local bridge. Open the intended editor/project and enable its MCP integration. In Roblox, enable Studio as MCP Server; the optional Multi-Script companion adds its own toolset. Open a fresh AI chat and start the engine session. Ask it to discover the available commands and inspect the project before editing. A connection does not mean every capture, import or upload permission is granted.

## Chat studio: work without an editor

Use Chat studio for planning, code, designs and general local tools without attaching a game engine. Start it in a fresh conversation. Connected editors elsewhere on your PC remain isolated from this session. It will not change your open Roblox/Godot/Unity/Blender project. To edit an actual engine project, open a new conversation and choose Studio engine mode instead.

## Build software / Code: use a desktop folder

Enable the workspace in Settings → Code & Build, choose or create a project folder and configure file/command permissions. Start Build software or Code in a fresh chat. The AI uses local workspace tools to inspect files, make changes and run permitted build checks. Roblox Studio is not required. Engine and other MCP access are optional add-ons.

## Interface sounds and live themes

Multi-Script's sound setting controls browser notification tones. Preview them in Settings. Live themes and motion settings animate the Multi-Script interface, including the chatbar. These settings do not add music, sound effects, rigs or animations to a game. Reduced-motion settings can make animated themes quieter or static.

## Game audio: real assets and playback

Connect the target editor in Studio engine mode. Tell the AI what the audio should do, which existing assets it may use and any licensing constraints. Generated local WAV files need an actual supported import/upload step before an engine can use them. Roblox SoundId values must refer to real, permitted uploaded assets. Ask for playback testing in the game; a filename or invented ID is not a working sound.

## Game animation: rig, clip and test

Connect the target editor, identify the rig/skeleton and describe the movement. Have the AI inspect existing actions, weights, constraints and controllers. Author or import a real animation, connect it to the character/controller and test transitions in the engine. Roblox AnimationId values require real uploaded assets and appropriate permissions. Interface motion settings do not create these clips.

## Notion and Vani: use the correct chat

Open Notion's AI Agent conversation or Vani's actual chat (`c.vani.ai`), then refresh after upgrading Multi-Script. Start the intended workspace mode and let initialization finish. Local tools run through the Multi-Script bridge using advertised commands; they are distinct from provider-native connectors. If delivery is unconfirmed, inspect the conversation before retrying. Multi-Script pauses instead of repeatedly sending the same tool result.

Choose models in the provider's own controls when your account permits it. A saved model name in a prompt cannot change the backend or unlock a plan. Notion eligibility is controlled by the workspace: [official model controls](https://www.notion.com/en-gb/help/manage-ai-models-and-member-credit-spend).

## Update without losing settings

Use Settings → Help → Updates. Check/download, stop active sessions, then Apply & reload extension and refresh provider tabs. Keep the same permanent installation folder and browser profile. Replace the Roblox companion from the new Dev package and restart Studio when its version changes; extension updates cannot install native Studio plugins automatically. Keep frozen Public separate from the current Dev installation.

## Local mockups and editor interfaces

`ms_create_canvas_ui` writes an SVG mockup under `runtime/generated/canvas` in the registered bridge installation. Its result explicitly reports `nativeUiCreated: false` and `engineImported: false`. A path containing an older version means that older folder is still registered; inspect Help → Updates and run Setup from the folder your browser actually loads.

An SVG mockup does not create a Roblox ScreenGui, Godot Control, Unity Canvas or Figma design. Native UI tasks must use connected editor tools to implement the interface and then verify it. All effort levels reject treating a local mockup as completed native implementation. Explicit requests for SVG/mockups can finish with the local artifact.

Effort methods are shown as collapsed chips beneath the original prompt. The complete prompt, method, enabled skills and other add-ons are still sent together. Receipt storage contains hashes and layout offsets, not copies of your prompt. Expand the chip to inspect the method; choose Show original message and controls to use native message actions. Only verified extension-sent messages are collapsed.

## Effort appearance and support

The chatbar names the selected Adaptive, Quick, Standard, Deep, Maximum or Ultra effort beside Multi-Script. Agent settings provide a keyboard/touch slider and direct stop buttons. Ultra colors offer Amethyst, Rainbow, Aurora and Sunset; animation offers Live flow, Soft pulse and Static. These preferences survive settings backup/import and respect system reduced-motion and forced-color settings. They change presentation only. Existing manuals and tool permissions remain in force.

The Home panel's Support Multi-Script card opens https://ko-fi.com/multixscript when clicked. Arena's optional model-preference metadata starts off; select a profile explicitly to opt in. Use Arena's native model selector to choose an actual backend.

## Chatbar presentation correction (6.49.8)

Desktop composers keep identity/status beside the controls in one compact row; phone-width bars may wrap. Auto and Floating use the available composer width. Each effort level is named beside Multi-Script, with gradient animation reserved for Ultra. Ordinary slider stops use neutral colors; Ultra's slider follows its selected palette. The glowing heart in the chatbar and the Home support card both open https://ko-fi.com/multixscript. Chat bar settings can hide the heart. Permanent Unstable labels have been removed; actual connection/delivery errors still appear when encountered.

## Automatic progress and optional checklists (6.49.9)

Every effort level starts the actual task directly. Multi-Script tracks response stages and tool activity locally. A detailed checklist is optional; use one when it helps coordinate a substantial task or the user asks for progress. Keep one plan and batch meaningful milestone changes with ms_task_progress updates. Done still requires real verification evidence; blocked work stays visible. Full checklist reads retain all evidence, while update receipts stay short. Timing estimates are optional. Ultra's relevant methods and verification remain active without a separate progress-planning ritual.

The initial catalogue lists direct tool names and discovery/retrieval schemas. Use list_commands with names/query or ms_direct_tool_details for exact parameters. Retrieve more_output pages only when they contain information needed for the current task. Existing stored evidence remains available; no tool permissions or native tools are granted by these optimizations.
