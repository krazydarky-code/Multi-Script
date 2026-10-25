# SPDX-License-Identifier: GPL-3.0-or-later
"""Multi-Script Forge, bridge side (standard library only).

The browser extension draws the art with the built-in Canvas (extension/core/forge.js) and sends
the PNGs here. This module stores them under runtime/generated/forge/<name>/, serves them on a
127.0.0.1 address (Studio's upload_image takes http paths), reads a local reference picture for
the extension, and writes the Luau builders (ForgeKit for UI, ForgeVFX for effects) once Studio
has returned the uploaded asset ids. The Luau templates live in forge_luau.py.
"""
from pathlib import Path
import base64, http.server, json, re, secrets, threading
from forge_luau import UI_LUAU, VFX_LUAU, UI_USAGE, VFX_USAGE

HERE = Path(__file__).resolve().parent
OUT = HERE / 'generated' / 'forge'
MAX_FILE = 8 * 1024 * 1024
STYLES = ['simulator', 'cartoon', 'glossy', 'candy', 'anime', 'glass', 'neon', 'fantasy', 'scifi', 'minimal', 'horror', 'pixel']

# ------------------------------------------------------------------ localhost file server
_SRV = {}
_SAVE_LOCK = threading.RLock()
def _serve():
    if _SRV: return _SRV['base']
    token = secrets.token_hex(8)
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            parts = self.path.split('?')[0].strip('/').split('/')
            if len(parts) != 3 or parts[0] != token or not re.fullmatch(r'[A-Za-z0-9._-]+', parts[1]) or not re.fullmatch(r'[A-Za-z0-9._-]+\.png', parts[2]):
                self.send_error(404); return
            f = (OUT / parts[1] / parts[2]).resolve()
            if not f.is_relative_to(OUT.resolve()) or not f.is_file(): self.send_error(404); return
            data = f.read_bytes()
            self.send_response(200); self.send_header('Content-Type', 'image/png'); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _SRV.update(base=f'http://127.0.0.1:{srv.server_address[1]}/{token}', srv=srv)
    return _SRV['base']

def _safe(s, default=''):
    s = re.sub(r'[^A-Za-z0-9._-]+', '-', str(s or '')).strip('-.')[:60]
    return s or default

def _png(b64):
    if not isinstance(b64, str) or len(b64) > (MAX_FILE + 2) // 3 * 4:
        raise ValueError('Files must be base64 PNG data under 8 MB.')
    try: data = base64.b64decode(b64, validate=True)
    except Exception: raise ValueError('Files must be base64 PNG data.')
    if data[:8] != b'\x89PNG\r\n\x1a\n': raise ValueError('Only PNG files are stored.')
    if len(data) > MAX_FILE: raise ValueError('A file is larger than 8 MB.')
    return data

def _manifest_path(name): return OUT / name / 'manifest.json'

# ------------------------------------------------------------------ actions
def act_save(args):
    with _SAVE_LOCK:
        return _act_save(args)

