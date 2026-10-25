"""Prepare the checksum-pinned official Luau CLI for native CI verification."""
from pathlib import Path
import hashlib,io,os,platform,sys,urllib.request,zipfile
VERSION='0.744'
ASSETS={
 'Windows':('luau-windows.zip','fde3e22c557aac6afe20a34e8050b7d8c290fa42638c04274a307ed5d0ef0db8'),
 'Linux':('luau-ubuntu.zip','6506f0852c623aaffcb28494aac16c26dc04a269ea0e16cc0aafc8c8ac79f3ec'),
}
def prepare(parent):
    name,digest=ASSETS[platform.system()];root=Path(parent).resolve()/('multiscript-luau-'+VERSION);root.mkdir(parents=True,exist_ok=True)
    archive=root/name
    if archive.is_file():raw=archive.read_bytes()
    else:
        with urllib.request.urlopen('https://github.com/luau-lang/luau/releases/download/'+VERSION+'/'+name,timeout=60) as response:raw=response.read(12_000_001)
    if len(raw)>12_000_000 or hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Official Luau archive digest mismatch')
    archive.write_bytes(raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
        suffix='.exe' if os.name=='nt' else ''
        for file in ('luau'+suffix,'luau-compile'+suffix):
            data=bundle.read(file)
            if len(data)>20_000_000:raise ValueError('Oversized Luau executable')
            target=root/file;target.write_bytes(data);target.chmod(0o755)
    return root/('luau.exe' if os.name=='nt' else 'luau')
if __name__=='__main__':
    executable=prepare(os.environ.get('RUNNER_TEMP',sys.argv[1] if len(sys.argv)>1 else str(Path.home()/'.cache')))
    if os.environ.get('GITHUB_ENV'):
        with open(os.environ['GITHUB_ENV'],'a',encoding='utf-8') as stream:stream.write('LUAU_BIN='+str(executable)+'\n')
    print(executable)
