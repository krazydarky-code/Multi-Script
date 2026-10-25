// SPDX-License-Identifier: GPL-3.0-or-later
// 6.36.1: provider-aware art direction, asset workflow, finish level and real delivery contract.
const fs = require('fs'), path = require('path'), vm = require('vm');
const root = path.resolve(__dirname, '..');
const ctx = { console }; vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(root, 'extension/core/config.js'), 'utf8') + '\n;globalThis.__MS=ZS;', ctx);
const C = ctx.__MS;
const ok = (condition, message) => { if (!condition) throw new Error(message); };
const styles = {
  auto: 'ART DIRECTION — AUTO', anime: 'ART DIRECTION — ANIME',
  'stylized-fantasy': 'ART DIRECTION — STYLIZED FANTASY', 'low-poly': 'ART DIRECTION — LOW-POLY',
  'realistic-pbr': 'ART DIRECTION — REALISTIC PBR', cyberpunk: 'ART DIRECTION — CYBERPUNK',
  'dark-gothic': 'ART DIRECTION — DARK GOTHIC', 'cozy-handpainted': 'ART DIRECTION — COZY HAND-PAINTED',
  'retro-pixel': 'ART DIRECTION — RETRO PIXEL', 'minimal-modern': 'ART DIRECTION — MINIMAL MODERN',
  'sci-fi-hard-surface': 'ART DIRECTION — SCI-FI HARD-SURFACE', 'toy-cartoon': 'ART DIRECTION — TOY/CARTOON',
  'luxury-gold': 'ART DIRECTION — LUXURY'
};
for (const [creativeStyle, phrase] of Object.entries(styles)) {
  const prompt = C.providerBehaviorPrompt({ creativeStyle, assetWorkflow: 'hybrid', creativeFinish: 'cinematic', loops: 'balanced', creativeSurface: 'auto' }, 'ChatGPT');
  ok(prompt.includes(phrase), `style missing: ${creativeStyle}`);
  ok(prompt.includes('ASSET WORKFLOW — HYBRID'), 'hybrid asset workflow missing');
  ok(prompt.includes('FINISH — CINEMATIC'), 'cinematic finish missing');
  ok(prompt.includes('ms_create_icon_pack') && prompt.includes('ms_create_canvas_ui') && prompt.includes('ms_create_canvas_texture'), 'real asset tools not named');
  ok(prompt.includes('read back final state') || prompt.includes('read back actual final state') || prompt.includes('read back final state'), 'evidence-based completion missing');
}
const notion = C.providerBehaviorPrompt({creativeStyle:'anime',assetWorkflow:'external-first',creativeFinish:'premium'}, 'Notion AI');
ok(notion.includes('PROVIDER ADAPTER NOTE — Notion AI') && notion.includes('not proof that Notion exposes a native system role'), 'Notion-specific adapter honesty missing');
const claude = C.providerBehaviorPrompt({}, 'Claude');
ok(claude.includes('PROVIDER ADAPTER NOTE — Claude') && claude.includes('dependent mutations sequential'), 'Claude adapter guidance missing');
const meta = C.providerBehaviorPrompt({}, 'Meta AI');
ok(meta.includes('PROVIDER ADAPTER NOTE — Meta AI'), 'Meta AI adapter guidance missing');
const superapp = C.providerBehaviorPrompt({}, 'SuperApp');
ok(superapp.includes('PROVIDER ADAPTER NOTE — SuperApp'), 'SuperApp adapter guidance missing');
const main = fs.readFileSync(path.join(root, 'extension/core/main.js'), 'utf8');
for (const token of ['creativeStyle: "auto"','assetWorkflow: "auto"','creativeFinish: "premium"','[\"anime\",\"Anime\"]','data-creative-style=\"${id}\"','data-asset-workflow=\"external-first\"','data-creative-finish=\"${id}\"','setProviderBehavior({ creativeStyle:','setProviderBehavior({ assetWorkflow:','setProviderBehavior({ creativeFinish:','msProviderBehavior']) ok(main.includes(token), `settings wiring missing: ${token}`);
const standard = JSON.parse(fs.readFileSync(path.join(root, 'runtime/studio-standard.json'), 'utf8'));
ok(standard.version === '12.1' && standard.creativeProductionV6361.disciplines.uiUxGui.length >= 6, 'studio standard creative contract missing');
const shared = JSON.parse(fs.readFileSync(path.join(root,'runtime/skill-shared-policy.json'),'utf8'));
const skills = Object.fromEntries(Object.entries(JSON.parse(fs.readFileSync(path.join(root, 'runtime/skills.json'), 'utf8'))).map(([id,skill])=>[id,{...shared,...skill}]));
ok(Object.keys(skills).length === 249, 'skill count/IDs changed unexpectedly');
ok(Object.values(skills).every(s => s.productionContractV6361 && s.productionContractV6361.workflow.length >= 7), 'all skills must receive execution contract');
ok(Object.values(skills).some(s => s.visualProductionContractV6361), 'visual production contract missing');
console.log('PASS 6.36.1 provider-aware creative prompt, per-provider settings, production contracts and visual skill layer');