def _act_save(args):
    """Called by the extension after it drew a set. part=first|more|last lets big sets arrive in batches."""
    name = _safe(args.get('name'))
    if not name: raise ValueError('name is required')
    files = args.get('files') or {}
    if not isinstance(files, dict): raise ValueError('files is {key: base64 png}')
    d = OUT / name
    if not d.resolve().is_relative_to(OUT.resolve()) or d.is_symlink():
        raise ValueError('Forge output must stay inside its generated folder.')
    part = args.get('part', 'only')
    if part not in ('first', 'only', 'more', 'last'):
        raise ValueError('Unknown Forge batch part.')
    if len(files) > 64:
        raise ValueError('Send at most 64 images per batch.')
    decoded={}
    for key,b64 in files.items():
        if not isinstance(key,str) or _safe(key)!=key:
            raise ValueError('Invalid Forge image key.')
        decoded[key]=_png(b64)
    preview=_png(args['preview']) if args.get('preview') else None
    if sum(map(len,decoded.values()))+(len(preview) if preview else 0)>32*1024*1024:
        raise ValueError('Send at most 32 MB per batch.')
    # A new generation never deletes an earlier set. Retry identical batches
    # safely, but refuse to replace different bytes under an existing key.
    if part in ('first','only') and d.is_dir() and any(d.iterdir()):
        raise ValueError('This Forge set already exists; choose a new generation name.')
    if part in ('more','last') and not (d/'.forge-generation').is_file():
        raise ValueError('Start this Forge generation with first before adding batches.')
    for key,data in decoded.items():
        target=d/(key+'.png')
        if target.is_symlink() or not target.resolve().is_relative_to(OUT.resolve()):
            raise ValueError('Forge images cannot be links outside the generated folder.')
        if target.exists() and target.read_bytes()!=data:
            raise ValueError('Refusing to replace an existing Forge image: '+key)
    d.mkdir(parents=True, exist_ok=True)
    (d/'.forge-generation').write_text('Multi-Script Forge generation\n',encoding='utf-8')
    base = _serve()
    for key,data in decoded.items():
        (d / f'{key}.png').write_bytes(data)
    if preview: (d / '_preview.png').write_bytes(preview)
    if part in ('first', 'more'):
        return {'text': json.dumps({'ok': True, 'stored': len(files)}), 'images': []}
    manifest = args.get('manifest') or {}
    if not isinstance(manifest, dict) or manifest.get('type') not in ('ui_kit', 'vfx', 'backdrop'): raise ValueError('manifest.type must be ui_kit, vfx or backdrop')
    manifest['name'] = name
    entries = manifest.get('elements') or manifest.get('textures') or manifest.get('files') or {}
    missing = []
    for key, e in entries.items():
        if not isinstance(key,str) or _safe(key)!=key or not isinstance(e,dict):
            raise ValueError('Invalid Forge manifest image entry.')
        f = d / f'{key}.png'
        if not f.is_file(): missing.append(key); continue
        e['file'] = str(f); e['url'] = f'{base}/{name}/{key}.png'; e['bytes'] = f.stat().st_size
    _manifest_path(name).write_text(json.dumps(manifest, indent=1))
    return _brief(name, manifest, missing)

def _brief(name, manifest, missing=(), extra=None):
    d = OUT / name
    entries = manifest.get('elements') or manifest.get('textures') or manifest.get('files') or {}
    brief = {'name': name, 'type': manifest['type'], 'count': len(entries), 'missing': list(missing), 'folder': str(d),
             'urls': [e['url'] for e in entries.values() if 'url' in e]}
    if manifest['type'] == 'ui_kit':
        brief['theme'] = manifest.get('theme'); brief['elements'] = sorted(entries)
    elif manifest['type'] == 'vfx':
        brief['textures'] = {k: {'kind': e.get('kind'), 'layout': e.get('layout')} for k, e in entries.items()}
        brief['presets'] = list((manifest.get('presets') or {}).keys())
        brief['note'] = 'White on transparent: tint with Color, LightEmission 1 to glow. Flipbooks are 1024x1024, which Roblox requires.'
    else:
        brief['note'] = 'Thumbnails: 16:9, 1920x1080, under 3 MB. Put the title in as real text.'
    if extra:
        brief.update(extra)
        inst = extra.get('install') or {}
        if inst.get('installed') and manifest['type'] == 'ui_kit':
            brief['next'] = 'Use the reported module '+str(inst.get('module',''))+' from a LocalScript for the requested screens. Verify actual wiring, asset loading and appearance in Studio.'
            if inst.get('demoVerified') and inst.get('demo'):brief['next']+=' Preview creation was reported at '+str(inst['demo'])+'; capture and inspect it. Preserve other scenes.'
        elif inst.get('installed') and manifest['type'] == 'vfx':
            brief['next'] = 'Use the reported module '+str(inst.get('module',''))+' from client scripts (burst, combo, attach, stop, trail, beam). Verify actual appearance, asset loading, cancellation and budget in Studio.'
        elif inst.get('installed'):
            brief['next'] = 'Uploaded. Use the asset id in an ImageLabel (ScaleType Crop) or as a thumbnail.'
        else:
            brief['next'] = NEXT
        brief.pop('urls', None) if inst.get('installed') else None
    else:
        brief['next'] = NEXT
    images = []
    pv = d / '_preview.png'
    if pv.is_file() and pv.stat().st_size < 4 * 1024 * 1024: images = [{'data': base64.b64encode(pv.read_bytes()).decode(), 'mimeType': 'image/png'}]
    return {'text': json.dumps(brief), 'images': images}

