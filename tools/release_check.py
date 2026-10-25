#!/usr/bin/env python3
"""Offline release gate for Multi-Script."""
from pathlib import Path
import json, re, subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
VERSION="6.50.0"
errors=[]
def need(ok,msg):
    if not ok: errors.append(msg)
def load(path):
    try:return json.loads((ROOT/path).read_text(encoding='utf-8'))
    except Exception as e: errors.append(f'{path}: {e}'); return {}
manifest=load('extension/manifest.json')
need(manifest.get('manifest_version')==3,'manifest must be v3')
need(manifest.get('version')==VERSION,'manifest version mismatch')
need(str(manifest.get('version_name','')).startswith(VERSION),'manifest version_name mismatch')
build_release=(ROOT/'tools/build_release.py').read_text(encoding='utf-8')
need("manifest.json" in build_release and "['version']" in build_release,
     'release builder must derive its version from the extension manifest')
overlay=(ROOT/'extension/overlay.css').read_text(encoding='utf-8')
need('#zs-stop[hidden] { display: none !important; }' in overlay,
     'chatbar Stop button can override its hidden state')
bridge=(ROOT/'runtime/bridge.py').read_text(encoding='utf-8')
need(f'BRIDGE_VERSION = "{VERSION}"' in bridge,'bridge version mismatch')
need('Py_GIL_DISABLED' in bridge and 'proc.stdin.close()' in bridge,
     'bridge lost free-threaded Python or graceful stdio shutdown hardening')
