const fs=require('fs'),path=require('path');const r=path.resolve(__dirname,'..');const main=fs.readFileSync(path.join(r,'extension/core/main.js'),'utf8'),css=fs.readFileSync(path.join(r,'extension/overlay.css'),'utf8'),bg=fs.readFileSync(path.join(r,'extension/background.js'),'utf8');
for(const x of ['brandName','brandIcon','tagline','theme','scale','radius','font','backdrop','motion','studio'])if(!main.includes(x))throw Error('missing customization '+x);
for(const x of ['Appearance studio','ms-custom-accent','ms-save-identity','data-theme','data-density','data-width'])if(!main.includes(x))throw Error('missing UI '+x);
for(const x of ['Audio generation','type="password"','elevenlabs_configure','elevenlabs_clear','never saved in browser storage'])if(!main.includes(x))throw Error('missing key UI '+x);
if(/chrome\.storage\.local\.set\([^\n]*ELEVEN/i.test(main))throw Error('secret stored in browser');
if(!bg.includes('case "elevenlabs_configure"')||!bg.includes('elevenlabs_settings'))throw Error('missing secure transport');
for(const x of ['data-ms-theme','data-ms-backdrop','data-ms-motion','zs-secret-field','zs-theme-grid'])if(!css.includes(x))throw Error('missing style '+x);
const settingsBody=main.slice(main.indexOf('const appearanceHtml'),main.indexOf('const activeNotionProfile'));
if(/DeepSeek/.test(settingsBody))throw Error('universal settings copy is branded or limited to DeepSeek');
for(const x of ['Prompt enhancer','Execution effort','Creative output','Production checks','Studio skill coverage','Usage optimizer','Reply pacing','Error recovery','Autonomy'])if(!settingsBody.includes(x))throw Error('universal settings section missing '+x);
if(!main.includes('providerBehaviorMap[P.id]')||main.includes('providerBehaviorMap.deepseek'))throw Error('provider settings are not keyed by the active provider');
console.log('PASS customizable settings UI and browser-secret exclusion');

if(!main.includes("Notion turns models on per workspace and plan."))throw new Error("missing actual Notion workspace/plan model boundary");
