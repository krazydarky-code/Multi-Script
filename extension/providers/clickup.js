// SPDX-License-Identifier: GPL-3.0-or-later
// Never fall back to ClickUp team-channel composers: they message humans.
const ZSProvider = (()=>{
  const human='cu-chat-channel, cu-chat-thread, cu-task-comment, [data-testid="team-chat"], [data-testid="task-comments"], [data-ms-human-chat]';
  const headingSelector='h1,h2,h3,[role="heading"]';
  const aiHeading=h=>/^(?:Tell .{1,60} what to do next|Ask Brain)$/i.test(h.textContent.trim().replace(/\s+/g,' '));
  const editors='textarea,[contenteditable="true"],[contenteditable="plaintext-only"],[data-zs-locked]';
  const aiHint=/^(?:Type your request:\s*I[’']ll search, answer, or build it for you\.?|Turn ideas into action\.\s*Create tasks, documents, or anything else with a prompt\.?)$/i;
  let landing=null;
  function privateScopes(){
    const roots=[...document.querySelectorAll('[data-testid="brain-chat"], [data-test="brain-chat"], cu-ai-chat, cu-brain-chat, cu-ai-chat-modal, cu-ai-chat-panel, cu-ai-hub-chat, cu-brain-chat-conversation, [data-testid="ai-chat"], [data-test="ai-chat"], [data-ms-clickup-ai-chat], [data-test="ai-hub-chat"]')];
    const route=location.pathname+location.search;
    // Once a landing composer is positively identified, its placeholder and
    // greeting may disappear on focus/input. Keep only that same live editor
    // in that same bounded surface and route. Never retain a human-channel root.
    if(landing){
      const {root,heading,frame}=landing;
      if(landing.route!==route||!root.isConnected||root.closest(human)||root.querySelector(human)||heading.isConnected&&!aiHeading(heading))landing=null;
      else{
        if(!landing.editor.isConnected&&frame?.isConnected&&root.contains(frame))landing.editor=[...frame.querySelectorAll(editors)].filter(e=>!e.closest(human)).at(-1)||landing.editor;
        const editor=landing.editor;
        if(editor.isConnected&&root.contains(editor)&&editor.matches(editors))return [...new Set(roots.some(r=>r.contains(editor))?roots:[...roots,root])];
      }
    }
    // The new Ask Brain landing page does not expose a chat wrapper yet.
    // Require its distinctive AI prompt AND AI heading in a bounded surface.
    // A generic textarea, team channel or task comment is never a fallback.
    for(const hintNode of document.querySelectorAll('textarea[placeholder],[data-placeholder],[aria-placeholder]')){
      const editor=hintNode.matches(editors)?hintNode:hintNode.closest(editors);
      if(!editor||editor.closest('#zs-root,#zs-bar'))continue;
      const hint=hintNode.getAttribute('placeholder')||hintNode.getAttribute('data-placeholder')||hintNode.getAttribute('aria-placeholder')||'';
      if(!aiHint.test(hint.trim().replace(/\s+/g,' '))||editor.closest(human)||roots.some(r=>r.contains(editor)))continue;
      for(let parent=editor.parentElement;parent&&parent!==document.body;parent=parent.parentElement){
        if(parent.matches(human)||parent.querySelector(human))break;
        const heading=[...parent.querySelectorAll(headingSelector)].find(aiHeading);
        if(heading){landing={root:parent,editor,heading,route,frame:editor.closest('form,[data-ms-ai-composer],[data-testid="composer"]')||editor.parentElement};roots.push(parent);break;}
      }
    }
    return [...new Set(roots)];
  }
  return MSDomChat.create({id:"clickup",name:"ClickUp",vision:false,persistentBarWhenNoEditor:true,preferComposerScope:true,
  scope:privateScopes,
  ignoreRoots:'cu-chat-channel, cu-chat-thread, cu-task-comment, [data-testid="team-chat"], [data-testid="task-comments"], [data-ms-human-chat]',
  contextAttributes:['data-conversation-id','data-chat-id','data-thread-id'],
  quietMs:2500,
  generating:'[data-testid="brain-thinking"], [data-test="ai-thinking"], cu-ai-loading, [data-is-streaming="true"]',
  stopText:/^(?:stop(?: generating| generation| response| answering)?|cancel response)$/i,
  exclude:'[data-native-tool-result], [data-testid="tool-result"], [data-role="tool"], [data-testid="citation-preview"]',
  editor:'textarea, [contenteditable="true"], [contenteditable="plaintext-only"], [data-zs-locked]',
  turns:'[data-message-author-role], [data-role="assistant"], [data-role="user"], [data-testid="assistant-message"], [data-testid="user-message"]',
  user:'[data-message-author-role="user"], [data-role="user"], [data-testid="user-message"]',assistant:'[data-message-author-role="assistant"], [data-role="assistant"], [data-testid="assistant-message"]',
  thinking:'[data-role="reasoning"], [data-testid="thinking"]',send:'button[aria-label="Send message"], button[aria-label="Send"], button[type="submit"]',
  stop:'button[aria-label="Stop generating"], button[aria-label="Stop generation"]',
  openHint:"Open ClickUp Brain’s Ask tab for a private AI conversation. The Super Agents creation form, team channels and task comments are separate surfaces.",verification:"Private-AI scope and Ask Brain landing layout tested in fixtures; authenticated ClickUp Brain UI is not verified."});
})();