notion=(ROOT/'extension/providers/notion.js').read_text(encoding='utf-8')
need(f'dataset.zsNotionVer = "{VERSION}"' in notion,'Notion adapter version mismatch')
required=['runtime/product-manifest.json','tools/critic_loop.py','docs/VSCODE_EXTENSION_FUTURE.md','README.md','LICENSE','CHANGELOG.md','CONTRIBUTING.md','docs/INSTALL.md','docs/PRIVACY.md','docs/SECURITY.md','docs/SUPPORT.md','docs/THIRD_PARTY_NOTICES.md','docs/RELEASE_CHECKLIST.md','runtime/config.example.json','runtime/studio-standard.json','roblox-plugin/MultiScriptCompanion.server.lua','docs/ROBLOX_PLUGIN.md','runtime/mobile_remote.py','runtime/phone/index.html','runtime/phone/phone.js','runtime/phone/phone.css','extension/mobile-control.js','extension/core/task-progress.js','docs/PHONE_CONTROL.md','tests/test_mobile_remote.py','tests/test_mobile_bridge_wire.py','tests/test_mobile_worker.js','tests/test_progress_phone_browser.js','tests/test_task_progress.js']
required += ['runtime/figma_link.py','runtime/launch_figma_mcp.py','figma-plugin/manifest.json','figma-plugin/code.js','figma-plugin/ui.html','extension/core/ultra-manuals.js','docs/FIGMA.md','docs/CLICKUP.md','docs/ULTRA_MANUALS.md','tests/test_figma_bridge.py','tests/test_figma_ui_roundtrip.js','tests/test_ultra_manuals.js']
required += ['extension/core/ultra-craft.js','extension/updates.js','runtime/update_manager.py','runtime/update-channel.json','tools/sign_update.py','docs/UPDATES.md','tests/test_update_manager.py','tests/test_updates.js','tests/test_updates_browser.js','tests/test_ultra_craft.js']
required += ['extension/core/execution-discipline.js','runtime/skill_references.py','runtime/skill-resources/stud-creatures/LICENSE','runtime/skill-resources/stud-creatures/MULTI-SCRIPT.md','runtime/skill-resources/roblox-service-style/GUIDE.md','legal/upstream-gpl/1.24.20-LICENSE.txt','legal/upstream-gpl/1.24.20-BRANDING-NOTICE.txt','tests/test_execution_guard_loop_646.js','tests/test_effort_delivery_646.js','tests/test_chat_studio_isolation_646.js','tests/test_skill_references_646.py','tests/test_roblox_probe_capabilities_646.py']
required += ['runtime/tool_discovery.py','runtime/plugin_console.py','docs/MODES_AND_MEDIA.md','docs/QA_6.50.0.md','tests/test_tool_discovery_647.py','tests/test_plugin_transfer_wire_647.py','tests/test_roblox_workbench_647.py','tests/support/roblox-plugin-host.lua','tests/test_tool_discovery_browser_647.js','tests/test_notion_runtime_roundtrip_647.js','tests/test_plugin_workbench_preview_647.js']
required += ['extension/core/update-panel.js','extension/core/roblox-production.js','runtime/skill-resources/roblox-production/methods.json','runtime/skill-resources/roblox-production/GUI.md','runtime/skill-resources/roblox-production/ANIMATION.md','runtime/skill-resources/roblox-production/PROVENANCE.json','tools/sync_production_methods.py','tests/test_updates_recovery_648.js','tests/test_update_reliability_648.py','tests/test_update_progress_browser_648.js','tests/test_production_methods_648.js','tests/test_production_resources_648.py']
required += ['tests/test_chatgpt_composer_6481.js','tests/test_native_methods_6484.js','tests/test_native_popups_6484.js','tests/test_gemini_compatibility_6484.js','tests/test_v24_catalogue_6484.py','runtime/skill-restorations.json','tests/test_startup_budget_6485.js','tests/test_ultra_scope_6485.js','tests/test_restored_specialists_6485.py','tests/test_startup_comparison_6485.js','tests/test_update_setup_6481.py','tests/test_update_setup_worker_6481.js','tests/test_chatgpt_runtime_roundtrip_6481.js','tests/test_claude_runtime_roundtrip_6481.js']
need(not (ROOT/'extension/providers/crax.js').exists(),'Crax adapter must be removed from the current build')
need('crax.gpt' not in json.dumps(manifest),'Crax must not remain in active manifest support')
required += ['tests/test_composer_docking_6482.js','tests/test_chatbar_studio.js','tests/test_notion_route_guard.js','tests/test_provider_benchmarks.js','tests/test_studio_ui.js']
required += ['tests/test_bar_presentation_6483.js','tests/test_gemini_runtime_roundtrip_6483.js','tests/test_gemini_startup_failure_6483.js','tests/test_chatgpt_article_roundtrip_6483.js']
required += ['tests/test_provider_error_reload_6483.js','tests/test_deepseek_send_safety_6486.js','tests/test_deepseek_pacing_6486.js','tests/test_deepseek_startup_6486.js','docs/DEEPSEEK_ACCOUNT_ACCESS.md','tests/test_deepseek_engine_startup_6487.js']
required += ['runtime/ultra-handbook.json','runtime/ultra_handbook.py','extension/core/ultra-handbook.js','tools/sync_ultra_handbook.py','tests/test_ultra_handbook_6488.js','tests/test_handbook_skills_6488.py','tests/test_handbook_browser_6488.js','tests/test_provider_boundaries_6488.js']
required += ['runtime/blender_workspace.py','runtime/blender_workspace_worker.py','runtime/blender_workspace_http.py','runtime/blender_portable.py','runtime/blender-runtime.json','runtime/blender-studio/index.html','runtime/blender-studio/studio.js','runtime/blender-studio/studio.bundle.js','runtime/blender-studio/studio.css','runtime/blender-studio/package-lock.json','runtime/blender-studio/THIRD_PARTY_LICENSES.txt','docs/BLENDER_WORKSPACE.md','tests/test_blender_workspace_real_6490.py','tests/test_blender_workspace_browser_6490.js']
required += ['extension/blender-tabs.js','extension/workspace-link.js','runtime/blender-studio/assistant.js','tests/test_gemini_slow_response_6491.js','tests/test_blender_session_grants_6491.js','docs/QA_6.50.0.md']
required += ['runtime/blender_pipeline.py','runtime/blender_preview_materials.py','runtime/blender-studio/pipeline.js','tests/test_blender_companion_real_6492.py','tests/test_blender_companion_entry_6492.js','tests/test_blender_preview_persistence_6492.py','tests/test_provider_regressions_6492.js','docs/QA_6.50.0.md']
required += ['tests/fixtures/ultra-before-6493.json','tests/test_existing_manual_expansion_6493.py','tests/test_existing_manual_browser_6493.js','docs/QA_6.50.0.md']
required += ['tests/test_provider_composers_6495.js','tests/test_chatgpt_rich_roundtrip_6495.js','docs/QA_6.50.0.md']
required += ['tests/test_prompt_reference_delivery_6496.js','tests/test_blender_target_routing_6496.py','tests/test_blender_target_entry_6496.js','docs/QA_6.50.0.md']
required += ['runtime/blender_worker_lifecycle.py','tests/test_blender_connection_faults_6497.py','tests/test_blender_owner_lifecycle_6497.py','tests/test_glm_runtime_roundtrip_6497.js','tests/test_kimi_runtime_roundtrip_6497.js','tests/test_glm_kimi_sends_6497.js','tests/test_effort_appearance_6497.js','docs/QA_6.50.0.md']
required += ['tests/test_compact_effort_bar_6498.js','tests/test_effort_slider_6498.js','tests/test_provider_bar_resize_6498.js','docs/QA_6.50.0.md']
required += ['tests/test_progress_efficiency_6499.js','tests/test_vani_progress_performance_6499.js','tests/test_catalog_paging_6499.js','docs/QA_6.50.0.md']
required += ['tests/test_scene_bar_layout_6499.js','tests/test_scene_bar_resize_6499.js']
required += ['tests/test_bar_space_recovery_6499.js','tests/test_response_recovery_6499.js','tests/test_task_activity_6499.js','tests/test_arena_stream_performance_6499.js','tests/test_incremental_application_6499.js','tests/test_prompt_wording_ab_6499.js','tests/test_menu_idle_layout_6499.js']
for x in required: need((ROOT/x).is_file(),f'missing {x}')
handbook=load('runtime/ultra-handbook.json')
need(len(handbook.get('manuals',{}))==12,'handbook must retain all twelve specialist domains')
need(sum(len(steps) for m in handbook.get('manuals',{}).values() for steps in m['phases'].values())==564,'handbook checkpoint count mismatch')
for mid,m in handbook.get('manuals',{}).items():
    need((ROOT/'docs/ultra-handbook'/(mid+'.md')).is_file(),'missing readable handbook '+mid)
