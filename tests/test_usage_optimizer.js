const fs=require('fs'),vm=require('vm');
const context={console}; vm.createContext(context);
vm.runInContext(fs.readFileSync('extension/core/config.js','utf8')+'\n;globalThis.__ZS=ZS;',context);
const Z=context.__ZS;
for(const p of ['notion','chatgpt','gemini','kimi','deepseek','glm','qwen','arena','meta']) {
  const x=Z.economyPrompt(p,'balanced'); if(!x.includes('USAGE OPTIMIZER')||x.length<180) throw new Error(p);
}
const value={rows:Array.from({length:12},(_,i)=>({id:i,name:'asset-'+i,ok:true}))};
const pretty=`Output of 'demo':\n${JSON.stringify(value,null,2)}`;
const compact=Z.optimizeInjectedText(pretty,'compact');
if(compact.length>=pretty.length) throw new Error('did not shrink JSON');
const parsed=JSON.parse(compact.slice(compact.indexOf('\n')+1));
if(JSON.stringify(parsed)!==JSON.stringify(value)) throw new Error('changed JSON');
const repeated="Output of 'x':\nhello\nhello\nworld";
if(Z.optimizeInjectedText(repeated,'balanced').includes('hello\nhello')) throw new Error('duplicate line');
if(Z.optimizeInjectedText(repeated,'off')!==repeated) throw new Error('off changed text');
if(Z.compactSystemReminder('notion','compact').length>1800) throw new Error('reminder too large');
console.log('PASS provider-wide usage optimizer');
