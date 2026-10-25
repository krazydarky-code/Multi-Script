// The prompt enhancer must HOLD the user's send, ask, and send exactly ONE message.
const fs = require('fs'), path = require('path');
const root = path.join(__dirname, '..');
const MAIN = fs.readFileSync(path.join(root, 'extension/core/main.js'), 'utf8');
const ZSEnhance = new Function(fs.readFileSync(path.join(root, 'extension/core/enhancer.js'), 'utf8') + ';return ZSEnhance;')();
let failed = 0;
const ok = (c, m) => { if (!c) throw new Error(m || 'assertion failed'); };
const results = [];
const t = (name, fn) => results.push([name, fn]);

// Static wiring
const a = MAIN.indexOf('let sendEvt = null;');
const b = MAIN.indexOf('// User-send interception: the provider wires');
ok(a > 0 && b > a, 'gate code not found');
const gateSrc = MAIN.slice(a, b);
ok(!/enhanceKickoff/.test(MAIN), 'old send-original-then-brief kickoff still present');
ok(/if \(gateEnhancedSend\(held,event\)\) return;/.test(MAIN), 'onUserMessage does not gate the send with its original event');
ok(/submitAndGetBase\(text, undefined, \{ visible: true, settingsKey \}\)/.test(MAIN), 'chosen prompt is not sent visibly');

function harness(settings, choiceFn) {
  const calls = { submit: [], loop: 0, toasts: [], listeners: {} };
  const A = { toolList: [], studios: [], running: false, starting: false, lastSendOk: true, userStopped: false };
  const window = { addEventListener: (n, f) => { calls.listeners[n] = f; } };
  const ui = { toast: (m) => calls.toasts.push(m), reviewEnhancedPrompt: choiceFn };
  const env = {
    window, setTimeout, A, ui, ZSEnhance, MSStudio:require('../extension/core/studio-workflows'), ZSParse:new Function(fs.readFileSync(path.join(root,'extension/core/parser.js'),'utf8')+';return ZSParse;')(), bg:async()=>{await A.waitForBackground?.();return{ok:true};},
    P: { conversationKey: () => A.chatKey || 'qa-chat' },
    getEnhanceSettings: () => settings,
    diag: () => {}, blenderWorkspaceInstructions:()=>'', activeEngineIds: () => ['roblox'], connectedEngineIds: () => ['roblox'], beginTaskProgress:()=>{}, bumpSys: () => {}, armCriticReview: () => {}, activeStudioInstructions: () => '[ACTIVE USER SETTINGS: ULTRA]',
    submitAndGetBase: async (text, images, opts) => { if (A.stop) { A.lastSendOk = false; return 3; } calls.submit.push({ text, opts }); await A.waitForAck?.(); return 3; },
    agentLoop: () => { calls.loop++; },
  };
  const fn = new Function(...Object.keys(env), 'let studioSettingsDirty = false; let criticSettings={enabled:false,passes:3}; let executionEffort="adaptive"; let autonomyLevel="guided";let customSkills=[]; function activeCustomSkills(){return customSkills;} function studioSettingsFingerprint(){return JSON.stringify([executionEffort,criticSettings,customSkills]);} function taskPromptAddon(source){return MSStudio.taskAddon(source,executionEffort,criticSettings);}\n' + gateSrc + '; return { gateEnhancedSend, noteSendEvent, setStudioDirty(value){studioSettingsDirty=value;}, setCritic(value){criticSettings.enabled=value;}, setEffort(value){executionEffort=value;studioSettingsDirty=true;}, isStudioDirty(){return studioSettingsDirty;} };');
  const api = fn(...Object.values(env));
  const press = (text, cancelable = true) => {
    const ev = { cancelable, defaultPrevented: false, stopped: false,
      preventDefault() { this.defaultPrevented = true; }, stopImmediatePropagation() { this.stopped = true; }, stopPropagation() {} };
    calls.listeners.keydown(ev);          // window-level capture listener runs first
    return { ev, held: api.gateEnhancedSend(text) };
  };
  return { calls, press, A, api };
}
const tick = () => new Promise((r) => setTimeout(r, 10));
const SHORT = 'make the door open when the player touches it';
const on = { mode: 'balanced', preview: true, injectEngineFacts: true, injectToolFacts: true, injectApproach: true, keepOriginalFirst: true };

