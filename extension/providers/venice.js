// SPDX-License-Identifier: GPL-3.0-or-later
// Classic and Agentic composer/role/final-answer selectors inspected live.
// Agentic user content also has .assistant-content: never treat that class alone
// as an assistant role. Native thinking/tool-step panels are not local commands.
const ZSProvider = (() => {
  const agent = () => /^\/chat\/agent(?:\/|$)/.test(location.pathname);
  const roles = '[data-message-author-role], [data-role="assistant"], [data-role="user"], [data-testid="assistant-message"], [data-testid="user-message"]';
  const agentUser = '[data-chat-turn-anchor] > .chakra-stack > [role="group"]:has(.assistant-content)';
  function responseError(){
    if(!agent())return null;
    const turns=document.querySelectorAll('[data-chat-turn-anchor]');let turn=null;
    for(let i=turns.length-1;i>=0;i--){const node=turns[i];if(node.getClientRects().length&&!node.closest('[hidden],[aria-hidden="true"],#zs-root')){turn=node;break;}}
    if(!turn)return null;
    // Only the latest native error panel, outside model prose or quoted code.
    // A failed turn can have no assistant prose node at all.
    for(const node of turn.querySelectorAll('div,p,span,[role="alert"]')){
      if(node.children.length||node.closest('.prose,pre,code,blockquote,[role="group"],#zs-root'))continue;
      const text=(node.textContent||'').trim();
      if(!/^(?:Response failed\. Please try again\.|An unexpected error occurred\. Please try again\.)$/i.test(text))continue;
      const panel=node.closest('[role="alert"]')||node.parentElement;
      if(panel?.querySelector('button')&&node.getClientRects().length)return {text,item:turn};
    }
    return null;
  }
  return MSDomChat.create({id:'venice',name:'Venice',vision:true,path:/^\/chat\/(?:classic|agent)(?:\/|$)/,
    editor:'textarea[name="prompt-textarea"], [data-zs-locked]',
    get turns(){return (agent() ? '[data-chat-turn-anchor] .assistant, '+agentUser : '.assistant[data-testid="text-chat-message"]')+', '+roles;},
    get user(){return (agent()?agentUser+', ':'')+'[data-message-author-role="user"], [data-role="user"], [data-testid="user-message"]';},
    get assistant(){return (agent()?'[data-chat-turn-anchor] .assistant':'.assistant[data-testid="text-chat-message"]')+', [data-message-author-role="assistant"], [data-role="assistant"], [data-testid="assistant-message"]';},
    get reply(){return agent()?'.assistant-content > div:nth-child(2) .prose':null;},
    thinking:'[data-role="reasoning"], [data-testid="thinking"]',
    nativeError:'[data-is-error="true"], [data-isratelimited="true"]',
    responseError,
    get send(){return agent()?'button[aria-label="Send message"]':'button[aria-label="Submit chat"]';},
    stop:'button[aria-label="Stop generating"], button[aria-label="Stop generation"], button[aria-label="Stop response"]',
    openHint:'Open Venice Agentic Chat (venice.ai/chat/agent) or Classic Chat. Select the model available on your account in Venice itself.',
    verification:'Both chat layouts and a guest response inspected live. Agentic final prose is read separately from native tool steps. The selected Venice model is preserved; no paid-model entitlement is implied.'});
})();