def act_report(args):
    name = _safe(args.get('name'))
    mp = _manifest_path(name)
    if not name or not mp.is_file(): raise ValueError('Unknown forge set.')
    try: extra = json.loads(args.get('report') or '{}')
    except Exception: extra = {}
    result=_brief(name, json.loads(mp.read_text()), (), extra if isinstance(extra, dict) else {})
    payload=json.loads(result['text']);payload['reportPolicy']='Installation fields are a caller-supplied summary. The real Studio execution/readback receipt, not this report action, is the installation evidence; runtime appearance and behavior remain separate checks.'
    result['text']=json.dumps(payload)
    return result

def act_reference(args):
    p = Path(str(args.get('path') or '')).expanduser()
    if not p.is_file(): raise ValueError('reference_image must be a path to a PNG or JPG on this computer.')
    if p.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'): raise ValueError('reference_image must be PNG, JPG or WEBP.')
    data = p.read_bytes()
    if len(data) > 12 * 1024 * 1024: raise ValueError('reference_image is larger than 12 MB.')
    return {'text': json.dumps({'data': base64.b64encode(data).decode()}), 'images': []}

def act_bind(args):
    name = _safe(args.get('name'))
    mp = _manifest_path(name)
    if not name or not mp.is_file(): raise ValueError('Unknown forge set; give the name used when it was made (action=list shows them).')
    manifest = json.loads(mp.read_text())
    amap = args.get('asset_map') or {}
    if not isinstance(amap, dict) or not amap: raise ValueError('asset_map is what Studio upload_image returned: {url: "rbxassetid://..."} (or {file name: id} after a manual import).')
    entries = manifest.get('elements') or manifest.get('textures') or {}
    by_key = {}
    for key, e in entries.items():
        for src in (e.get('url'), e.get('file'), key, key + '.png'):
            if src in amap: by_key[key] = str(amap[src]).strip(); break
    for k, v in list(by_key.items()):
        if re.fullmatch(r'\d+', v): by_key[k] = v = 'rbxassetid://' + v
        if not re.fullmatch(r'rbxassetid://\d+', v): raise ValueError('Asset ids look like rbxassetid://123456; got ' + v)
    missing = [k for k in entries if k not in by_key]
    if manifest['type'] == 'ui_kit': src, module = ui_luau(manifest, by_key), 'ForgeKit'
    elif manifest['type'] == 'vfx': src, module = vfx_luau(manifest, by_key), 'ForgeVFX'
    else: raise ValueError('Backdrops have no builder; use the id directly in an ImageLabel or as a thumbnail.')
    manifest['assets'] = by_key; mp.write_text(json.dumps(manifest, indent=1))
    usage = UI_USAGE if module == 'ForgeKit' else VFX_USAGE
    return {'text': json.dumps({'module': module, 'bound': len(by_key), 'missing': missing, 'source': src, 'example': usage,
                                'place': 'ReplicatedStorage', 'note': 'Write source as a ModuleScript named ' + module + ' in ReplicatedStorage; require it from a LocalScript.'}), 'images': []}

def act_list(_args):
    sets = []
    if OUT.is_dir():
        for mp in sorted(OUT.glob('*/manifest.json')):
            try: m = json.loads(mp.read_text())
            except Exception: continue
            sets.append({'name': m.get('name'), 'type': m.get('type'), 'items': len(m.get('elements') or m.get('textures') or m.get('files') or {}), 'bound': len(m.get('assets') or {})})
    return {'text': json.dumps({'sets': sets, 'folder': str(OUT)}), 'images': []}

