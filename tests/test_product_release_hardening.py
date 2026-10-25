import importlib.util,json,sys,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];w=types.ModuleType("websockets");w.ConnectionClosed=Exception;sys.modules.setdefault("websockets",w)
sp=importlib.util.spec_from_file_location("b65",ROOT/"runtime/bridge.py");b=importlib.util.module_from_spec(sp);sp.loader.exec_module(b)
assert all(x.get("promptRewriteIndependent") is True and len(x.get("productReleaseGate",[]))==7 and len(x.get("defectPriorityOrder",[]))==7 for x in b.ADVANCED_DIRECT_CONTRACTS.values())
sk={k:{**json.load(open(ROOT/"runtime/skill-shared-policy.json")),**v} for k,v in json.load(open(ROOT/"runtime/skills.json")).items()};assert len(sk)==249 and all(x.get("promptRewriteIndependent") is True and len(x.get("productReleaseGate",[]))==7 for x in sk.values())
v=json.load(open(ROOT/"runtime/virtual-tools.json"));assert len(v["tools"])==263 and all(x.get("promptRewriteIndependent") is True and len(x.get("productReleaseGate",[]))==7 for x in v["tools"].values())
st=json.load(open(ROOT/"runtime/studio-standard.json"));assert st["version"]=="12.1" and st["promptRewriting"]["independentFromCapabilityEnhancement"] and len(st["perfectReleaseGate"])==8 and st["menuSettingsCoverage"] and st["zeroScriptEvolution"] and st["portableSettings"]
main=(ROOT/"extension/core/main.js").read_text();cfg=(ROOT/"extension/core/config.js").read_text()
assert 'ZS.skillToolCoveragePrompt' in main and 'behavior.promptSkills === "automatic" && ZS.skillToolCoveragePrompt' not in main
for x in ('Prompt rewriting','skills always active','Off — literal prompt','Suggest rewrite','Automatic rewrite'):assert x in main
for x in ('PROMPT REWRITING OFF','PROMPT REWRITING SUGGEST-ONLY','PROMPT REWRITING AUTOMATIC','ALWAYS-ON CAPABILITY RULE'):assert x in cfg
print("PASS 6.5 release hardening: rewriting is optional while every skill/tool remains active; all catalogues carry product gates")
