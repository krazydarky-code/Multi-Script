# SPDX-License-Identifier: GPL-3.0-or-later
"""Product limits separate from existing workspace safeguards and provider quotas."""
from pathlib import Path
import json
def policy():
    try:return json.loads((Path(__file__).with_name('edition.json')).read_text(encoding='utf-8'))
    except (OSError,ValueError):return {'edition':'public','workspace':{'maxPayloadBytes':262144,'maxCommandSeconds':60,'background':False}}
def check(name,args):
    p=policy();caps=p.get('workspace',{})
    if p.get('edition')=='dev':return None
    if name in ('ms_ws_write','ms_ws_edit','ms_ws_patch','ms_ws_replace'):
        if len(json.dumps(args,ensure_ascii=False).encode('utf-8'))>int(caps.get('maxPayloadBytes') or 262144):return 'Public edition allows up to 256 KiB per edit/write payload.'
    if name in ('ms_ws_run','ms_ws_build','ms_ws_check'):
        if args.get('background'):return 'Background processes are available in the development edition.'
        if float(args.get('timeout_s',60))>int(caps.get('maxCommandSeconds') or 60):return 'Public edition command timeout is at most 60 seconds.'
    return None