NEXT = ('Next: (1) look at the preview; remake with other colours or tweaks if anything is off; (2) upload with the Roblox Studio upload_image tool, imagePaths = the urls '
        '(served from this computer while the bridge runs); (3) call ms_forge action=bind with this name and asset_map = what upload_image returned; '
        '(4) write the returned source as a ModuleScript in ReplicatedStorage and build the real UI or effects with it; (5) play-test and screen_capture. '
        'Without Studio upload: import the files in Studio (Asset Manager > Bulk Import) and pass {file name: id} to bind.')

def call(args):
    args = args or {}
    action = str(args.get('action') or 'list')
    if action == 'save': return act_save(args)
    if action == 'bind': return act_bind(args)
    if action == 'list': return act_list(args)
    if action == 'reference': return act_reference(args)
    if action == 'report': return act_report(args)
    if action == 'styles':
        return {'text': json.dumps({'styles': STYLES, 'note': 'Drawing happens in the Multi-Script browser extension; actions ui_kit, vfx and backdrop run there.'}), 'images': []}
    if action in ('ui_kit', 'vfx', 'backdrop'):
        raise ValueError('Forge drawing runs in the Multi-Script browser extension. Call ms_forge from the chat with the extension active.')
    raise ValueError('action is one of ui_kit, vfx, backdrop, bind, list, styles.')

TOOL = {"name": "ms_forge", "description": "Forge: makes real game art and installs it as working Roblox UI or effects in ONE call. "
        "When Roblox Studio is connected, action ui_kit / vfx / backdrop draws selected art, uploads it with Studio and writes a uniquely named ModuleScript (ForgeKit_<generation> or ForgeVFX_<generation>). Existing artwork/modules are preserved. Only demo=true creates a fresh preview; install=false only saves local files. Returned asset IDs do not prove moderation, ownership or runtime loading. "
        "ui_kit {name, style: simulator|cartoon|glossy|candy|anime|glass|neon|fantasy|scifi|minimal|horror|pixel, pack: essentials|hud|shop|inventory|settings|leaderboard|dialogue|rewards|full (default essentials; full explicitly selects everything), elements:[prefixes], colors:{primary,secondary,success,danger,panel,panel2,accent,text}, reference_image: PNG/JPG path for a palette, tweaks:{radius,ow,lip,gloss,shadow,glow}}. Draws only selected elements and keeps their complete states. "
        "ForgeKit API: Kit.screen, Kit.modal, Kit.panel, Kit.button, Kit.iconButton, Kit.grid, Kit.list, Kit.card, Kit.slot, Kit.bar (progress, xp, hp, mana), Kit.pill, Kit.priceTag, Kit.toggle, Kit.checkbox, Kit.radio, Kit.slider, Kit.input, Kit.tabs, Kit.badge, Kit.bubble, Kit.leaderboardRow, Kit.toast, Kit.tooltip, Kit.reward (rays pop-up), Kit.billboard (name tag and health over a character), Kit.loading, Kit.icon (30 icons). "
        "vfx {name, textures:[...]}: 27 particle textures, 6 trail/beam strips, 8 flipbooks (1024x1024) and 27 presets; ForgeVFX API: VFX.burst, VFX.combo, VFX.attach, VFX.stop, VFX.trail, VFX.beam. "
        "backdrop {style, kind: burst|clouds|space|dungeon|sparkles|stripes|grid|sunset, use: thumbnail|ingame}. bind {name, asset_map} and list are for manual installs.",
        "inputSchema": {"type": "object", "properties": {
            "action": {"type": "string", "enum": ["ui_kit", "vfx", "backdrop", "bind", "list", "styles", "save", "reference", "report"]},
            "name": {"type": "string"}, "style": {"type": "string"}, "colors": {"type": "object", "additionalProperties": {"type": "string"}},
            "reference_image": {"type": "string"}, "tweaks": {"type": "object", "additionalProperties": {"type": "number"}},
            "elements": {"type": "array", "items": {"type": "string"}}, "icons": {"type": "array", "items": {"type": "string"}}, "icon_colors": {"type": "object", "additionalProperties": {"type": "string"}},
            "textures": {"type": "array", "items": {"type": "string"}}, "kind": {"type": "string"}, "use": {"type": "string"}, "seed": {"type": "integer"},
            "asset_map": {"type": "object", "additionalProperties": {"type": "string"}},
            "files": {"type": "object", "additionalProperties": {"type": "string"}, "description": "internal: sent by the extension"},
            "manifest": {"type": "object", "description": "internal: sent by the extension"}, "preview": {"type": "string", "description": "internal"},
            "part": {"type": "string", "description": "internal"}, "path": {"type": "string", "description": "internal"}, "report": {"type": "string", "description": "internal"},
            "pack": {"type": "string"}, "install": {"type": "boolean"}, "demo": {"type": "boolean"}, "module": {"type": "string"}, "studio_id": {"type": "string"}},
            "required": ["action"], "additionalProperties": False}}