product=load('runtime/product-manifest.json')
need(product.get('version')==VERSION,'product manifest version mismatch')
plugin=(ROOT/'roblox-plugin/MultiScriptCompanion.server.lua').read_text(encoding='utf-8')
need(f'PLUGIN_VERSION = "{VERSION}"' in plugin,'Roblox plugin version mismatch')
companion=product.get('robloxCompanion') or {}
need(companion.get('companionTools')==26,'Roblox companion tool count mismatch')
need(companion.get('defaultPermission')=='off','Roblox companion must default Off')
need((companion.get('security') or {}).get('arbitraryCodeEvaluation') is False,'arbitrary plugin code evaluation must remain disabled')
need('loadstring(' not in plugin,'Roblox companion must not evaluate arbitrary Lua')
for route in ['/status','/catalog','/plugin/heartbeat','/plugin/register','/plugin/next','/plugin/result','/plugin/unregister']: need(route in plugin,f'missing plugin route {route}')
companion_tools=load('runtime/roblox-plugin-tools.json').get('tools',[])
need(len(companion_tools)==26 and len({x.get('name') for x in companion_tools})==26,'companion catalog must contain 26 unique tools')
for tool in companion_tools: need(f"handlers.{tool.get('name')}=" in plugin,f"missing companion handler: {tool.get('name')}")
for x in ['runtime/elevenlabs_audio.py','runtime/configure_elevenlabs.py','runtime/.env.example']: need((ROOT/x).is_file(),f'missing {x}')
need((ROOT/'docs/MODEL_WATCH.md').is_file(),'missing model watch')
need((ROOT/'tests/test_notion_prompt_only_routing.js').is_file(),'missing prompt-only routing test')
need((ROOT/'tests/test_cross_provider_tool_matrix.js').is_file(),'missing cross-provider tool matrix')
need((ROOT/'tests/test_arena_roblox_json_protocol.js').is_file(),'missing Arena Roblox JSON protocol test')
need((ROOT/'extension/core/tool-routing.js').is_file(),'missing exact engine tool resolver')
need((ROOT/'tests/test_engine_tool_routing.js').is_file(),'missing engine routing regression')
need((ROOT/'tests/test_settings_customization.js').is_file(),'missing customization UI test')
need((ROOT/'tests/test_elevenlabs_settings.py').is_file(),'missing ElevenLabs settings test')
need((ROOT/'tests/test_roblox_companion.py').is_file(),'missing Roblox companion test')
need((ROOT/'tests/test_tool_parameter_contracts.py').is_file(),'missing parameter contract test')
need((ROOT/'tests/test_model_improvement_layer.py').is_file(),'missing model-improvement architecture test')
need((ROOT/'tests/test_creative_production_6361.js').is_file(),'missing 6.50.0 creative production prompt/settings test')
need((ROOT/'tests/test_creative_asset_pack_6361.py').is_file(),'missing 6.50.0 icon asset generation test')
need((ROOT/'tests/test_full_spectrum_skill_mesh.py').is_file(),'missing full-spectrum skill mesh test')
need('ms_roblox_capability_audit' in direct_names if 'direct_names' in locals() else True,'missing Roblox capability audit')
need((ROOT/'tests/test_arena_human_verification.js').is_file(),'missing Arena verification test')
need((ROOT/'tests/test_roblox_studio_id.js').is_file(),'missing Roblox studio_id contract test')
need((ROOT/'tests/test_required_param_contract.js').is_file(),'missing required-parameter contract test')
need((ROOT/'docs/release-notes/RELEASE_NOTES_6.17.3.md').is_file(),'missing 6.17.3 release notes')
need((ROOT/'docs/release-notes/RELEASE_NOTES_6.17.4.md').is_file(),'missing 6.17.4 release notes')
need((ROOT/'docs/release-notes/RELEASE_NOTES_6.23.0.md').is_file(),'missing 6.23.0 release notes')
need((ROOT/'docs/release-notes/RELEASE_NOTES_6.25.0.md').is_file(),'missing 6.25.0 release notes')
need((ROOT/'docs/release-notes/RELEASE_NOTES_6.28.2.md').is_file(),'missing 6.28.2 release notes')
need((ROOT/'docs/release-notes/RELEASE_NOTES_6.28.3.md').is_file(),'missing 6.28.3 release notes')
need((ROOT/'docs/release-notes/RELEASE_NOTES_6.29.0.md').is_file(),'missing 6.29.0 release notes')
need((ROOT/'docs/release-notes/RELEASE_NOTES_6.29.1.md').is_file(),'missing 6.29.1 release notes')
need((ROOT/'docs/release-notes/RELEASE_NOTES_6.50.0.md').is_file(),'missing 6.50.0 release notes')
readme=(ROOT/'README.md').read_text(encoding='utf-8')
policy=load('release-policy.json')
need(policy.get('primaryEdition')=='dev' and policy.get('publicBuild')=='frozen','release policy must keep Dev primary and Public frozen')
need(f'Multi-Script-{VERSION}-Dev.zip' in readme and f'Multi-Script-{VERSION}-Bundle.zip' in readme and policy.get('publicCompanion',{}).get('file','MISSING') in readme,'README Dev/bundle/frozen-Public filenames are stale')
need(f'Multi-Script Bridge v{VERSION}' in readme,'README bridge-version example is stale')
arena=(ROOT/'extension/providers/arena.js').read_text(encoding='utf-8')
for x in ['waitForHumanVerification','humanVerificationRequired','does not bypass verification challenges']: need(x in arena,f'missing Arena verification guard: {x}')
# The assisted first-click is the only interaction with a challenge, and the
# release must never ship a bypass. Scan the PROVIDER + CORE for the concrete
# implementations of one (solving services, token fields, execute APIs).
verify=(ROOT/'extension/core/verification.js')
need(verify.is_file(),'missing verification assistant module')
import re as _re
def _strip_comments(s):
    s=_re.sub(r'/\*[\s\S]*?\*/',' ',s)
    s=_re.sub(r'^\s*//.*$',' ',s,flags=_re.M)
    return s
