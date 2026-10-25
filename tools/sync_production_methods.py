#!/usr/bin/env python3
"""Synchronize generated production-method data and read-only guides."""
from pathlib import Path
import json,re,sys
root=Path(__file__).resolve().parents[1];folder=root/'runtime/skill-resources/roblox-production';pack=json.loads((folder/'methods.json').read_text(encoding='utf-8'))
p=root/'extension/core/roblox-production.js';source=p.read_text(encoding='utf-8');line='const pack='+json.dumps(pack,ensure_ascii=False,separators=(',',':'))+';';source=re.sub(r'^const pack=.*;$',lambda _:line,source,count=1,flags=re.M);p.write_text(source,encoding='utf-8')
for key,title in [('gui','Roblox GUI production'),('animation','Roblox animation production')]:
 d=pack[key];body='# Multi-Script — '+title+'\n\n'+pack['policy']+'\n\n'
 for phase in ['inspect','design','build','integrate','verify','failures']:body+='## '+phase.title()+'\n\n'+d[phase]+'\n\n'
 if key=='gui':body+='## Style recipes\n\n'+''.join('### '+k+'\n\n'+v+'\n\n' for k,v in pack['themes'].items())
 body+='## Sources and use\n\nAdapted from user-provided ProjectGUI and Ultraskills references. Provenance hashes are in PROVENANCE.json. UltraLab quality patterns retain GPL attribution under legal/upstream-gpl. Linked third-party image assets are not imported.\n\n'+''.join('- ['+x['title']+']('+x['url']+')\n' for x in pack['references'])
 study=pack.get('referenceStudies',{})
 if study:
  body+='\n## Expanded reference study\n\n'+study['policy']+'\n\n'
  for item in study['sources']:
   if (item['attachment']<=17)==(key=='gui'):body+='- Supplied image '+str(item['attachment'])+': '+item['observed']+'\n'
 (folder/d['entry']).write_text(body,encoding='utf-8')
if '--preserve-catalog' in sys.argv:
 print('Synchronized existing browser methods and two full guides; original skill definitions preserved.');raise SystemExit(0)
skills_path=root/'runtime/skills.json';skills=json.loads(skills_path.read_text(encoding='utf-8'));updated=0
for skill in skills.values():
 binding=skill.get('resources',{})
 if binding.get('revision')!=pack['revision']:continue
 method=pack['gui' if binding.get('entry')=='GUI.md' else 'animation'];workflow=skill['executionWorkflow']
 for target,phases in [('inspect',['inspect']),('execute',['build','integrate']),('verify',['verify']),('craft',['design']),('recovery',['failures'])]:workflow[target]=' '.join(method[phase] for phase in phases)
 updated+=1
skills_path.write_text(json.dumps(skills,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(f'Synchronized browser production data, two full reference methods and {updated} bound skill workflows.')
