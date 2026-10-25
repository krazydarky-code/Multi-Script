# SPDX-License-Identifier: GPL-3.0-or-later
"""Resolve exact schemas across built-in, toolkit, companion and live MCP sources."""
import copy

ALIASES={'ms_roblox_run_lua':'ms_roblox_run_luau'}
def arguments(args):
    out=dict(args or {})
    if not out.get('tool'):
        values={str(out[k]).strip() for k in ('tool_name','name','command') if isinstance(out.get(k),str) and out[k].strip()}
        if len(values)==1:
            out['tool']=values.pop()
            for key in ('tool_name','name','command'):out.pop(key,None)
    return out

def details(target,server,available,builtins,toolkit=(),companions=(),contracts=None):
    target=ALIASES.get(str(target).strip(),str(target).strip());server=str(server or '').strip()
    bare=lambda n:str(n).split('/')[-1].split('.')[-1]
    rows=[t for t in available if t.get('name')==target or bare(t.get('name'))==bare(target)]
    if server:rows=[t for t in rows if t.get('server')==server]
    if len(rows)>1:
        exact=[t for t in rows if t.get('name')==target]
        if len(exact)==1:rows=exact
    if len(rows)>1:return {'available':False,'status':'ambiguous','choices':[{'name':t['name'],'server':t.get('server')} for t in rows],'next':'Supply server from these exact choices.'}
    known=[(builtins,'built-in'),(toolkit,'toolkit'),(companions,'companion')]
    if rows:
        tool=copy.deepcopy(rows[0]);source=next((label for group,label in known if any(t['name']==bare(tool['name']) for t in group)),'native MCP')
        return {'available':True,'status':'advertised','source':source,'tool':tool,'contract':(contracts or {}).get(bare(tool['name'])),'executionRequired':True,'note':'This is its current advertised schema, not evidence that a call or project test succeeded.'}
    for group,label in known:
        tool=next((t for t in group if t.get('name')==target),None)
        if tool and not server:
            return {'available':False,'status':'not advertised','source':label,'tool':copy.deepcopy(tool),'next':'Enable the required engine/toolset, then refresh list_commands. A schema does not grant access.'}
    return {'available':False,'status':'not found in current catalog','requested':target,'next':'Read list_commands for this session. For Roblox enable its Studio MCP server, or enable the companion toolset for msrb_* tools. Do not repeat guessed names.'}
