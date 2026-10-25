const assert=require('assert'),cp=require('child_process');
const provider=process.env.MS_BENCH_PROVIDER||'chatgpt';
const results=[];for(const variant of ['legacy','current','compact']){
 const run=cp.spawnSync(process.execPath,[require.resolve('./test_agentic_runtime_roundtrip')],{encoding:'utf8',env:{...process.env,MS_TEST_PROVIDER:provider,MS_TEST_STARTUP_VARIANT:variant,MS_TEST_STARTUP_BENCH:'1'},timeout:180000});
 const line=(run.stdout||'').split('\n').find(x=>x.startsWith('STARTUP_BENCH '));if(line)results.push(JSON.parse(line.slice(14)));
 process.stdout.write(run.stdout||'');process.stderr.write(run.stderr||'');assert.strictEqual(run.status,0,provider+' '+variant+' startup must complete actual tool/skill/asset roundtrip');
}

assert.strictEqual(results.length,3);assert(results.every(x=>x.taskMethods&&x.manuals&&x.startupSends===3&&x.assetsCreated>=1));assert.strictEqual(new Set(results.map(x=>x.taskChars)).size,1,'Startup strategy must not change the actual task method payload');assert(results.find(x=>x.variant==='compact').startupChars<=results.find(x=>x.variant==='current').startupChars,'Compact initialization must not add standards overhead');