# ------------------------------------------------------------------ Luau
def lua_value(v, indent='\t'):
    if isinstance(v, dict):
        if not v: return '{}'
        items = []
        for k in sorted(v):
            key = k if re.fullmatch(r'[A-Za-z_]\w*', k) else '[' + json.dumps(k) + ']'
            items.append(f'{indent}{key} = {lua_value(v[k], indent + chr(9))},')
        return '{\n' + '\n'.join(items) + '\n' + indent[:-1] + '}'
    if isinstance(v, (list, tuple)): return '{' + ', '.join(lua_value(x, indent) for x in v) + '}'
    if isinstance(v, bool): return 'true' if v else 'false'
    if isinstance(v, float): return repr(round(v, 4))
    if isinstance(v, int): return str(v)
    if v is None: return 'nil'
    return json.dumps(str(v))

def ui_luau(manifest, assets):
    th = manifest.get('theme') or {}
    slices = {k: v['slice'] for k, v in manifest['elements'].items() if v.get('slice')}
    font = th.get('font') or 'Enum.Font.FredokaOne'
    if not re.fullmatch(r'Enum\.Font\.[A-Za-z]+', font): font = 'Enum.Font.FredokaOne'
    hexok = lambda s, d: s if isinstance(s, str) and re.fullmatch(r'#[0-9a-fA-F]{6}', s) else d
    pal = th.get('palette') or {}
    return (UI_LUAU.replace('__STYLE__', _safe(th.get('style'), 'custom')).replace('__ASSETS__', lua_value({k: assets.get(k, '') for k in manifest['elements']}))
            .replace('__SLICES__', lua_value(slices)).replace('__FONT__', font).replace('__TEXT__', hexok(th.get('text'), '#ffffff'))
            .replace('__STROKE__', hexok(th.get('textStroke'), '#10203a')).replace('__ACCENT__', hexok(pal.get('accent'), '#ffe14d')))

def _preset_lua(p):
    out = {'Texture': p['tex'], 'Color': p['color'], 'Lifetime': list(p['lifetime']), 'Speed': list(p['speed']), 'Size': [list(x) for x in p['size']],
           'Transparency': [list(x) for x in p['transp']], 'LightEmission': p.get('light', 0)}
    for a, b in (('emit', 'Emit'), ('rate', 'Rate'), ('drag', 'Drag'), ('orient', 'Orientation')):
        if a in p: out[b] = p[a]
    for a, b in (('spread', 'Spread'), ('rot', 'Rotation'), ('rotspeed', 'RotSpeed'), ('accel', 'Acceleration'), ('flip', 'Flipbook'), ('framerate', 'Framerate')):
        if a in p: out[b] = list(p[a])
    return out

def vfx_luau(manifest, assets):
    presets = {k: _preset_lua(v) for k, v in (manifest.get('presets') or {}).items() if v.get('tex') in manifest['textures']}
    return VFX_LUAU.replace('__TEXTURES__', lua_value({k: assets.get(k, '') for k in manifest['textures']})).replace('__PRESETS__', lua_value(presets))