_ship=_strip_comments(arena+_strip_comments((ROOT/'extension/core/verification.js').read_text(encoding='utf-8'))+_strip_comments((ROOT/'extension/core/main.js').read_text(encoding='utf-8'))).lower()
for bad in ['2captcha','anticaptcha','capsolver','capmonster','rucaptcha','deathbycaptcha',
            'grecaptcha.execute','grecaptcha.getresponse','hcaptcha.execute','turnstile.render(',
            'g-recaptcha-response','h-captcha-response','cf-turnstile-response','contentwindow.postmessage']:
    need(bad not in _ship,f'captcha bypass implementation in shipped code: {bad}')
need('assistChallengeClick' in arena,'missing assisted challenge click')
need((ROOT/'tests/test_verification_assistant.js').is_file(),'missing verification assistant test')
need((ROOT/'tests/test_arena_human_verification.js').is_file(),'missing Arena human-verification gate test')
# 6.17.4: the content-script load contract. 6.17.3 shipped a TDZ ReferenceError
# that killed every content script before any UI mounted; node --check cannot see
# it, only evaluating the concatenated chain in one shared scope can. The test is
# required to exist AND to carry its non-vacuous guard.
_lct=(ROOT/'tests/test_content_script_load_contract.js')
need(_lct.is_file(),'missing content-script load contract test (6.17.4 regression gate)')
_lct_src=_lct.read_text(encoding='utf-8')
need('content_scripts' in _lct_src,'load contract test does not walk manifest.content_scripts')
need('TDZ' in _lct_src and 'not vacuous' in _lct_src,'load contract test lost its non-vacuous TDZ guard')
# The bug itself: no top-level assignment to A before `const A = {`.
_main_src=(ROOT/'extension/core/main.js').read_text(encoding='utf-8')
_A_decl=_main_src.find('const A = {')
need(_A_decl>0,'core/main.js lost its `const A = {` declaration')
for _ln,_line in enumerate(_main_src[:_A_decl].splitlines(),1):
    _code=_line.split('//')[0]
    if re.match(r'^\s*A\.[A-Za-z_$][\w$]*\s*=',_code) and _code.startswith('  A.'):
        need(False,f'core/main.js assigns A before `const A` (temporal dead zone) at line {_ln}')
