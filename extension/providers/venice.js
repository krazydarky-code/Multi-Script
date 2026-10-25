// SPDX-License-Identifier: GPL-3.0-or-later
// Classic and Agentic composer/role/final-answer selectors inspected live.
// Agentic user content also has .assistant-content: never treat that class alone
// as an assistant role. Native thinking/tool-step panels are not local commands.
const ZSProvider = (() => {
  const agent = () => /^\/chat\/agent(?:\/|$)/.test(location.pathname);
  const roles = '[data-message-author-role], [data-role="assistant"], [data-role="user"], [data-testid="assistant-message"], [data-testid="user-message"]';
  const agentUser = '[data-chat-turn-anchor] > .chakra-stack > [role="group"]:has(.assistant-content)';
  return MSDomChat.create({id:'venice',name:'Venice',vision:true,path:/^\/chat\/(?:classic|agent)(?:\/|$)/,
    editor:'textarea[name="prompt-textarea"], [data-zs-locked]',
    get turns(){return (agent() ? '[data-chat-turn-anchor] .assistant, '+agentUser : '.assistant[data-testid="text-chat-message"]')+', '+roles;},
    get user(){return (agent()?agentUser+', ':'')+'[data-message-author-role="user"], [data-role="user"], [data-testid="user-message"]';},
    get assistant(){return (agent()?'[data-chat-turn-anchor] .assistant':'.assistant[data-testid="text-chat-message"]')+', [data-message-author-role="assistant"], [data-role="assistant"], [data-testid="assistant-message"]';},
    get reply(){return agent()?'.assistant-content > div:nth-child(2) .prose':null;},
    thinking:'[data-role="reasoning"], [data-testid="thinking"]',
    nativeError:'[data-is-error="true"], [data-isratelimited="true"]',
    get send(){return agent()?'button[aria-label="Send message"]':'button[aria-label="Submit chat"]';},
    stop:'button[aria-label="Stop generating"], button[aria-label="Stop generation"], button[aria-label="Stop response"]',
    openHint:'Open Venice Agentic Chat (venice.ai/chat/agent) or Classic Chat. Select the model available on your account in Venice itself.',
    verification:'Both chat layouts and a guest response inspected live. Agentic final prose is read separately from native tool steps. The selected Venice model is preserved; no paid-model entitlement is implied.'});
})();
