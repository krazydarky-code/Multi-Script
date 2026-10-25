import importlib.util
from pathlib import Path
R=Path(__file__).resolve().parents[1];sp=importlib.util.spec_from_file_location("critic",R/"tools/critic_loop.py");c=importlib.util.module_from_spec(sp);sp.loader.exec_module(c)
r=c.critic(skip_tests=True,write=False);assert r["verdict"]=="pass",r;assert len(r["rounds"])==3 and r["rounds"][0]["verdict"]=="pass" and r["rounds"][1]["verdict"]=="skipped" and r["rounds"][2]["verdict"]=="pass";assert len(r["rounds"][2]["recommendations"])==3
print("PASS three-round product critic: architecture, regressions placeholder, opportunities and release verdict")
