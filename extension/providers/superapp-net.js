// SPDX-License-Identifier: GPL-3.0-or-later
// Observe the user's existing gateway; never capture tickets, cookies or headers.
(() => {
  'use strict';
  if (window.__msSuperAppObserver) return;
  window.__msSuperAppObserver = true;
  const Native = window.WebSocket;
  if (typeof Native !== 'function') return;
  const publish = value => window.postMessage({ source: 'ms-superapp-wire-v1', value }, location.origin);
  window.WebSocket = new Proxy(Native, {
    construct(Target, args, NewTarget) {
      const socket = Reflect.construct(Target, args, NewTarget);
      let url; try { url = new URL(String(args[0]), location.href); } catch { return socket; }
      if (!['superapp.chat', 'www.superapp.chat'].includes(url.hostname) || !url.pathname.includes('/gateway')) return socket;
      socket.addEventListener('message', e => {
        if (typeof e.data !== 'string' || e.data.length > 2000000) return;
        const event = MSSuperAppProtocol.decode(e.data);
        if (event) publish(event);
      });
      socket.addEventListener('close', () => publish({ type: 'wire_closed' }));
      const send = socket.send;
      socket.send = function (data) {
        const result = Reflect.apply(send, this, [data]);
        try {
          const frame = JSON.parse(data);
          if (frame.type === 'command' && frame.payload?.name === 'send_message') {
            publish({ type: 'local_send', stream: frame.payload.stream_key || '',
              text: String(frame.payload.args?.message || '').slice(0, 160) });
          }
        } catch {}
        return result;
      };
      return socket;
    }
  });
})();
