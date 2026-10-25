// SPDX-License-Identifier: GPL-3.0-or-later
// Guest /c markup inspected live, 2026-10-17. Explicit action roles and the
// model label identify actual turns; arbitrary marketing text is never a reply.
const ZSProvider = MSDomChat.create({id:"vani",name:"Vani",vision:()=>!document.querySelector('#public-composer'),
  path:/^\/(?:c|chat)(?:\/|$)/,
  preferredEditor:'#public-composer, textarea[data-testid="chat-input"], textarea[name="prompt"]',
  editor:'#public-composer, textarea[data-testid="chat-input"], textarea[name="prompt"], textarea[placeholder], [contenteditable="true"][role="textbox"], [data-zs-locked]',
  turns:'[data-turn-id]:has([data-turn-model]), [data-turn-id]:has([data-message-actions="user"]), [data-message-author-role], [data-role="assistant"], [data-role="user"], [data-testid="assistant-message"], [data-testid="user-message"]',
  user:'[data-turn-id]:has([data-message-actions="user"]), [data-message-author-role="user"], [data-role="user"], [data-testid="user-message"]',
  assistant:'[data-turn-id]:has([data-turn-model]), [data-message-author-role="assistant"], [data-role="assistant"], [data-testid="assistant-message"]',
  reply:item=>item.hasAttribute('data-turn-id')?[...item.querySelectorAll('[data-turn-model] + div')]:[item],
  exclude:'[data-message-actions], [data-turn-model]',
  thinking:'[data-testid="thinking"], [data-role="reasoning"], details[data-thinking], [data-testid*="reasoning"], [data-status="thinking"], [data-thinking="true"]',
  generating:'[data-status="thinking"], [data-thinking="true"]',
  send:'button[data-testid="send-button"], button[aria-label="Send message"], button[aria-label="Send"], button[type="submit"]',
  stop:'button[aria-label="Stop generating"], button[aria-label="Stop generation"], button[aria-label="Stop response"], button[aria-label="Stop responding"], button[aria-label="Stop thinking"], button[aria-label="Stop it"], button[data-testid="stop-button"]',
  stopText:/^stop(?: it| answering| responding| thinking| generating| generation)?$/i,
  busyNotice:/Vani is still (?:answering|responding)|response is still (?:running|generating)/i,
  async prepareComposer(reason,{frame,visible,sleep}){
    if(reason!=='startup'||!frame)return '';
    // Search is a native mode, not a local tool transport. Change only a
    // positively identified active toggle in this composer, never chat history.
    const controls=[...frame.querySelectorAll('button,[role="switch"],[role="checkbox"]')].filter(visible);
    const search=controls.find(e=>/^(?:search|web search|search the web)$/i.test((e.getAttribute('aria-label')||e.textContent||'').trim()));
    const on=e=>e&&(e.getAttribute('aria-pressed')==='true'||e.getAttribute('aria-checked')==='true'||e.dataset.state==='on'||e.dataset.state==='checked');
    if(on(search)){
      search.click();await sleep(100);
      if(on(search)&&search.isConnected)return 'Turn off Vani Search before starting Multi-Script. The Search toggle did not switch off; nothing was sent.';
    }
    return '';
  },
  openHint:"Open Vani Chat at https://c.vani.ai/chat (guest chat redirects to /c). Sign in for your saved chats. A marketing page is not a chat session.",verification:"Guest composer, turn roles, response and plain-text local-tool protocol inspected live. Authenticated workspace layouts and paid models require separate verification. Guest chat is text-only."});
