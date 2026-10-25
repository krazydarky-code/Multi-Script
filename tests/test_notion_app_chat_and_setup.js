const fs=require('fs');
const manifest=JSON.parse(fs.readFileSync('extension/manifest.json','utf8'));
const main=fs.readFileSync('extension/core/main.js','utf8');
const notion=fs.readFileSync('extension/providers/notion.js','utf8');
const bg=fs.readFileSync('extension/background.js','utf8');
const popup=fs.readFileSync('extension/popup.js','utf8');
function ok(v,m){if(!v)throw new Error(m)}
const pat='https://app.notion.com/*';
const block=manifest.content_scripts.find(x=>(x.js||[]).includes('providers/notion.js'));
ok(block&&block.matches.includes(pat),'app.notion.com missing from Notion content script');
ok(manifest.host_permissions.includes(pat),'app.notion.com missing host permission');
ok(bg.includes(pat),'background status is not broadcast to app.notion.com');
ok(popup.includes('app.notion.com'),'popup cannot find/repair app.notion.com');
ok(main.includes('url: "https://app.notion.com/chat"'),'Notion switcher still opens the old workspace/connectors route');
ok(!main.includes('{ name: "Notion AI", url: "https://www.notion.so/"'),'old Notion workspace root remains');
ok(notion.includes("[placeholder*='ask anything' i]")&&notion.includes('location.assign("https://app.notion.com/chat")'),'current composer/recovery route missing');
for(const x of ['["home", "Home"','Set up Multi-Script','Run setup check','Copy checklist','Open Engines setup','https://app.notion.com/chat — not workspace Connectors'])ok(main.includes(x),'setup tutorial missing '+x);
// The settings were regrouped from 5 flat tabs into 7 named ones (Appearance and
// Interface split out of the old catch-all Agent tab). Every tab the strip
// declares must also be a valid saved default, or picking it would be silently
// discarded on reload.
const stripTabs=[...main.matchAll(/\["([a-z]+)", "[^"]+", '<(?:path|rect|circle)/g)].map(m=>m[1]);
const savedTabs=(main.match(/defaultTab:\[([^\]]+)\]/)||[])[1];
ok(savedTabs,'defaultTab enum missing');
const saved=new Set([...savedTabs.matchAll(/"([^"]+)"/g)].map(m=>m[1]));
ok(stripTabs.length>0,'no tabs declared in the settings strip');
// "backstage" is the Fazbear's-theme secret tab: shown only while that theme is on, so never a saved default.
ok(!saved.has('backstage'),'secret Backstage tab must not be a saved default');
for(const t of stripTabs.filter(x=>x!=='backstage'))ok(saved.has(t),'tab "'+t+'" is not a real saved category');
ok(stripTabs.includes('home')&&saved.has('setup'),'Home tab missing (or the legacy setup alias was dropped)');
console.log('PASS app.notion.com injection, real-chat routing, current composer detection, and complete in-settings setup tutorial');
