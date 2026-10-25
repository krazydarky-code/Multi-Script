#!/usr/bin/env python3
"""Run isolated Multi-Script regression suites and retain honest per-suite results.

python tools/verify.py all --output test-results
python tools/verify.py js test_provider_browser_matrix_641.js
Optional dependencies: Playwright/Chromium, Pillow, websockets and lupa. Tests
report environment skips; mocked engines do not certify live editor behavior.
"""
from pathlib import Path
import argparse,json,os,shutil,subprocess,sys,tempfile,time

ROOT=Path(__file__).resolve().parents[1]

def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('group',choices=('js','py','all'))
    parser.add_argument('files',nargs='*')
    parser.add_argument('--output',type=Path,default=ROOT/'test-results')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    groups=('js','py') if args.group=='all' else (args.group,)
    targets=[]
    for group in groups:
        targets.extend((group,p) for p in sorted((ROOT/'tests').glob('test_*.'+group)) if not args.files or p.name in args.files)
    missing=set(args.files)-{p.name for _,p in targets}
    if missing:parser.error('Unknown test files: '+', '.join(sorted(missing)))
    results=[]
    for group,path in targets:
        command=([sys.executable,'-u','-X','utf8'] if group=='py' else ['node'])+[str(path)]
        started=time.monotonic();limit=900 if path.name in ('test_settings_sweep.js','test_fnaf_theme.js','test_new_theme_matrix.js') else 240
        with tempfile.TemporaryDirectory(prefix='multiscript-test-') as data:
            env={**os.environ,'PYTHONUTF8':'1','PYTHONUNBUFFERED':'1','MS_TEST_PYTHON':sys.executable,'MS_STUDIO_DATA_DIR':data,'PATH':str(Path(sys.executable).parent)+os.pathsep+os.environ.get('PATH','')}
            if not shutil.which(command[0]):code=127;output='Missing test runtime: '+command[0]
            else:
                process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=os.name!='nt')
                try:raw,_=process.communicate(timeout=limit);code=process.returncode
                except subprocess.TimeoutExpired:
                    if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                    else:
                        import signal
                        os.killpg(process.pid,signal.SIGKILL)
                    raw,_=process.communicate();raw+=f'\nTIMEOUT after {limit}s'.encode();code=-1
                output=raw.decode('utf-8','replace')
        record={'file':path.name,'exitCode':code,'seconds':round(time.monotonic()-started,2),'skipped':'SKIP' in output or 'skipped' in output.lower()}
        results.append(record);(args.output/(path.name+'.log')).write_text(output,encoding='utf-8')
        (args.output/'results.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
        print(('PASS' if code==0 else 'FAIL')+' '+path.name+f' ({record["seconds"]}s)',flush=True)
        if code:print(output[-2000:],flush=True)
    print(f'{sum(r["exitCode"]==0 for r in results)}/{len(results)} suites returned success; inspect explicit environment skips in logs.')
    return int(any(r['exitCode'] for r in results))

if __name__=='__main__':raise SystemExit(main())
