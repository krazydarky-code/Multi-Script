# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded PDF page viewing in an isolated process; never initialize PDF scripts.

PDFium is not thread-safe. Each worker owns and closes its document; the bridge
admits one worker at a time and kills it on timeout. No runtime installation.
"""
from pathlib import Path
import base64,io,json,subprocess,sys,threading
_SLOT=threading.BoundedSemaphore(1)
def render(path,page,metadata):
 if type(page) is not int or not 1<=page<=2000:raise ValueError('page must be 1–2000')
 if Path(path).stat().st_size>100_000_000:raise ValueError('PDF reference exceeds 100 MB')
 with _SLOT:
  result=subprocess.run([sys.executable,str(Path(__file__).resolve()),str(path),str(page)],capture_output=True,text=True,encoding='utf-8',timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 if result.returncode:raise ValueError('PDF preview unavailable: '+result.stderr[-500:]+'. Run Setup to prepare the reference reader; the text catalogue remains available.')
 data=json.loads(result.stdout)
 return {'text':json.dumps({**metadata,'page':page,'pages':data['pages'],'kind':'stored-pdf-reference','text':data['text'],'note':'Actual archived reference page, not a capture of the current project.'}), 'images':[{'data':data['png'],'mimeType':'image/png'}]}
def _worker():
 import pypdfium2 as pdfium
 path,page=Path(sys.argv[1]),int(sys.argv[2])
 with pdfium.PdfDocument(path) as document:
  if not 1<=page<=min(len(document),2000):raise ValueError('Page is outside this PDF')
  sheet=document[page-1]
  try:
   width,height=sheet.get_size()
   if min(width,height)<=0:raise ValueError('Invalid page dimensions')
   scale=min(1.5,1100/max(width,height))
   bitmap=sheet.render(scale=scale)
   try:
    picture=bitmap.to_pil();out=io.BytesIO();picture.save(out,format='PNG');picture.close()
   finally:bitmap.close()
   textpage=sheet.get_textpage()
   try:text=textpage.get_text_bounded()[:3000]
   finally:textpage.close()
  finally:sheet.close()
  raw=out.getvalue()
  if len(raw)>3_000_000:raise ValueError('Rendered page exceeds preview budget')
  print(json.dumps({'pages':len(document),'text':text,'png':base64.b64encode(raw).decode()}))
if __name__=='__main__':_worker()
