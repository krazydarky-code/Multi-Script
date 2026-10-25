Copy each block into a separate Discord post.

```text
MULTI-SCRIPT — PHONE CONTROL SETUP

Your phone can view task progress and send follow-ups or Stop requests. Work still runs on your computer.

1. Install the latest Dev build:
https://github.com/krazydarky-code/Multi-Script/releases/latest
Keep its extension and bridge on the same version. Start the bridge and a supported AI chat on the PC.

2. Connect your phone and computer to the same trusted Wi-Fi. Keep the PC awake and its desktop browser open.

3. Click the phone icon in the Multi-Script chatbar, or open Settings → Co-work → Phone control.

4. Select the PC's private network address, then click Enable on this network. If Windows asks, allow Python on your trusted Private network.

5. Open the exact address shown on your phone, including http:// and the port. No phone extension is needed.

6. Enter the eight-digit pairing code and a device name. Codes work once and expire after two minutes. Use New pairing code if needed.

7. Select the desktop chat on your phone. Enable background running on the PC if you want that chat to continue while its tab is hidden.

Phone control is for your local network, not cellular or another location. It uses local HTTP: use trusted Wi-Fi and never forward its port through your router.
```

```text
MULTI-SCRIPT — USING PHONE CONTROL

• Progress shows the plan, current stage and remaining work. Time ranges appear when enough step data exists. Simple replies show response stages; this does not claim a game was tested.

• Queue request adds a follow-up, correction or goal at a safe send point. It waits for the current AI response and preserves the desktop draft.

• Pause queue / Resume queue controls queued instructions. It does not pause a response or tool already running.

• Stop run asks the desktop to stop. A tool already sent may still finish.

• Check receipts before retrying after a lost connection. Acknowledged means the desktop accepted the action, not that the task is complete.

CAN'T CONNECT?
Check that both devices use the same network, the selected address is correct and Python is allowed on your Private network. Guest Wi-Fi isolation or a VPN can block access. If the bridge restarted, enable phone control again and pair with a fresh code.

Pairing lasts one hour. Use Revoke or Turn off remote on the desktop to remove access. Sleeping PCs and stale/disconnected chats cannot accept remote work.
```
