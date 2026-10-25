// SPDX-License-Identifier: GPL-3.0-or-later
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const pw = require('./playwright-env');
const root = path.join(__dirname, '..');
const server = http.createServer((_req, res) => { res.setHeader('Content-Type', 'text/html'); res.end('<main><textarea placeholder="Send a message"></textarea><button aria-label="Send">Send</button></main>'); });

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await pw.launch(); if (!browser) throw new Error('Browser required for SuperApp wire regression');
  try {
    const page = await browser.newPage();
    await page.addInitScript(() => {
      window.WebSocket = class FixtureSocket extends EventTarget {
        constructor(url) { super(); this.url = url; }
        send(frame) { this.sent = frame; }
      };
    });
    await page.addInitScript({ path: path.join(root, 'extension/core/superapp-protocol.js') });
    await page.addInitScript({ path: path.join(root, 'extension/providers/superapp-net.js') });
    await page.goto('http://127.0.0.1:' + server.address().port);
    await page.addScriptTag({ content: fs.readFileSync(path.join(root, 'extension/providers/superapp.js'), 'utf8') + '\nwindow.provider = ZSProvider;' });
    await page.evaluate(() => {
      window.gateway = new WebSocket('wss://superapp.chat/ws/v1/gateway/?ticket=DO_NOT_LEAK');
      window.frames = [];
      window.addEventListener('message', e => { if (e.data?.source === 'ms-superapp-wire-v1') frames.push(e.data); });
      gateway.send(JSON.stringify({ type: 'command', payload: { name: 'send_message', stream_key: 'channel:one::chat', args: { message: 'Build a coin system' } } }));
    });
    await page.waitForFunction(() => provider.diagnostics().state.wire.running);
    assert.equal(await page.evaluate(() => provider.isGenerating()), true);
    assert.equal(await page.evaluate(() => provider.lastAssistant()), null, 'old DOM reply must not be mistaken for this pending turn');
    const feed = async (event, stream = 'channel:one::chat') => page.evaluate(({ event, stream }) => gateway.dispatchEvent(new MessageEvent('message', { data: JSON.stringify({ type: 'event', payload: { stream_key: stream, data: event } }) })), { event, stream });
    await feed({ event: 'sandbox_progress', status: 'running', message: 'Installing project dependencies' });
    await page.waitForFunction(() => provider.readAssistant().thinking === '' || provider.isGenerating());
    await feed({ event: 'ai_chunk_broadcast', message_id: 'assistant-1', messages_until_now: [{ msg_type: 'answer', type: 'text', content: '{"command":"read_file","params":{"path":"a.lua"}}' }] });
    await page.waitForFunction(() => provider.readAssistant().reply.includes('read_file'));
    const first = await page.evaluate(() => provider.lastAssistantId());
    await feed({ event: 'ai_complete', message_id: 'other', full_response: 'Unrelated shared-room reply' }, 'channel:other::chat');
    assert.equal(await page.evaluate(() => provider.lastAssistantId()), first);
    assert.equal(await page.evaluate(() => provider.isGenerating()), true);
    await feed({ event: 'ai_complete', message_id: 'assistant-1', full_response: '{"command":"read_file","params":{"path":"a.lua"}}' });
    await page.waitForFunction(() => !provider.isGenerating());
    assert.equal(await page.evaluate(() => provider.lastAssistantId()), first);
    await feed({ event: 'new_message', message_id: 'human-1', role: 'user', content: [{ type: 'text', text: '{"command":"delete_path"}' }] });
    assert.equal(await page.evaluate(() => provider.lastAssistantId()), first, 'human messages do not replace the assistant');
    assert.equal(await page.evaluate(() => JSON.stringify(frames).includes('DO_NOT_LEAK')), false);
    await page.evaluate(() => gateway.send(JSON.stringify({ type: 'command', payload: { name: 'send_message', stream_key: 'channel:two::chat', args: { message: 'Another task' } } })));
    await page.waitForFunction(() => provider.diagnostics().state.wire.stream === 'channel:two::chat');
    assert.equal(await page.evaluate(() => provider.lastAssistant()), null);
    await feed({ event: 'ai_error', error: { message: 'Sandbox unavailable' } }, 'channel:two::chat');
    await page.waitForFunction(() => provider.scanError().includes('Sandbox unavailable'));
    console.log('PASS SuperApp gateway: 10 browser checks, assistant identity, channel isolation, progress, completion, errors and ticket privacy');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); server.close(); process.exitCode = 1; });