# Engine-registry integrity. The registry in core/engines.js carries the
# action-dispatch vocabulary, the copy-paste REQUIRED SHAPE templates and the
# Roblox place-scope set. A drift between a template and its tool (wrong
# `command`, an action that is not in the tool's vocabulary, a template that
# does not parse) hands the model a shape the server rejects, which is exactly
# the 6.17.1/6.17.2 BAD-JSON failure class. The test is required to exist AND to
# keep asserting JSON round-trip + template/command agreement.
_eri=(ROOT/'tests/test_engine_registry_integrity.js')
need(_eri.is_file(),'missing engine registry integrity test')
_eri_src=_eri.read_text(encoding='utf-8')
need('ENGINE_TEMPLATES' in _eri_src or 'templateFor' in _eri_src,'engine registry test lost its template walk')
need('JSON.parse' in _eri_src and 'actionsOf' in _eri_src,'engine registry test lost template-parse/action checks')
# Refusal feedback honesty. 6.17.5 fixed `subagent` being refused with a
# false "timed out" cause (a permanent block is not a transient failure). The
# helper must exist and be shared, and main.js must not reintroduce a fabricated
# timeout for a permanently disabled command.
_rf=(ROOT/'tests/test_refusal_feedback.js')
need(_rf.is_file(),'missing refusal feedback test')
_cfg_src=(ROOT/'extension/core/config.js').read_text(encoding='utf-8')
need('blockedFeedback' in _cfg_src,'core/config.js lost blockedFeedback')
need('PERMANENTLY_BLOCKED' in _cfg_src,'core/config.js lost the shared PERMANENTLY_BLOCKED set')
need('ZS.blockedFeedback' in _main_src,'core/main.js no longer delegates refusal text to the shared helper')
# Roblox required-shape conformance. The Roblox templates were written by
# guessing parameter names and several were wrong (generate_mesh takes
# textPrompt not prompt; wait_job_finished takes jobId not generation_id;
# screen_capture REQUIRES capture_id; search_game_tree REQUIRES datamodel_type).
# The test pins the real schema facts so an edit cannot reintroduce a guess.
_rsc=(ROOT/'tests/test_roblox_schema_conformance.js')
need(_rsc.is_file(),'missing Roblox schema conformance test')
_rsc_src=_rsc.read_text(encoding='utf-8')
for _x in ['textPrompt','jobId','capture_id','datamodel_type','assetId']:
    need(_x in _rsc_src,f'Roblox schema test lost its {_x} assertion')