t('enhancer off: original wording receives one active effort method without a preview', async () => {
  const h = harness({ ...on, mode: 'off' }, async () => ({ action: 'send', text: 'x' }));
  const r = h.press(SHORT);
  await tick();ok(r.held && r.ev.defaultPrevented);ok(h.calls.submit.length===1&&h.calls.submit[0].text.startsWith(SHORT)&&!h.calls.submit[0].text.includes('ENHANCED BRIEF'));ok(h.calls.submit[0].text.includes('ADAPTIVE · WORK METHOD'));
});
t('changed effort is delivered on the next turn with enhancer off, exactly once', async () => {
  const h=harness({...on,mode:'off'},async()=>{throw Error('Enhancer review should stay off');});
  h.api.setStudioDirty(true);const r=h.press(SHORT);await tick();
  ok(r.held&&r.ev.defaultPrevented);ok(h.calls.submit.length===1&&h.calls.submit[0].text.startsWith(SHORT)&&h.calls.submit[0].text.includes('ULTRA'));
  ok(h.press(SHORT).held);await tick();ok(h.calls.submit.length===2&&!h.calls.submit[1].text.includes('ACTIVE USER SETTINGS'),'Dirty settings are acknowledged once; each task still receives its active method');
});
t('Critic add-on with enhancer off: one send on every user prompt', async()=>{
  const h=harness({...on,mode:'off'},async()=>{throw Error('No enhancer preview required');});h.api.setCritic(true);
  const first=h.press(SHORT);await tick();ok(first.held&&h.calls.submit.length===1);ok(h.calls.submit[0].text.startsWith(SHORT));
  ok((h.calls.submit[0].text.match(/CRITIC · PROMPT ADD-ON/g)||[]).length===1,'Critic instructions appear once');
  h.press('Now polish the icons');await tick();ok(h.calls.submit.length===2&&h.calls.submit[1].text.includes('CRITIC · PROMPT ADD-ON'));
});
t('Ultra adds reference research and screenshots on every prompt, even with Critic off',async()=>{
  const h=harness({...on,mode:'off'},async()=>null);h.api.setEffort('ultra');h.press(SHORT);await tick();
  const text=h.calls.submit[0].text;ok(text.includes('REFERENCE RESEARCH AND VISUAL EVIDENCE')&&text.includes('2–3')&&text.includes('ms_screen_record')&&text.includes('screenshots'));
  ok(!text.includes('CRITIC · PROMPT ADD-ON'));
});
t('choosing original wording retains the separately enabled Critic add-on',async()=>{
  const h=harness(on,async()=>({action:'original'}));h.api.setCritic(true);h.press(SHORT);await tick();
  ok(h.calls.submit.length===1&&h.calls.submit[0].text.startsWith(SHORT));ok(h.calls.submit[0].text.includes('CRITIC · PROMPT ADD-ON'));ok(!h.calls.submit[0].text.includes('ENHANCED BRIEF'));
});
t('already-detailed prompts still receive an enabled Critic add-on',async()=>{
  const h=harness({...on,preview:false},async()=>null);h.api.setCritic(true);h.press('Implement the supplied design. '+('Detailed acceptance criteria, platform constraints and tests. '.repeat(80)));await tick();
  ok(h.calls.submit.length===1&&h.calls.submit[0].text.includes('CRITIC · PROMPT ADD-ON'));
});
t('settings changed during send are preserved for the following turn',async()=>{
  const h=harness({...on,mode:'off'},async()=>null);let release;h.A.waitForAck=()=>new Promise(r=>{release=r;});h.api.setStudioDirty(true);h.press(SHORT);await tick();
  h.api.setEffort('ultra');release();await tick();ok(h.api.isStudioDirty(),'A successful older send must not acknowledge newer settings');
  h.A.waitForAck=null;h.press('Now apply the latest effort');await tick();ok(h.calls.submit.length===2&&h.calls.submit[1].text.includes('REFERENCE RESEARCH'));ok(!h.api.isStudioDirty());
});
t('Ultra methods reach one task send and disappear after lowering effort',async()=>{
  const h=harness({...on,mode:'off'},async()=>null);h.api.setEffort('ultra');h.press('Fix this inventory menu');await tick();
  ok(h.calls.submit.length===1);ok((h.calls.submit[0].text.match(/ULTRA · EXECUTION METHODS/g)||[]).length===1);ok(h.calls.submit[0].text.includes('Method: interface'));
  h.api.setEffort('maximum');h.press('Now fix its alignment');await tick();
  ok(h.calls.submit.length===2&&!h.calls.submit[1].text.includes('ULTRA · EXECUTION METHODS')&&!h.calls.submit[1].text.includes('REFERENCE RESEARCH AND VISUAL EVIDENCE'));
});

