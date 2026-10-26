#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build/sign/upload a Dev release, then publish only after asset verification.

Requires normal `gh auth login` (or Actions' GH_TOKEN) and the private signing key
outside the repository. Published versions are immutable to this helper. The
Actions job calls --require-ci and receives no signing key on pull requests.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'runtime'))
from update_manager import verify_envelope,download,version


def run(args,**kwargs):
    return subprocess.run([str(x) for x in args],check=True,**kwargs)


_last_mutation=None
def gh_call(gh,args,*,mutating=False,missing=False):
    """Serial, paced CLI requests. An error stops this run; never replay writes."""
    global _last_mutation
    if mutating and _last_mutation is not None:
        time.sleep(max(0,1.0-(time.monotonic()-_last_mutation)))
    result=subprocess.run([str(gh),*map(str,args)],capture_output=True,text=True,encoding='utf-8',timeout=180)
    if mutating:_last_mutation=time.monotonic()
    if result.returncode:
        detail=(result.stderr+'\n'+result.stdout)[-2000:]
        if missing and ('HTTP 404' in detail or 'release not found' in detail.lower()):return None
        detail=re.sub(r'\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)\b','[redacted]',detail)
        raise RuntimeError('GitHub request failed; publishing stopped without retry. Check sign-in, permissions or GitHub rate-limit/Retry-After notices. '+detail[:800])
    return result


def gh_json(gh,args):
    return json.loads(gh_call(gh,args).stdout)


def get_release(gh,repo,tag):
    r=gh_call(gh,['release','view',tag,'--repo',repo,'--json','apiUrl,isDraft,url,targetCommitish,tagName'],missing=True)
    if r is None:return None
    return json.loads(r.stdout)


def validate_repository(repo,channel):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):
        raise ValueError('Use an exact owner/repository')
    expected=f'https://github.com/{repo}/releases/latest/download/dev-update.json'
    if channel.get('feedUrl')!=expected or not channel.get('publicKey'):
        raise ValueError('Repository must match the pinned, configured public update feed')


def validate_access(repo,repository,environ=None):
    """Actions tokens don't expose the human account's repository role flags.

    A main-branch workflow in this exact public repository can use its scoped
    token; GitHub enforces contents:write on every release mutation. This does
    not relax the independent identity, exact-main or successful-CI checks.
    """
    environ=os.environ if environ is None else environ
    scoped_actions=(environ.get('GITHUB_ACTIONS')=='true' and
                    environ.get('GITHUB_REPOSITORY')==repo and
                    environ.get('GITHUB_REF')=='refs/heads/main' and
                    environ.get('GITHUB_EVENT_NAME') in ('workflow_run','workflow_dispatch'))
    if repository.get('full_name')!=repo or repository.get('private') or not (
            repository.get('permissions',{}).get('push') or scoped_actions):
        raise ValueError('Publishing requires this public repository and an authorized account or its scoped main-branch Actions token')