_eng=(ROOT/'extension/core/engines.js').read_text(encoding='utf-8')
need('"textPrompt"' in _eng or "'textPrompt'" in _eng,'engines.js lost the real generate_mesh textPrompt field')
need('"jobId"' in _eng,'engines.js lost the real wait_job_finished jobId field')
need('"capture_id"' in _eng,'engines.js lost the required screen_capture capture_id')
need('character_navigation' in _eng,'engines.js lost character_navigation')
notion=(ROOT/'extension/providers/notion.js').read_text(encoding='utf-8')
for x in ['opus55','Claude Opus 5.5','luna','GPT-6 Luna','awaiting-notion','Saved preference metadata:', 'cannot select, pin or change the model', 'Never claim a model was selected without provider confirmation.','directPickerInteraction: false']: need(x in notion,f'missing Notion model starter guard: {x}')
for section in manifest.get('content_scripts',[]):
    for rel in section.get('js',[])+section.get('css',[]): need((ROOT/'extension'/rel).is_file(),f'manifest references missing extension/{rel}')
for rel in list(manifest.get('icons',{}).values())+list(manifest.get('action',{}).get('default_icon',{}).values()): need((ROOT/'extension'/rel).is_file(),f'missing icon {rel}')
skills=load('runtime/skills.json'); need(len(skills)==249,f"expected 249 skills, found {len(skills)}")
need(len(set(skills))==len(skills),'duplicate skill ids')
direct_names=re.findall(r"\{[\"']name[\"']:\s*[\"'](ms_[^\"']+)[\"']",bridge)
roblox_contract_line=next((line for line in bridge.splitlines() if line.startswith('ROBLOX_STUDIO_V3_CONTRACTS = ')),'')
direct_names += re.findall(r"'(ms_roblox_[^']+)': \{",roblox_contract_line)
engine_contract_line=next((line for line in bridge.splitlines() if line.startswith('ENGINE_PRO_V3_CONTRACTS = ')),'')
direct_names += re.findall(r"'(ms_(?:unity|godot|blender)_[^']+)': \{",engine_contract_line)
need(len(direct_names)==232 and len(set(direct_names))==232,f'expected 232 inline direct tool definitions, found {len(direct_names)}')
for x in ['ms_roblox_capability_audit','ms_camera_system_design','ms_shader_production','ms_security_abuse_review','ms_regression_plan']: need(x in direct_names,f'missing expanded direct tool {x}')
packs=load('runtime/skill-packs.json'); need(packs.get('totalSkills')==len(skills),'skill-packs totalSkills mismatch')
capabilities=load('runtime/capability-index.json'); need(capabilities.get('totalSkills')==len(skills),'capability-index totalSkills mismatch')
virtual=load('runtime/virtual-tools.json'); vtools=virtual.get('tools',{}) if isinstance(virtual,dict) else {}; need(virtual.get('total')==263 and len(vtools)==263,'expected 263 virtual tools'); need(virtual.get('engineCounts')=={'roblox':90,'unity':70,'godot':70,'blender':33},'virtual tool engine counts mismatch')
for tid,v in vtools.items():
    need(v.get('id')==tid and v.get('engine') in {'roblox','unity','godot','blender'},f'invalid virtual tool {tid}')
    need(len(v.get('stages') or [])>=8 and len(v.get('qualityGates') or [])>=8,f'incomplete virtual tool {tid}')
need(all(len(v.get('relatedSkills') or [])>=4 for v in skills.values()),'every skill must have four related collaborators')
for pack_name,pack in packs.items():
    if not isinstance(pack,dict): continue
    ids=pack.get('skillIds',pack.get('skills'))
    if ids is None: continue
    need(len(ids)==len(set(ids)),f'duplicate ids in pack {pack_name}')
    if 'count' in pack: need(pack['count']==len(ids),f'count mismatch in pack {pack_name}')
    for sid in ids: need(sid in skills,f'unknown skill {sid} in pack {pack_name}')
for sid,v in skills.items():
    need(bool(v.get('name')) and bool(v.get('description')),f'incomplete skill {sid}')
    need(len(v.get('steps') or [])>=1,f'skill lacks steps {sid}')