t('navigation during background pacing resume cannot send into another chat',async()=>{
  const h=harness({...on,mode:'off'},async()=>null);let release;h.A.waitForBackground=()=>new Promise(r=>{release=r;});h.api.setCritic(true);h.press(SHORT);await tick();h.A.chatKey='another-chat';release();await tick();ok(h.calls.submit.length===0&&h.calls.loop===0);
});
t('enhanced: the original send is cancelled and NOTHING is sent until the user answers', async () => {
  let release; const gate = new Promise((r) => { release = r; });
  const h = harness(on, async (orig, res) => { await gate; return { action: 'send', text: res.text }; });
  const r = h.press(SHORT);
  ok(r.held && r.ev.defaultPrevented && r.ev.stopped, 'original send was not cancelled');
  await tick(); ok(h.calls.submit.length === 0, 'something was sent before the user answered');
  const r2 = h.press(SHORT);                      // impatient second Enter
  ok(r2.held && r2.ev.defaultPrevented, 'second send slipped past the open review');
  release(); await tick();
  ok(h.calls.submit.length === 1, 'expected exactly one message, got ' + h.calls.submit.length);
  ok(/ENHANCED BRIEF/.test(h.calls.submit[0].text) && h.calls.submit[0].text.startsWith(SHORT), 'enhanced text not sent');
  ok(h.calls.submit[0].opts.visible === true);
  ok(h.calls.loop === 1, 'agent loop not started after send');
});
t('choose original: only the original is sent (once)', async () => {
  const h = harness(on, async () => ({ action: 'original' }));
  h.press(SHORT); await tick();
  ok(h.calls.submit.length === 1 && h.calls.submit[0].text.startsWith(SHORT), JSON.stringify(h.calls.submit));
  ok(h.calls.loop === 1);
});
t('original task leads the send and an edited clarification follows it', async () => {
  const h = harness(on, async () => ({ action: 'send', text: '  my edited version  ' }));
  h.press(SHORT); await tick();
  ok(h.calls.submit.length === 1 && h.calls.submit[0].text.startsWith(SHORT)&&h.calls.submit[0].text.includes('my edited version')&&h.calls.submit[0].text.indexOf(SHORT)<h.calls.submit[0].text.indexOf('my edited version'));
});
t('cancel: nothing is sent and the loop does not start', async () => {
  const h = harness(on, async () => ({ action: 'cancel' }));
  const r = h.press(SHORT); await tick();
  ok(r.held && h.calls.submit.length === 0 && h.calls.loop === 0);
});
t('preview off: improved prompt replaces the original automatically (still one message)', async () => {
  const h = harness({ ...on, preview: false }, async () => { throw new Error('should not ask'); });
  h.press(SHORT); await tick();
  ok(h.calls.submit.length === 1 && /ENHANCED BRIEF/.test(h.calls.submit[0].text));
});
t('uncancelable events stay native; detailed wording receives the active method without rewriting', async () => {
  const h = harness(on, async () => ({ action: 'send', text: 'x' }));
  ok(!h.press(SHORT, false).held);
  ok(h.press('x'.repeat(1500)).held);await tick();ok(h.calls.submit.length===1&&h.calls.submit[0].text.startsWith('x'.repeat(1500))&&!h.calls.submit[0].text.includes('ENHANCED BRIEF'));
});
t('a failing review never strands the user', async () => {
  const h = harness(on, async () => { throw new Error('boom'); });
  h.press(SHORT); await tick();
  ok(h.calls.submit.length === 0 && h.calls.toasts.some((m) => /press Send again/.test(m)));
  const r = h.press(SHORT);                       // busy flag released -> works again
  ok(r.held);
});

t('a previous Stop does not suppress a new enhanced send', async () => {
  const h = harness(on, async (orig, result) => ({ action: 'send', text: result.text }));
  Object.assign(h.A, { stop: true, stopping: true, userStopped: true, stopAt: 10 });
  h.press(SHORT); await tick();
  ok(h.calls.submit.length === 1 && h.calls.loop === 1, 'stale Stop swallowed the enhanced send');
  ok(h.A.stop === false && h.A.stopping === false && h.A.userStopped === false);
});

t('original and automatic sends also clear a previous Stop', async () => {
  for (const automatic of [false, true]) {
    const h = harness({ ...on, preview: !automatic }, async () => ({ action: 'original' }));
    Object.assign(h.A, { stop: true, userStopped: true, stopAt: 10 });
    h.press(SHORT); await tick();
    ok(h.calls.submit.length === 1 && h.calls.loop === 1);
    ok(automatic ? /ENHANCED BRIEF/.test(h.calls.submit[0].text) : h.calls.submit[0].text.startsWith(SHORT));
  }
});

t('Stop pressed during review still cancels the pending send', async () => {
  let release; const choice = new Promise(r => { release = r; });
  const h = harness(on, () => choice);
  h.press(SHORT);
  Object.assign(h.A, { stop: true, userStopped: true, stopAt: 20 });
  release({ action: 'send', text: 'chosen' }); await tick();
  ok(h.calls.submit.length === 0 && h.calls.loop === 0 && h.A.stop === true);
  ok(h.calls.toasts.some(m => /stopped or the conversation changed/.test(m)));
});

t('conversation changes during review do not send into another chat', async () => {
  let release; const choice = new Promise(r => { release = r; });
  const h = harness(on, () => choice);
  h.press(SHORT); h.A.chatKey = 'another-chat';
  release({ action: 'original' }); await tick();
  ok(h.calls.submit.length === 0 && h.calls.loop === 0);
});

(async () => {
  for (const [name, fn] of results) {
    try { await fn(); console.log('  ok  ' + name); } catch (e) { failed++; console.log('  FAIL ' + name + ': ' + e.message); }
  }
  console.log(failed ? `\n${failed} FAILED` : '\nPASS enhancer send gate');
  process.exit(failed ? 1 : 0);
})();
