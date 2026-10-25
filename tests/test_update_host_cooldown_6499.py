"""HTTP refusals must not become a repeated GitHub request loop."""
import datetime,email.utils,json,sys,tempfile,urllib.error
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
import update_manager as u
now=1800000000
for code,headers,delay in [(429,{'Retry-After':'1200'},1200),(403,{'X-RateLimit-Remaining':'0','X-RateLimit-Reset':str(now+3600)},3600),(403,{},86400),(401,{},86400),(404,{},86400),(410,{},86400),(429,{'Retry-After':'bad'},60),(429,{'Retry-After':email.utils.format_datetime(datetime.datetime.fromtimestamp(now+180,datetime.timezone.utc))},180)]:
 error=urllib.error.HTTPError('https://github.com/test/feed',code,'fixture',headers,None)
 opener=Mock();opener.open.side_effect=error
 with patch.object(u.urllib.request,'build_opener',return_value=opener),patch.object(u.time,'time',return_value=now),patch.object(u.time,'sleep') as sleeping:
  try:u.download('https://github.com/test/feed',32768);raise AssertionError('Refusal accepted')
  except u.DownloadDeferred as failure:assert failure.retry_at==now+delay,(code,failure.retry_at)
  assert opener.open.call_count==1 and not sleeping.called,'Refused requests must stop immediately'
with tempfile.TemporaryDirectory() as temp:
 root=Path(temp);(root/'runtime').mkdir();(root/'extension').mkdir();(root/'extension/manifest.json').write_text('{"version":"1.0"}')
 cfg={'feedUrl':'https://github.com/old/repo/releases/latest/download/dev-update.json','publicKey':{'n':'fixture'}}
 channel=root/'runtime/update-channel.json';channel.write_text(json.dumps(cfg));private=root/'runtime/config.json';private.write_bytes(b'preserve private settings')
 with patch.object(u.time,'time',return_value=now),patch.object(u,'download',side_effect=u.DownloadDeferred('Rate limited',now+1200)) as request:
  for _ in range(3):
   try:u.Updater(root).check();raise AssertionError('Cooldown bypassed')
   except u.DownloadDeferred:pass
  assert request.call_count==1,'Cooldown survives updater-process restarts'
  assert u.Updater(root).status()['nextCheckAt']==(now+1200)*1000
 # A user-authorized feed migration must not inherit the inaccessible old host's cooldown.
 cfg['feedUrl']='https://github.com/new/repo/releases/latest/download/dev-update.json';channel.write_text(json.dumps(cfg))
 with patch.object(u.time,'time',return_value=now),patch.object(u,'download',return_value=b'{}') as request,patch.object(u,'verify_envelope',return_value={'version':'1.0'}):
  assert not u.Updater(root).check()['available'];assert request.call_count==1
 assert not (root/'.updates/host-retry.json').exists() and private.read_bytes()==b'preserve private settings'
print('PASS one-request HTTP refusal, numeric/date Retry-After, primary reset, durable cross-process cooldown, public-feed migration and private-data preservation.')
