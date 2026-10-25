const fs=require('fs');
const main=fs.readFileSync('extension/core/main.js','utf8');
const notion=fs.readFileSync('extension/providers/notion.js','utf8');
for(const x of ['const bootstrapClaims = new Set()','bootstrapClaims.has(claimKey)','bootstrapClaims.add(claimKey)','finally {','bootstrapClaims.delete(claimKey)','Claims prevent two simultaneous bootstraps','top of each new chat','Saved for the next new chat']) if(!main.includes(x)) throw new Error('missing '+x);
const finallyBlock=main.slice(main.indexOf('} finally {',main.indexOf('async function startSession')),main.indexOf('// ════════════════════════════════════════════════════════════════════════',main.indexOf('} finally {',main.indexOf('async function startSession'))));
if(!finallyBlock.includes('bootstrapClaims.delete(claimKey)')) throw new Error('bootstrap claim must always be released in finally so a later blank chat can start');
for(const x of ['notionPageToken','notionChatEpoch','notionHadTurns','notionChatEpoch += 1']) if(!notion.includes(x)) throw new Error('missing '+x);
if(/resendSystemEvery\s*:/.test(notion)) throw new Error('Notion must not periodically resend full system prompt');
console.log('PASS one Notion bootstrap per chat and next-chat profile lifecycle');
