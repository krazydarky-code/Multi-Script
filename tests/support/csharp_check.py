"""Compile C# against REAL Unity assemblies (UnityEngine.Modules 2021.3 + UnityEditor + UGUI reference DLLs).

Needs the .NET SDK and the reference DLLs; returns None when they are not installed so tests can skip.
Environment: MS_DOTNET (dotnet root, default /tmp/dotnet), MS_UNITY_REFS (folder of Unity DLLs, default /tmp/unity_refs)."""
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net48</TargetFramework>
    <LangVersion>9.0</LangVersion>
    <Nullable>disable</Nullable>
    <EnableDefaultCompileItems>false</EnableDefaultCompileItems>
    <GenerateAssemblyInfo>false</GenerateAssemblyInfo>
    <OutputType>Library</OutputType>
    <NoWarn>CS0618;CS0612;CS0168;CS0219;CS0414;CS0649;CS0169;CS1591;CS8632</NoWarn>
    <ImplicitUsings>disable</ImplicitUsings>
  </PropertyGroup>
  <ItemGroup>
    <Compile Include="src/**/*.cs" />
    <PackageReference Include="Microsoft.NETFramework.ReferenceAssemblies.net48" Version="1.0.3" PrivateAssets="all" />
    <Reference Include="%(refs)s/*.dll" />
  </ItemGroup>
</Project>
"""


def _paths():
    root = Path(os.environ.get("MS_DOTNET", "/tmp/dotnet"))
    refs = Path(os.environ.get("MS_UNITY_REFS", "/tmp/unity_refs"))
    exe = root / "dotnet"
    return (root, exe, refs) if exe.exists() and (refs / "UnityEngine.dll").exists() else None


def available():
    return _paths() is not None


def compile_sources(sources, extra_defines=(), editor=True):
    """sources: {name: csharp text}. UNITY_EDITOR is defined by default (generated editor tasks live inside #if UNITY_EDITOR); pass editor=False for player-build checks. Returns (ok, [error lines]) or None if the toolchain is missing."""
    p = _paths()
    if not p:
        return None
    root, exe, refs = p
    work = Path(tempfile.mkdtemp(prefix="ms_cs_"))
    try:
        (work / "src").mkdir()
        (work / "Check.csproj").write_text(CSPROJ % {"refs": str(refs).replace("\\", "/")}, encoding="utf-8")
        extra_defines = (("UNITY_EDITOR",) if editor else ()) + tuple(extra_defines)
        if extra_defines:
            (work / "Directory.Build.props").write_text('<Project><PropertyGroup><DefineConstants>$(DefineConstants);%s</DefineConstants></PropertyGroup></Project>' % ";".join(extra_defines), encoding="utf-8")
        for name, text in sources.items():
            (work / "src" / (re.sub(r"[^\w.-]", "_", name) + ".cs")).write_text(text, encoding="utf-8")
        env = dict(os.environ, DOTNET_ROOT=str(root), PATH=str(root) + os.pathsep + os.environ.get("PATH", ""),
                   DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1", DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1")
        r = subprocess.run([str(exe), "build", "-nologo", "-v", "q", "-clp:NoSummary"], cwd=work, env=env, capture_output=True, text=True, timeout=240)
        out = (r.stdout or "") + (r.stderr or "")
        errs = sorted({re.sub(r"^.*?src[/\\]", "", ln.split(" [")[0]).strip() for ln in out.splitlines() if re.search(r"error (CS|MSB|NU)\d+", ln)})
        return (r.returncode == 0 and not errs), errs
    finally:
        shutil.rmtree(work, ignore_errors=True)
