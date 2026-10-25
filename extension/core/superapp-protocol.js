// SPDX-License-Identifier: GPL-3.0-or-later
// Data-only SuperApp wire decoding; shared by the extension and desktop client.
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.MSSuperAppProtocol = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const contentText = value => typeof value === 'string' ? value : Array.isArray(value)
    ? value.filter(x => x && ['text', 'output_text', 'input_text'].includes(x.type)).map(x => x.text || '').join('') : '';
  function decode(raw) {
    let frame;
    try { frame = typeof raw === 'string' ? JSON.parse(raw) : raw; } catch { return null; }
    if (!frame || typeof frame !== 'object') return null;
    const payload = frame.payload || {};
    const data = payload.data || frame.data || frame;
    const name = data.event || data.type || frame.type;
    if (typeof name !== 'string') return null;
    const response = data.response;
    const out = { type: name, stream: payload.stream_key || data.stream_key || '',
      id: data.message_id || data.ai_message_id || response?.id || data.id || '',
      sessionId: data.agent_session?.session_id || '', text: '', final: false, running: false,
      role: data.role || '', error: '', reasoning: '' };
    if (name === 'ai_chunk_broadcast') {
      const chunks = data.messages_until_now || [];
      out.text = chunks.filter(x => x.msg_type === 'answer' && x.type === 'text').map(x => contentText(x.content)).join('');
      out.reasoning = chunks.filter(x => ['thinking', 'reasoning'].includes(x.msg_type)).map(x => contentText(x.content)).join('');
      out.running = true; out.role = 'assistant'; out.snapshot = true;
    } else if (name === 'ai_complete') {
      out.text = contentText(data.full_response); out.final = true; out.role = 'assistant'; out.snapshot = true;
    } else if (name === 'new_message') {
      out.text = contentText(data.content); out.final = data.role === 'assistant'; out.snapshot = true;
    } else if (/^response\.(output_text|text)\.delta$/.test(name)) {
      out.text = typeof data.delta === 'string' ? data.delta : data.delta?.text || ''; out.role = 'assistant'; out.running = true;
    } else if (/reasoning.*delta/.test(name)) {
      out.reasoning = typeof data.delta === 'string' ? data.delta : ''; out.running = true;
    } else if (/progress|sandbox|tool_start|agent_status|thinking/.test(name)) {
      out.running = !/complete|failed|cancelled/.test(data.status || '');
      out.reasoning = data.label || data.message || data.status || name;
    }
    if (/error|failed/.test(name)) out.error = data.error?.message || data.message || String(data.error || name);
    if (/cancelled|canceled/.test(name)) out.final = true;
    return out;
  }
  function responseText(obj) {
    if (typeof obj?.output_text === 'string') return obj.output_text;
    return (obj?.output || []).filter(x => x.type === 'message' || x.content).map(x => contentText(x.content)).join('\n').trim();
  }
  return { decode, contentText, responseText };
});
