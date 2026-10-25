#!/usr/bin/env python3
"""Three-round, evidence-based product critic for Multi-Script releases."""
from pathlib import Path
import argparse, json, re, subprocess, sys, time
ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'runtime'/'critic-loop-report.json'

def run(cmd):
    started=time.time();p=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
    return {'command':' '.join(map(str,cmd)),'passed':p.returncode==0,'returnCode':p.returncode,'durationSeconds':round(time.time()-started,3),'tail':(p.stdout+p.stderr)[-1200:]}

def static_audit():
    findings=[]; manifest=json.load(open(ROOT/'runtime/product-manifest.json'))
    version=manifest['version']; ext=json.load(open(ROOT/'extension/manifest.json'))
    bridge=(ROOT/'runtime/bridge.py').read_text();plugin=(ROOT/'roblox-plugin/MultiScriptCompanion.server.lua').read_text();readme=(ROOT/'README.md').read_text();store=(ROOT/'docs/STORE_LISTING.md').read_text()
    def check(ok,severity,code,detail):
        if not ok: findings.append({'severity':severity,'code':code,'detail':detail})
    check(ext.get('version')==version,'critical','extension-version-drift','extension manifest differs from canonical product version')
    check(f'BRIDGE_VERSION = "{version}"' in bridge,'critical','bridge-version-drift','bridge differs from canonical product version')
    check(f'PLUGIN_VERSION = "{version}"' in plugin,'high','plugin-version-drift','Roblox companion differs from canonical product version')
    check(readme.startswith(f'# Multi-Script {version}'),'medium','readme-version-drift','README heading differs from canonical product version')
    skills=json.load(open(ROOT/'runtime/skills.json'));virtual=json.load(open(ROOT/'runtime/virtual-tools.json'))['tools']
    check(len(skills)==manifest['catalogue']['skills'],'critical','skill-count-drift','skill count differs from product manifest')
    check(len(virtual)==manifest['catalogue']['virtualSpecialists'],'critical','virtual-count-drift','virtual specialist count differs from product manifest')
    check(all(x.get('engine') for x in skills.values()),'high','implicit-skill-engine','one or more skills lacks explicit engine assignment')
    check(all(x.get('engineExecutionContract') for x in skills.values()),'high','missing-skill-runtime-contract','one or more skills lacks runtime compatibility contract')
    check(all(x.get('engineExecutionContract') for x in virtual.values()),'high','missing-virtual-runtime-contract','one or more specialists lacks runtime compatibility contract')
    companion=manifest['robloxCompanion']
    check(companion.get('defaultPermission')=='off','critical','plugin-default-permission','companion execution must default Off')
    check((companion.get('security') or {}).get('arbitraryCodeEvaluation') is False and 'loadstring(' not in plugin,'critical','plugin-arbitrary-eval','arbitrary Lua evaluation appeared')
    for route in ['/status','/catalog','/plugin/heartbeat','/plugin/register','/plugin/next','/plugin/result','/plugin/unregister']:
        check(route in plugin,'high','plugin-endpoint-missing',f'expected companion endpoint missing: {route}')
    check('306 reusable workflows' not in store,'medium','stale-store-count','store listing has obsolete workflow count')
    check('model-targeted' in (ROOT/'docs/release-notes/RELEASE_NOTES_6.12.0.md').read_text().lower(),'medium','arena-doc-drift','Arena model-targeted behavior is not documented')
    # Audit current declarations instead of requiring a stale local runtime report
    # to be distributed with the source package.
    sys.path.insert(0,str(ROOT/'tools'))
    import schema_audit
    current=schema_audit.load_bridge()
    schemas={'highRisk':sum(current._schema_risk_analysis(schema).get('riskBand')=='high' for _,schema in schema_audit.collect_schemas(current))}
    check(schemas.get('highRisk',0)==0,'high','high-risk-schema','schema audit still reports high-risk built-in contracts')
    return findings

def test_matrix():
    checks=[]
    for path in sorted((ROOT/'tests').glob('test_*.py')): checks.append(run([sys.executable,str(path)]))
    for path in sorted((ROOT/'tests').glob('test_*.js')): checks.append(run(['node',str(path)]))
    checks.append(run([sys.executable,str(ROOT/'tools/release_check.py')]))
    return checks

def critic(skip_tests=False,write=True):
    started=time.time();initial=static_audit()
    rounds=[{'round':1,'name':'static architecture and drift review','verdict':'pass' if not initial else 'revise','findings':initial,'evidence':['canonical product manifest parsed','catalogue and engine contracts inspected','plugin security boundary scanned','public current docs checked']}]
    checks=[] if skip_tests else test_matrix();failed=[x for x in checks if not x['passed']]
    rounds.append({'round':2,'name':'automated behavior and release regression','verdict':'skipped' if skip_tests else ('pass' if not failed else 'revise'),'findings':[{'severity':'critical','code':'test-failure','detail':x['command'],'tail':x['tail']} for x in failed],'evidence':[] if skip_tests else [f"{sum(x['passed'] for x in checks)}/{len(checks)} checks passed",'Python, JavaScript, provider, schema, plugin, security, release and archive-facing gates executed']})
    final_findings=static_audit();blocking=[x for x in final_findings if x['severity'] in ('critical','high')]
    recommendations=[
      {'priority':'next-live-validation','item':'Run editor-attached mutation/read-back smoke tests on Roblox Studio, Unity, Godot and Blender before store publication.','reason':'The sandbox cannot prove third-party editor state or future upstream MCP behavior.'},
      {'priority':'research-before-integration','item':'Evaluate Mirelo only after official API/MCP, authentication, licensing, export and automation terms can be verified.','reason':'Do not ship an undocumented website automation path.'},
      {'priority':'deferred','item':'Consider a VS Code extension after the bridge protocol and diagnostic contracts remain stable.','reason':'A future editor surface should reuse this bridge rather than fork execution logic.'},
    ]
    verdict='pass' if not blocking and not failed else 'revise'
    rounds.append({'round':3,'name':'final critic and product opportunity review','verdict':verdict,'findings':final_findings,'evidence':['companion defaults Off and exposes no arbitrary evaluation' if not any(x['code'] in ('plugin-default-permission','plugin-arbitrary-eval') for x in final_findings) else 'plugin boundary failure','all catalogue items retain explicit engine/runtime contracts' if not any('engine' in x['code'] or 'runtime-contract' in x['code'] for x in final_findings) else 'catalogue contract failure','release evidence is machine-readable'],'recommendations':recommendations})
    report={'product':'Multi-Script','version':json.load(open(ROOT/'runtime/product-manifest.json'))['version'],'generatedAtUnix':round(time.time()),'durationSeconds':round(time.time()-started,3),'verdict':verdict,'rounds':rounds,'testChecks':checks,'summary':{'critical':sum(x['severity']=='critical' for r in rounds for x in r.get('findings',[])),'high':sum(x['severity']=='high' for r in rounds for x in r.get('findings',[])),'medium':sum(x['severity']=='medium' for r in rounds for x in r.get('findings',[])),'recommendations':len(recommendations)}}
    if write: REPORT.write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--skip-tests',action='store_true');ap.add_argument('--no-write',action='store_true');args=ap.parse_args()
    result=critic(args.skip_tests,not args.no_write);print(json.dumps({'version':result['version'],'verdict':result['verdict'],'summary':result['summary'],'rounds':[{'round':x['round'],'verdict':x['verdict']} for x in result['rounds']]},indent=2));raise SystemExit(0 if result['verdict']=='pass' else 1)