for p in ROOT.rglob('*'):
    if p.is_file():
        rel=p.relative_to(ROOT).as_posix()
        if '__pycache__' in p.parts or rel.endswith('.pyc'): continue
        if p.stat().st_size>15_000_000: errors.append(f'oversized file: {rel}')
for p in list((ROOT/'runtime').glob('*.py'))+list((ROOT/'tests').glob('*.py'))+list((ROOT/'tools').glob('*.py')):
    try: compile(p.read_text(encoding='utf-8'),str(p),'exec')
    except Exception as e: errors.append(f'python syntax {p.relative_to(ROOT)}: {e}')
js=list((ROOT/'extension').glob('*.js'))+list((ROOT/'extension/core').glob('*.js'))+list((ROOT/'extension/providers').glob('*.js'))+list((ROOT/'tests').glob('*.js'))+list((ROOT/'runtime/phone').glob('*.js'))+list((ROOT/'runtime/blender-studio').glob('*.js'))+list((ROOT/'figma-plugin').glob('*.js'))
for p in js:
    r=subprocess.run(['node','--check',str(p)],capture_output=True,text=True)
    if r.returncode: errors.append(f'javascript syntax {p.relative_to(ROOT)}: {r.stderr.strip()}')
# Block common accidental secret forms without printing values.
secret_re=re.compile(r'(?i)(api[_-]?key|access[_-]?token|client[_-]?secret|private[_-]?key)\s*[=:]\s*["\'][A-Za-z0-9_\-]{16,}')
for p in ROOT.rglob('*'):
    if p.is_file() and p.suffix.lower() in {'.py','.js','.json','.md','.yml','.yaml','.html','.css','.bat','.command','.sh'}:
        try:text=p.read_text(encoding='utf-8')
        except Exception:continue
        if secret_re.search(text): errors.append(f'possible hardcoded secret in {p.relative_to(ROOT)}')
# 6.25.0: the terminal icon starts the bridge (Native Messaging), start.bat is gone,
# every engine ships a native toolkit, and Notion gets model/trial tooling.
for _rel in ['runtime/schema_repair.py','runtime/native_host.py','runtime/install_native_host.py','runtime/engine_toolkit.py','runtime/toolkit_blender.py','runtime/toolkit_roblox.py','runtime/toolkit_unity.py','runtime/toolkit_godot.py','runtime/launch_blender_mcp.py','Setup.bat','MacOS_Setup.command','Start.bat','MacOS_Start.command','Setup.sh','Start.sh','runtime/unix_env.sh','runtime/winquiet.py','extension/core/notion-usage.js','tests/test_engine_toolkit.py','tests/test_schema_repair_and_native_host.py','tests/test_notion_usage.js','tests/test_parser_repair.js','tests/test_studio_ui.js','tests/test_chatbar_studio.js','tests/fixtures/roblox_mock.lua','tools/studio_harness.js']:
    need((ROOT/_rel).is_file(),f'missing 6.25.0 file {_rel}')
need((ROOT/'Start.bat').is_file(),'Start.bat is the no-setup fallback launcher and must ship')
need('DETACHED' not in (ROOT/'runtime/native_host.py').read_text(encoding='utf-8').split('def _spawn_bridge',1)[1].split('def _kill_tree',1)[0].replace('Do NOT add DETACHED_PROCESS','').replace('overrides NO_WINDOW',''),'native_host must not spawn the bridge DETACHED (flashing consoles)')
need(bool(manifest.get('key')),'manifest needs the pinned key (stable extension id for Setup)')
need('nativeMessaging' in manifest.get('permissions',[]),'manifest lost the nativeMessaging permission')
need(any('core/notion-usage.js' in sec.get('js',[]) for sec in manifest.get('content_scripts',[])),'notion-usage.js is not loaded on Notion')
_pm=load('runtime/product-manifest.json')
need(_pm.get('engineToolkit',{}).get('total',0)>=100,'product manifest lost the engine toolkit counts')
if errors:
    print('RELEASE CHECK FAILED')
    for e in errors: print(' -',e)
    sys.exit(1)
print(f'PASS Multi-Script {VERSION} release check: {len(skills)} skills, {len(js)} JavaScript files, manifest references and public docs verified')
