const fs=require('fs');
const manifest=JSON.parse(fs.readFileSync('extension/manifest.json','utf8'));
const main=fs.readFileSync('extension/core/main.js','utf8');
const enhancer=fs.readFileSync('extension/core/enhancer.js','utf8');
function ok(v,m){if(!v)throw new Error(m)}
const appBlocks=(manifest.content_scripts||[]).filter(block=>block.js.includes('core/main.js'));
for(const block of appBlocks){
  ok(block.js.includes('core/enhancer.js'),`enhancer missing from ${block.matches&&block.matches[0]}`);
  ok(block.js.indexOf('core/enhancer.js')<block.js.indexOf('core/main.js'),'enhancer must load before main');
}
ok(/es\.preview\s*&&\s*ui\.reviewEnhancedPrompt/.test(main),'saved preview setting is not used by kickoff');
ok(/function reviewEnhancedPrompt/.test(main)&&/data-action="original"/.test(main)&&/data-action="send"/.test(main),'editable review actions missing');
ok(/settings\.injectToolFacts\s*&&\s*f\.toolCount/.test(enhancer),'tool fact toggle does not govern tool count');
ok(/ms-enhance-tool-facts/.test(main)&&/injectToolFacts:\s*tf\.checked/.test(main),'tool-fact menu control is not wired');
ok(/const EXECUTION_EFFORTS/.test(main)&&/adaptive:/.test(main)&&/maximum:/.test(main),'effort levels missing');
ok(/msExecutionEffort/.test(main)&&/executionEffortPrompt\(\)/.test(main),'effort is not persisted and injected');
ok(/promptEnhancer:ZSEnhance\.sanitize\(enhanceSettings\)/.test(main)&&/executionEffort/.test(main),'portable settings omit enhancer or effort');
ok(main.includes('Execution effort &amp; reasoning')&&main.includes('class="zs-provider-badge">all providers'),'effort must be described consistently for every provider');
ok(!/P\.id\s*===\s*["']deepseek["'][\s\S]{0,200}ZSEnhance\.enhance/.test(main),'enhancer is gated to DeepSeek');
console.log(`PASS universal enhancer + effort harness across ${appBlocks.length} provider app blocks`);