def verify_assets(metadata,artifacts):
    assets={a['name']:a for a in metadata['assets']}
    for path in artifacts:
        asset=assets.get(path.name)
        if not asset or asset.get('state')!='uploaded' or asset.get('size')!=path.stat().st_size:
            raise ValueError('Missing/incomplete uploaded asset: '+path.name)
        expected='sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()
        if asset.get('digest')!=expected:
            raise ValueError('Uploaded asset hash mismatch: '+path.name)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',required=True)
    p.add_argument('--key',type=Path)
    p.add_argument('--output',type=Path,default=ROOT/'release')
    p.add_argument('--gh',default='gh')
    p.add_argument('--public-archive',type=Path)
    p.add_argument('--require-ci',action='store_true')
    p.add_argument('--check-only',action='store_true',help='Validate identity/main/CI and report release need; never load a signing key or write to GitHub')
    a=p.parse_args()
    cfg=json.loads((ROOT/'runtime/update-channel.json').read_text(encoding='utf-8'))
    validate_repository(a.repo,cfg)
    current=json.loads((ROOT/'extension/manifest.json').read_text(encoding='utf-8'))['version']
    tag='v'+current
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():
        raise ValueError('Publish only a clean, committed source tree')
    repository=gh_json(a.gh,['api',f'repos/{a.repo}'])
    validate_access(a.repo,repository)
    remote=gh_json(a.gh,['api',f'repos/{a.repo}/git/ref/heads/main'])['object']['sha']
    if remote!=head:
        raise ValueError('Only the exact current main commit can publish; checkout main after CI')
    verified_ci=None
    if a.require_ci:
        runs=gh_json(a.gh,['api',f'repos/{a.repo}/actions/workflows/ci.yml/runs?head_sha={head}&event=push&per_page=20'])['workflow_runs']
        verified_ci=next((r for r in runs if r['head_sha']==head and r.get('conclusion')=='success'),None)
        if not verified_ci:
            raise ValueError('Current main must have a successful push CI run before release')
    existing=get_release(a.gh,a.repo,tag)
    if existing and not existing['isDraft']:
        meta=gh_json(a.gh,['api',existing['apiUrl']])
        feed=next((x for x in meta['assets'] if x['name']=='dev-update.json'),None)
        if not feed:raise ValueError('Published version has no signed feed; use a new version instead of overwriting it')
        signed=verify_envelope(json.loads(download(feed['browser_download_url'],32768)),cfg['publicKey'])
        if signed['version']!=current:raise ValueError('Published feed version mismatch')
        print(json.dumps({'published':True,'publish':False,'alreadyPublished':True,'url':existing['url'],'version':current}))
        return
    # Do not move latest backwards if an older commit's workflow finishes late.
    latest=gh_call(a.gh,['api',f'repos/{a.repo}/releases/latest'],missing=True)
    if latest is not None:
        old=json.loads(latest.stdout)['tag_name'].removeprefix('v')
        if re.fullmatch(r'\d+(?:\.\d+){0,3}',old) and version(old)>version(current):
            raise ValueError('A newer release is already latest')
    if a.check_only:
        print(json.dumps({'publish':True,'published':False,'version':current,'commit':head,'repository':a.repo}))
        return
    if not a.key or not a.key.is_file():raise ValueError('An existing private signing key outside this checkout is required')
    a.output.mkdir(parents=True,exist_ok=True)
    policy=json.loads((ROOT/'release-policy.json').read_text(encoding='utf-8'))
    frozen=policy['publicCompanion']
    public=a.public_archive
    if public is None:
        public=a.output/frozen['file']
        if not public.exists():
            with tempfile.TemporaryDirectory(prefix='ms-public-') as temp:
                gh_call(a.gh,['release','download',frozen['sourceRelease'],'--repo',a.repo,'--pattern',frozen['file'],'--dir',temp])
                public.write_bytes((Path(temp)/frozen['file']).read_bytes())
    if hashlib.sha256(public.read_bytes()).hexdigest()!=frozen['sha256']:
        raise ValueError('Frozen Public archive checksum mismatch')
    run([sys.executable,'-X','utf8',ROOT/'tools/build_release.py','--output',a.output,'--public-archive',public],cwd=ROOT)
    dev=a.output/f'Multi-Script-{current}-Dev.zip'
    feed=a.output/'dev-update.json'
    run([sys.executable,ROOT/'tools/sign_update.py','--key',a.key,'--archive',dev,'--archive-url',f'https://github.com/{a.repo}/releases/download/{tag}/{dev.name}','--output',feed],cwd=ROOT)
    signed=verify_envelope(json.loads(feed.read_text()),cfg['publicKey'])
    if signed['sha256']!=hashlib.sha256(dev.read_bytes()).hexdigest():raise ValueError('Signed artifact mismatch')
    artifacts=[dev,a.output/f'Multi-Script-{current}-Bundle.zip',a.output/frozen['file'],feed,a.output/'SHA256SUMS.txt',a.output/f'Multi-Script-{current}-Update-Guide.md',a.output/f'Multi-Script-{current}-Publishing.txt']
    tutorial=a.output/f'Multi-Script-{current}-Discord-Phone-Tutorial.md'
    if tutorial.is_file():artifacts.append(tutorial)
    if verified_ci:
        with tempfile.TemporaryDirectory(prefix='ms-ci-receipt-') as temp:
            gh_call(a.gh,['run','download',str(verified_ci['id']),'--repo',a.repo,'--name','ci-verification','--dir',temp])
            results=json.loads((Path(temp)/'results.json').read_text())
            if not results or any(x['exitCode'] or x['skipped'] for x in results):
                raise ValueError('Upstream CI artifact contains failed or skipped checks')
        receipt=a.output/'CI-verification-results.json'
        receipt.write_text(json.dumps({'commit':head,'run':verified_ci['html_url'],'passed':len(results),'results':results},indent=2)+'\n',encoding='utf-8')
        artifacts.append(receipt)
    notes=ROOT/f'docs/release-notes/RELEASE_NOTES_{current}.md'
    if gh_json(a.gh,['api',f'repos/{a.repo}/git/ref/heads/main'])['object']['sha']!=head:
        raise ValueError('Main moved during the build; nothing was uploaded')
    if not existing:
        gh_call(a.gh,['release','create',tag,'--repo',a.repo,'--draft','--target',head,'--title',f'Multi-Script {current} Dev','--notes-file',notes],mutating=True)
    else:
        gh_call(a.gh,['release','edit',tag,'--repo',a.repo,'--target',head,'--title',f'Multi-Script {current} Dev','--notes-file',notes],mutating=True)
    # Bulk CLI uploads may run concurrent requests. Upload serially and retain
    # already verified assets when resuming a draft.
    for artifact in artifacts:
        draft=get_release(a.gh,a.repo,tag)
        if not draft or not draft['isDraft']:raise ValueError('Release is no longer a draft; uploads stopped')
        metadata=gh_json(a.gh,['api',draft['apiUrl']])
        try:verify_assets(metadata,[artifact]);continue
        except ValueError:pass
        gh_call(a.gh,['release','upload',tag,artifact,'--repo',a.repo,'--clobber'],mutating=True)
    # GitHub does not expose an untagged draft at /releases/tags/<version>.
    # Resolve its stable release API URL through gh's draft-aware lookup.
    draft=get_release(a.gh,a.repo,tag)
    if not draft:raise ValueError('Draft disappeared before verification')
    metadata=gh_json(a.gh,['api',draft['apiUrl']])
    if not metadata['draft']:raise ValueError('Release changed out of draft during upload; refusing publish')
    verify_assets(metadata,artifacts)
    if gh_json(a.gh,['api',f'repos/{a.repo}/git/ref/heads/main'])['object']['sha']!=head:
        raise ValueError('Main moved during upload; the draft remains unpublished')
    gh_call(a.gh,['release','edit',tag,'--repo',a.repo,'--draft=false','--latest'],mutating=True)
    print(json.dumps({'published':True,'url':f'https://github.com/{a.repo}/releases/tag/{tag}','version':current,'sha256':signed['sha256']}))


if __name__=='__main__':main()
