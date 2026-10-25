const fs=require('fs'),vm=require('vm'); const c={console}; vm.createContext(c);
vm.runInContext(fs.readFileSync('extension/core/config.js','utf8')+'\n;globalThis.__MS=ZS;',c);
const cases=[
 [{promptSkills:'off',loops:'fast'},['PROMPT REWRITING OFF','ALWAYS-ON CAPABILITY RULE','FAST PRODUCTION OVERRIDE','Disable automatic workflow-plan']],
 [{promptSkills:'suggest',loops:'balanced'},['SUGGEST-ONLY','ALWAYS-ON CAPABILITY RULE','BALANCED VALIDATION','one focused verification']],
 [{promptSkills:'automatic',loops:'rigorous'},['PROMPT REWRITING AUTOMATIC','ALWAYS-ON CAPABILITY RULE','RIGOROUS VALIDATION','at most 3 rounds']],
];
for(const [settings,phrases] of cases){const p=c.__MS.providerBehaviorPrompt(settings,'Notion AI');for(const x of phrases)if(!p.includes(x))throw new Error(`${JSON.stringify(settings)} missing ${x}`);if(!p.includes('Notion AI'))throw new Error('provider label');}
if(!c.__MS.providerBehaviorPrompt({},'ChatGPT').includes('BALANCED VALIDATION'))throw new Error('defaults');
const main=fs.readFileSync('extension/core/main.js','utf8');
for(const x of ['msProviderBehavior','providerBehaviorMap[P.id]','data-prompt-skills','data-loop-mode','Fast — loops disabled','Suggest rewrite','Rigorous','getProviderBehavior'])if(!main.includes(x))throw new Error(`wiring missing ${x}`);
console.log('PASS per-provider prompt rewriting, always-on skills and production loop modes');
