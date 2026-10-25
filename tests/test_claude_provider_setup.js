const fs=require('fs');
const manifest=JSON.parse(fs.readFileSync('extension/manifest.json','utf8'));
const code=fs.readFileSync('extension/providers/claude.js','utf8');
const main=fs.readFileSync('extension/core/main.js','utf8');
const notices=fs.readFileSync('legal/upstream-gpl/ORIGINAL_NOTICES.md','utf8');
const origin=JSON.parse(fs.readFileSync('legal/upstream-gpl/SOURCE.json','utf8')).originName;
function ok(v,m){if(!v)throw new Error(m)}
const block=manifest.content_scripts.find(x=>(x.js||[]).includes('providers/claude.js'));
ok(block,'Claude provider block missing');
for(const p of ['https://claude.ai/*','https://www.claude.ai/*','https://claude.com/*','https://www.claude.com/*'])ok(block.matches.includes(p)&&manifest.host_permissions.includes(p),'missing '+p);
for(const f of ['core/enhancer.js','core/pacing.js','core/resilience.js','core/verification.js','core/trust.js','core/main.js'])ok(block.js.includes(f),'Claude missing shared '+f);
ok(code.includes('const ZSProvider')&&code.includes('id: "claude"'),'Claude adapter not renamed for Multi-Script');
ok(!code.toLowerCase().includes(origin.toLowerCase()),'Upstream product branding leaked into shipped provider');
ok(main.includes('{ name: "Claude", url: "https://claude.ai/new" }'),'Claude missing AI-site switcher');
ok(notices.includes(origin+' 1.18.74')&&notices.includes('no '+origin+' IDE'),'GPL provenance/IDE exclusion missing');
console.log('PASS adapted Claude provider integrated under Multi-Script with shared settings and preserved legal attribution');
