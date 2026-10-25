const fs=require('fs'),vm=require('vm');const c={console};vm.createContext(c);
vm.runInContext(fs.readFileSync('extension/core/config.js','utf8')+'\n;globalThis.__MS=ZS;',c);
const modes={
 auto:['CREATIVE SURFACE — AUTO','Direct Roblox Studio','skip Canvas'],
 engine:['CREATIVE SURFACE — DIRECT ENGINE','Skip Canvas and Figma drafts','connected target engine'],
 figma:['CREATIVE SURFACE — FIGMA','connected Figma MCP','fall back to an importable SVG'],
 canvas:['CREATIVE SURFACE — CANVAS/SVG','actual SVG/Canvas artifact','import or implement'],
};
for(const [creativeSurface,phrases] of Object.entries(modes)){const p=c.__MS.providerBehaviorPrompt({promptSkills:'automatic',loops:'balanced',creativeSurface},'Notion AI');for(const x of phrases)if(!p.includes(x))throw new Error(`${creativeSurface} missing ${x}`)}
const base=fs.readFileSync('extension/core/config.js','utf8');for(const x of ['ADAPTIVE CREATIVE SURFACE','Prefer DIRECT ROBLOX STUDIO','Prefer FIGMA','Prefer CANVAS/SVG'])if(!base.includes(x))throw new Error('base routing '+x);
const main=fs.readFileSync('extension/core/main.js','utf8');for(const x of ['creativeSurface: "auto"','data-creative-surface="auto"','data-creative-surface="engine"','data-creative-surface="figma"','data-creative-surface="canvas"','Direct in Roblox/engine','setProviderBehavior({ creativeSurface'])if(!main.includes(x))throw new Error('UI wiring '+x);
console.log('PASS adaptive Auto/direct-engine/Figma/Canvas routing');
