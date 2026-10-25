# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded execution receipts. No arguments, credentials or public output endpoint."""
import collections,threading,time,json
_lock=threading.RLock();_rows=collections.deque(maxlen=120);_sequence=0
RANK={'off':0,'read':1,'project':2,'full':3}
def record(tool,ok,elapsed,text='',permission='full'):
 global _sequence
 with _lock:
  _sequence+=1
  _rows.append({'sequence':_sequence,'time':time.time(),'tool':str(tool)[:120],'status':'done' if ok else 'error','durationMs':round(max(0,elapsed)*1000),'permission':permission,'output':str(text)[:1800]})
def snapshot(mode):
 with _lock:
  rows=[]
  for item in _rows:
   row=dict(item)
   if RANK.get(mode,0)<RANK.get(item['permission'],3):row['output']='Output requires '+item['permission']+' access in the plugin.'
   rows.append(row)
  return {'entries':rows,'lastSequence':_sequence,'scope':'Observed bridge execution receipts. A completed command does not certify the project or a visual test.'}
