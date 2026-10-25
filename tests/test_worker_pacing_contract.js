// Evaluate the actual worker and its imported modules, then use its real message handler.
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
(async()=>{const root=path.resolve(__dirname,'../extension'),store={},handlers=[];let storageFails=false;
const event={addListener(){}};
class Socket{static CONNECTING=0;static OPEN=1;static CLOSED=3;constructor(){this.readyState=0;}addEventListener(){}close(){this.readyState=3;}send(){}}
const chrome={runtime:{id:'fixture',getManifest:()=>({version:'6.41.0'}),onMessage:{addListener:f=>handlers.push(f)},onStartup:event,onInstalled:event,sendMessage(){},lastError:null},storage:{local:{get:(keys,cb)=>{if(storageFails)return Promise.reject(Error('fixture storage unavailable'));cb?.(store);return Promise.resolve(store);},set:(x,cb)=>{Object.assign(store,x);cb?.();return Promise.resolve();}}},tabs:{query:(_q,cb)=>{cb?.([]);return Promise.resolve([]);},sendMessage:()=>Promise.resolve()},scripting:{executeScript:()=>Promise.resolve([])}};
const ctx=vm.createContext({chrome,WebSocket:Socket,console,AbortController,fetch:async()=>({ok:true,json:async()=>({ok:true})}),navigator:{userAgent:'fixture'},URL,URLSearchParams,TextEncoder,TextDecoder,Uint8Array,crypto:require('crypto').webcrypto,Date,Promise,Map,Set,Error,JSON,setTimeout:()=>1,clearTimeout(){},setInterval:()=>1,clearInterval(){}});ctx.self=ctx;
ctx.importScripts=(...files)=>files.forEach(file=>vm.runInContext(fs.readFileSync(path.join(root,file),'utf8'),ctx,{filename:file}));
vm.runInContext(fs.readFileSync(path.join(root,'background.js'),'utf8'),ctx,{filename:'background.js'});assert.strictEqual(handlers.length,1);
const request=msg=>new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Worker did not respond')),1000);handlers[0](msg,{},r=>{clearTimeout(timer);resolve(JSON.parse(JSON.stringify(r)));});});
const sessions=await request({type:'ms_cowork_tabs',action:'list'});assert(sessions.ok&&sessions.participants.length===0,'The real worker routes provider session discovery');
const denied=await request({type:'ms_cowork_tabs',action:'assign',tabId:-1,requestId:'invalid-target-123'});assert(denied.ok===false&&denied.error.includes('provider tab'),'Invalid target returns a response without dispatch');
const first=await request({type:'ms_provider_pacing',action:'acquire',provider:'venice',owner:'tab-a'});assert(first.granted);
assert(!(await request({type:'ms_provider_pacing',action:'acquire',provider:'venice',owner:'tab-b'})).granted);
assert(store.msProviderSendState.venice.owner==='tab-a');
await request({type:'ms_provider_pacing',action:'release',provider:'venice',owner:'tab-a',success:true});
storageFails=true;const failed=await request({type:'ms_provider_pacing',action:'acquire',provider:'venice',owner:'tab-c'});assert(failed.ok===false&&failed.error.includes('state unavailable'),'Storage failure returns an error rather than stranding the sender');
console.log('PASS complete worker/import initialization, actual pacing message dispatch, shared lease persistence and response on storage failure.');
})().catch(e=>{console.error(e.stack);process.exit(1)});
