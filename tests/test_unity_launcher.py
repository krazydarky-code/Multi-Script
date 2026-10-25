import importlib.util,os,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('launcher',ROOT/'runtime'/'launch_unity_mcp.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
with tempfile.TemporaryDirectory() as d:
 p=Path(d)/('uvx.exe' if os.name=='nt' else 'uvx'); p.write_text(''); os.environ['ZS_UVX_PATH']=str(p)
 assert m.find_uvx()==str(p)
 assert m.DEFAULT_VERSION=='10.2.0'
print('PASS Unity launcher pin and override')
