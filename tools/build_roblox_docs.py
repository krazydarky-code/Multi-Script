# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the offline Roblox + Luau documentation library used by ms_roblox_docs.

Sources (clone them first, then run this script):
  git clone --depth 1 https://github.com/Roblox/creator-docs.git   (CC-BY-4.0 docs, MIT code)
  git clone --depth 1 https://github.com/luau-lang/site.git         (MIT)

  python tools/build_roblox_docs.py --creator-docs ../creator-docs --luau-site ../site

Needs PyYAML at build time only. The runtime reader uses the standard library.
"""
import argparse, gzip, json, re, shutil, subprocess, time
from pathlib import Path

OUT_DEFAULT = Path(__file__).resolve().parent.parent / 'runtime' / 'skill-resources' / 'roblox-docs'
SHARD_CHARS = 1_500_000

def inline_includes(text, path, depth=0):
    imports = dict(re.findall(r"^import (\w+) from ['\"]([^'\"]+\.md)['\"]", text, flags=re.M))
    for name, rel in imports.items():
        f = (path.parent / rel).resolve()
        body = ''
        if f.is_file() and depth < 3:
            body = inline_includes(f.read_text(encoding='utf-8', errors='replace'), f, depth + 1)
            body = re.sub(r'^---\n.*?\n---\n', '', body, flags=re.S)
        text = re.sub(r'<' + name + r'(\s[^<>]*)?/>', lambda m: body, text)
    return text

def clean_md(text, path=None):
    text = text.replace('\r\n', '\n')
    if path is not None: text = inline_includes(text, path)
    meta = {}
    m = re.match(r'^---\n(.*?)\n---\n', text, re.S)
    if m:
        for line in m.group(1).split('\n'):
            k, _, v = line.partition(':')
            if v.strip() and not line.startswith(' '):
                meta[k.strip()] = v.strip().strip('"\'')
        text = text[m.end():]
    parts = re.split(r'(```.*?```)', text, flags=re.S)
    out = []
    for i, p in enumerate(parts):
        if i % 2:
            out.append(p)
            continue
        p = re.sub(r'<!--.*?-->', '', p, flags=re.S)
        p = re.sub(r'<img[^>]*>', '', p)
        p = re.sub(r'<video[^>]*>.*?</video>', '', p, flags=re.S)
        p = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', p)
        p = re.sub(r'</?[A-Za-z][A-Za-z0-9]*(\s[^<>]*)?/?>', '', p)
        p = ref_text(p)
        p = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', p)
        p = re.sub(r'^import .*$', '', p, flags=re.M)
        p = re.sub(r'^[ \t]+', '', p, flags=re.M)
        p = re.sub(r'[ \t]+$', '', p, flags=re.M)
        p = re.sub(r'\n{3,}', '\n\n', p)
        out.append(p)
    return meta, ''.join(out).strip()

def ref_text(s):
    # `Class.Tween|Tweens` -> `Tweens`; `Class.TweenService:Create()` -> `TweenService:Create()`
    s = re.sub(r'`(?:Class|Enum|Datatype|Global|Library)\.([^`|]+)\|([^`]+)`', r'`\2`', s)
    s = re.sub(r'`(?:Class|Enum|Datatype|Global|Library)\.([^`]+)`', r'`\1`', s)
    return s

def heads(text):
    return [h.strip('# ').strip() for h in re.findall(r'^#{2,3} .+$', text, flags=re.M)][:40]

def tagstr(item):
    tags = [t for t in (item.get('tags') or []) if isinstance(t, str)]
    if item.get('deprecation_message'):
        tags = sorted(set(tags + ['Deprecated']))
    sec = item.get('security')
    if isinstance(sec, dict):
        r, w = sec.get('read'), sec.get('write')
        if r and r != 'None': tags.append('read:' + r)
        if w and w != 'None' and w != r: tags.append('write:' + w)
    elif isinstance(sec, str) and sec != 'None':
        tags.append('security:' + sec)
    ts = item.get('thread_safety')
    if ts and ts != 'Unsafe': tags.append('thread:' + ts)
    return tags

def one(s):
    return re.sub(r'\s+', ' ', ref_text(str(s or ''))).strip()

def sig(m):
    ps = ', '.join(f"{p.get('name')}: {((p.get('type') or '') if isinstance(p.get('type'), str) else '')}" + (f" = {p.get('default')}" if p.get('default') not in (None, '') else '') for p in (m.get('parameters') or []))
    rs = ', '.join(str(r.get('type')) for r in (m.get('returns') or []) if r.get('type')) or '()'
    return f"{m.get('name')}({ps}) -> {rs}"

def api_doc(y, kind, rel):
    name = y.get('name')
    lines, members = [], []
    head = f"{kind} {name}"
    if y.get('inherits'): head += ' : ' + ', '.join(y['inherits'])
    lines.append(head)
    t = tagstr(y)
    if t: lines.append('Tags: ' + ', '.join(t))
    if y.get('deprecation_message'): lines.append('DEPRECATED: ' + one(y['deprecation_message']))
    lines.append(one(y.get('summary')))
    if y.get('description'): lines.append('\n' + ref_text(str(y['description'])).strip())
    groups = [('Properties', 'properties'), ('Methods', 'methods'), ('Functions', 'functions'), ('Events', 'events'),
              ('Callbacks', 'callbacks'), ('Constructors', 'constructors'), ('Constants', 'constants'), ('Items', 'items'), ('Math operations', 'math_operations')]
    for title, key in groups:
        items = y.get(key) or []
        if not items: continue
        lines.append(f'\n## {title}')
        for it in items:
            if not isinstance(it, dict): continue
            nm = it.get('name') or ''
            if key in ('methods', 'functions', 'callbacks', 'constructors'):
                label = sig(it)
            elif key == 'events':
                label = f"{nm}({', '.join(str(p.get('name')) + ': ' + str(p.get('type')) for p in (it.get('parameters') or []))})"
            elif key == 'items':
                label = f"{nm} = {it.get('value')}"
            elif key == 'math_operations':
                label = f"{it.get('type_a')} {it.get('operation')} {it.get('type_b')} -> {it.get('return_type')}"
                nm = label
            else:
                label = f"{nm}: {it.get('type')}" + (f" (default {it.get('default')})" if it.get('default') not in (None, '') else '')
            tg = tagstr(it)
            depr = 'Deprecated' in tg
            lines.append(f"- {label}" + (f" [{', '.join(tg)}]" if tg else ''))
            s = one(it.get('summary'))
            if s: lines.append('  ' + s)
            if it.get('deprecation_message'): lines.append('  Deprecated: ' + one(it['deprecation_message']))
            d = one(it.get('description'))
            if d and d != s and len(d) > len(s) + 20: lines.append('  ' + d[:1600])
            short = nm.split(':')[-1].split('.')[-1] if key not in ('math_operations',) else nm
            members.append({'n': short, 'k': key, 'd': depr, 's': s[:200], 'sig': label[:240], 'why': one(it.get('deprecation_message'))[:220] if depr else ''})
    text = '\n'.join(l for l in lines if l is not None).strip()
    url = 'https://create.roblox.com/docs/reference/engine/' + rel
    return {'kind': kind.lower(), 'title': name, 'url': url, 'summary': one(y.get('summary'))[:300],
            'deprecated': bool(y.get('deprecation_message')) or 'Deprecated' in (y.get('tags') or []),
            'inherits': y.get('inherits') or [], 'members': members, 'text': text,
            'headings': [m['n'] for m in members][:400]}

def build(cd, ls, out):
    import yaml
    docs = []
    en = cd / 'content' / 'en-us'
    for p in sorted(en.rglob('*.md')):
        rel = p.relative_to(en).as_posix()
        if rel.startswith('includes/') or rel.endswith('README.md'): continue
        meta, text = clean_md(p.read_text(encoding='utf-8', errors='replace'), p)
        if len(text) < 80: continue
        slug = rel[:-3]
        if slug.endswith('/index'): slug = slug[:-6]
        docs.append({'kind': 'guide', 'title': meta.get('title') or slug.split('/')[-1], 'url': 'https://create.roblox.com/docs/' + slug,
                     'summary': one(meta.get('description'))[:300], 'deprecated': False, 'headings': heads(text), 'text': text, 'section': slug.split('/')[0]})
    ref = en / 'reference' / 'engine'
    kinds = {'classes': 'Class', 'datatypes': 'Datatype', 'enums': 'Enum', 'globals': 'Global', 'libraries': 'Library'}
    for folder, kind in kinds.items():
        for p in sorted((ref / folder).glob('*.yaml')):
            try: y = yaml.safe_load(p.read_text(encoding='utf-8'))
            except Exception as e: print('skip', p, e); continue
            if not isinstance(y, dict) or not y.get('name'): continue
            d = api_doc(y, kind, f"{folder}/{p.stem}")
            d['section'] = 'reference'
            docs.append(d)
    cloud = en / 'reference' / 'cloud'
    for p in sorted(cloud.rglob('*.yaml')) + sorted(cloud.rglob('*.json')):
        pass  # Open Cloud OpenAPI specs are large machine specs; the cloud guides above cover usage.
    if ls:
        base = ls / 'src' / 'content'
        for p in sorted(base.rglob('*.md')) + sorted(base.rglob('*.mdx')):
            rel = p.relative_to(base).as_posix()
            meta, text = clean_md(p.read_text(encoding='utf-8', errors='replace'))
            if len(text) < 80: continue
            slug = meta.get('slug') or rel.rsplit('.', 1)[0].replace('docs/', '', 1)
            docs.append({'kind': 'luau-news' if rel.startswith('news/') else 'luau', 'title': meta.get('title') or slug, 'url': 'https://luau.org/' + slug.strip('/'),
                         'summary': one(meta.get('description'))[:300], 'deprecated': False, 'headings': heads(text), 'text': text, 'section': 'luau'})
    if out.exists(): shutil.rmtree(out)
    out.mkdir(parents=True)
    index, shard, size, n = [], [], 0, 0
    def flush():
        nonlocal shard, size, n
        if not shard: return
        with gzip.open(out / f'docs-{n:03d}.jsonl.gz', 'wt', encoding='utf-8', compresslevel=9) as f:
            for d in shard: f.write(json.dumps(d, ensure_ascii=False) + '\n')
        shard, size, n = [], 0, n + 1
    for i, d in enumerate(docs):
        d['id'] = i
        index.append({'id': i, 'k': d['kind'], 't': d['title'], 'u': d['url'], 's': d['summary'], 'h': d['headings'][:60] if d['kind'] == 'guide' or d['kind'].startswith('luau') else [],
                      'dep': d['deprecated'], 'sh': n, 'c': len(d['text']), 'sec': d.get('section', '')})
        shard.append(d); size += len(d['text'])
        if size > SHARD_CHARS: flush()
    flush()
    api = {k: {} for k in ('class', 'datatype', 'enum', 'global', 'library')}
    for d in docs:
        if d['kind'] in api:
            api[d['kind']][d['title']] = {'id': d['id'], 'k': d['kind'], 'dep': d['deprecated'], 'inh': d.get('inherits', []), 'm': {m['n']: [m['k'][0], int(m['d']), m['sig']] + ([m['why']] if m['why'] else []) for m in d['members']}, 'why': one(d['text'].split('DEPRECATED: ', 1)[1].split('\n', 1)[0])[:220] if 'DEPRECATED: ' in d['text'] else ''}
    with gzip.open(out / 'index.json.gz', 'wt', encoding='utf-8', compresslevel=9) as f: json.dump(index, f, ensure_ascii=False, separators=(',', ':'))
    with gzip.open(out / 'api.json.gz', 'wt', encoding='utf-8', compresslevel=9) as f: json.dump(api, f, ensure_ascii=False, separators=(',', ':'))
    def rev(path):
        try: return subprocess.check_output(['git', '-C', str(path), 'log', '-1', '--format=%H %cI'], text=True).strip()
        except Exception: return 'unknown'
    src = {'built': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'creator_docs': rev(cd), 'luau_site': rev(ls) if ls else None,
           'studio_version': (ref / 'STUDIO_VERSION').read_text().strip().split('\n')[0] if (ref / 'STUDIO_VERSION').exists() else None,
           'counts': {k: sum(1 for d in docs if d['kind'] == k) for k in sorted({d['kind'] for d in docs})}, 'total': len(docs),
           'licenses': {'creator-docs text': 'CC-BY-4.0 (Roblox Corporation)', 'creator-docs code': 'MIT (Roblox Corporation)', 'luau.org site': 'MIT (Roblox Corporation)'}}
    (out / 'SOURCE.json').write_text(json.dumps(src, indent=2))
    shutil.copy(cd / 'LICENSE', out / 'LICENSE-creator-docs-CC-BY-4.0')
    shutil.copy(cd / 'LICENSE-CODE', out / 'LICENSE-creator-docs-code-MIT')
    if ls and (ls / 'LICENSE.md').exists(): shutil.copy(ls / 'LICENSE.md', out / 'LICENSE-luau-site-MIT')
    (out / 'NOTICE.md').write_text('# Offline Roblox and Luau documentation\n\nText from Roblox Creator Documentation (https://github.com/Roblox/creator-docs), (c) Roblox Corporation, licensed CC-BY-4.0; code in it is MIT. Luau documentation from https://github.com/luau-lang/site, (c) Roblox Corporation, MIT. Converted to plain text by tools/build_roblox_docs.py: front matter, images and page components removed, links reduced to their text. Not endorsed by Roblox.\n')
    return src

if __name__ == '__main__':
    a = argparse.ArgumentParser()
    a.add_argument('--creator-docs', required=True, type=Path)
    a.add_argument('--luau-site', type=Path)
    a.add_argument('--out', type=Path, default=OUT_DEFAULT)
    x = a.parse_args()
    print(json.dumps(build(x.creator_docs.resolve(), x.luau_site.resolve() if x.luau_site else None, x.out), indent=2))
