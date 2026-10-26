# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded OMNI reference queries and an opt-in, namespaced native Luau kit.

No catalogue/PDF enters startup prompts. Source designs are not live evidence.
"""
from functools import lru_cache
from pathlib import Path
import gzip, hashlib, json, re, uuid

HERE=Path(__file__).resolve().parent/'skill-resources'/'omni-gui'
MODULES=('Maid','Signal','Spring','Tokens','ThemeRegistry','Toolkit')
PDF_SHA='c10c86d39ea24e4ede9d1cba60c1f3862a11604d48b234bad7f5b5ae40e5d8ef'
POLICY='Reference screenshots and approximate tokens are design evidence only, not current project verification, asset permissions or reusable game imagery. Preserve the project style and use real engine readback/playtests.'
TOOL={'name':'ms_roblox_omni','description':'Query the compact OMNI UI/VFX/animation reference library, analyze relevant style, read reviewed modules, or explicitly install a namespaced native UI/cleanup/spring kit in connected Roblox Studio. Does not create combat/remotes, replace existing skills, or claim screenshots as playtests. Install performs a real engine call; bundle only returns source.', 'inputSchema':{'type':'object','additionalProperties':False,'required':['action'],'properties':{'action':{'type':'string','enum':['references','analyze','modules','bundle','install']},'query':{'type':'string','maxLength':1000},'style':{'type':'string','maxLength':80},'id':{'type':'string','maxLength':80},'limit':{'type':'integer','minimum':1,'maximum':8,'default':4},'module':{'type':'string','enum':list(MODULES)},'offset':{'type':'integer','minimum':0,'maximum':100000},'max_chars':{'type':'integer','minimum':1000,'maximum':16000},'namespace':{'type':'string','pattern':'^[A-Za-z][A-Za-z0-9_]{0,59}$'},'studio_id':{'type':'string'}}}}

@lru_cache(maxsize=1)
def catalog():
    with gzip.open(HERE/'catalog.json.gz','rt',encoding='utf-8') as f:return json.load(f)

TOOL['inputSchema']['properties']['action']['enum'].append('recipe')
TOOL['inputSchema']['properties']['recipe']={'type':'string','enum':['ui','vfx','pose','composite']}
TOOL['inputSchema']['properties']['action']['enum']+=['status','packages','context','preview']
TOOL['inputSchema']['properties']['project']={'type':'string','pattern':'^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$','default':'default'}

def inventory():
    import obsidian_vault as vault
    state=vault.status();pdf=None
    if state['available']:
        candidate=vault._path(vault._root(),'Attachments/'+PDF_SHA+'.pdf')
        if candidate.is_file():pdf=candidate
    packages=[{'id':'native-ui-kit','kind':'reviewed Luau source','modules':list(MODULES),'read':{'action':'modules'},'install':'Explicit live Studio install; no automatic project writes.'}]
    for kind in ('ui','vfx','pose','composite'):
        packages.append({'id':kind+'-recipes','kind':'adaptable recipes','read':{'action':'recipe','recipe':kind}})
    return {'available':True,'references':len(catalog()['references']),'modules':list(MODULES),'packages':packages,'pdfAvailable':bool(pdf),'pdfPreview':'Use preview with a reference id that has pdfPage; Setup prepares the bounded PDF reader.','policy':POLICY}

def task_context(args):
    import obsidian_vault as vault
    query=str(args.get('query') or '')[:1000]
    found=references({'query':query,'limit':3})
    if not found['references']:
        found=references({'limit':2});found['selection']='Representative examples; no exact keyword match.'
    result={'library':inventory(),'references':found['references'],'selection':found.get('selection','Ranked for the current request.'),'policy':POLICY}
    kind='vfx' if re.search(r'vfx|particle|effect|beam|trail',query,re.I) else 'pose' if re.search(r'animat|pose|rig|motion',query,re.I) else 'ui'
    result['recipe']={'id':kind,'excerpt':(HERE/(kind+'-recipes.md')).read_text(encoding='utf-8')[:1600]}
    try:result['memory']=vault.context({'project':args.get('project','default'),'query':query})
    except (ValueError,OSError) as error:result['memory']={'available':False,'error':str(error)[:300]}
    result['next']='Use these observations and recipes in the real deliverable. For a screenshot reference, call preview with its id and compare the actual page before claiming visual inspection. Generate requested editable artwork with ms_forge; read modules or install only when needed. Do not mix every style or replace existing systems.'
    return result

def references(args):
    data=catalog();rows=data['references'];query=str(args.get('query') or '').lower()[:1000]
    terms=set(re.findall(r'[\w-]+',query));style=str(args.get('style') or '').lower()
    ident=args.get('id');ranked=[]
    for row in rows:
        if ident and row.get('id')!=ident:continue
        hay=json.dumps(row,ensure_ascii=False).lower()
        if style and style not in hay:continue
        score=sum(1 for term in terms if term in hay)
        if terms and not score:continue
        ranked.append((score,row))
    ranked.sort(key=lambda pair:(-pair[0],str(pair[1].get('id',''))))
    limit=args.get('limit',4)
    if type(limit) is not int or not 1<=limit<=8:raise ValueError('limit must be 1–8')
    return {'policy':POLICY,'total':len(rows),'matches':len(ranked),'references':[r for _,r in ranked[:limit]],'source':'Supplied OMNI References Edition 500; original PDF retained separately.'}

def bundle(namespace=None):
    namespace=namespace or 'MultiScriptOmni_'+uuid.uuid4().hex[:12]
    if not isinstance(namespace,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,59}',namespace):raise ValueError('Use a namespace of up to 60 letters/digits/underscores, starting with a letter.')
    lines=['local RS = game:GetService("ReplicatedStorage")',f'assert(not RS:FindFirstChild("{namespace}"), "Existing namespace preserved; choose a fresh name")','local folder = Instance.new("Folder")',f'folder.Name = "{namespace}"','folder:SetAttribute("MultiScriptOmni", "6.50.2")','local ok, message = pcall(function()']
    hashes={}
    for name in MODULES:
        source=(HERE/'modules'/(name+'.luau')).read_text(encoding='utf-8');hashes[name]=hashlib.sha256(source.encode()).hexdigest()
        level='='
        while ']'+level+']' in source:level+='='
        lines.extend(['do',f'local source = [{level}[{source}]{level}]','local item = Instance.new("ModuleScript")',f'item.Name = "{name}"','item.Source = source','assert(item.Source == source, "Module source readback differs")','item.Parent = folder','end'])
    lines.extend(['end)','if not ok then folder:Destroy(); error(message) end','folder.Parent = RS',f'print("OMNI_INSTALLED {namespace} {len(MODULES)}")'])
    return {'namespace':namespace,'moduleCount':len(MODULES),'moduleSha256':hashes,'code':'\n'.join(lines),'usage':f'In a LocalScript: local kit = require(game:GetService("ReplicatedStorage").{namespace}.Toolkit); local ui = kit.new(game.Players.LocalPlayer:WaitForChild("PlayerGui"), {{reducedMotion = false}}). Create only requested panels/buttons; ui:Destroy() releases owned work. Themes require explicit registration; use Toolkit.Burst only for requested cosmetic effects.','verified':False,'policy':'Generated source only until an actual Studio installation receipt. Installation verifies source readback, not input behavior, appearance, asset loading or performance.'}

def call(args,install=None):
    action=args.get('action','references')
    if action=='status' or action=='packages':result=inventory()
    elif action=='context':result=task_context(args)
    elif action=='preview':
        import obsidian_vault as vault
        rows=references({'id':args.get('id'),'limit':1})['references'] if args.get('id') else []
        if not rows or type(rows[0].get('pdfPage')) is not int:raise ValueError('Choose a reference id with an actual pdfPage from references; no thumbnail is fabricated.')
        path=vault._path(vault._root(),'Attachments/'+PDF_SHA+'.pdf')
        if not path.is_file():raise ValueError('Import the supplied REFERENCES.pdf in Obsidian settings first. The built-in catalogue, modules and recipes are already available.')
        with path.open('rb') as stream:
            if vault._file_hash(stream)!=PDF_SHA:raise ValueError('The imported reference PDF changed; no unrelated page was substituted.')
        return vault.read({'path':'Attachments/'+PDF_SHA+'.pdf','page':rows[0]['pdfPage']})
    elif action=='references':result=references(args)
    elif action=='analyze':
        result=references(args);result['direction']='Keep the existing primary style and tokens; compare only these relevant references. Adapt spacing, hierarchy, state and VFX/pose recipes without importing branding or guessed assets.'
        result['recipes']=['ui-recipes.md','vfx-recipes.md','pose-recipes.md','composite-recipes.md']
        result['tools']='Use ms_forge for generated artwork and ms_roblox_omni install for the reviewed native kit when needed; no mandatory preparation/progress loop.'
        result['styleStudy']={'existingStyle':str(args.get('style') or 'Inspect project tokens first'),'approximateStartingPoints':[{'id':row.get('id'),'analysis':row.get('analysis',{})} for row in result['references'][:2]],'rule':'Keep primary structure coherent. Texture and effect accents are explicit choices; do not combine all styles or treat approximate samples as measured values.'}
    elif action=='recipe':
        name=args.get('recipe','ui')
        if name not in ('ui','vfx','pose','composite'):raise ValueError('Unknown recipe')
        text=(HERE/(name+'-recipes.md')).read_text(encoding='utf-8');offset=args.get('offset',0);limit=args.get('max_chars',10000)
        if type(offset) is not int or not 0<=offset<=100000 or type(limit) is not int or not 1000<=limit<=16000:raise ValueError('Use a bounded recipe offset/limit')
        result={'recipe':name,'text':text[offset:offset+limit],'next_offset':offset+limit if offset+limit<len(text) else None,'total_chars':len(text),'policy':POLICY}
    elif action=='modules':
        name=args.get('module')
        if not name:result={'modules':list(MODULES),'loadPolicy':'Require is inert. No global singleton, polling, combat service, remotes or automatic scene creation.'}
        else:
            if name not in MODULES:raise ValueError('Unknown reviewed module')
            source=(HERE/'modules'/(name+'.luau')).read_text(encoding='utf-8');offset=args.get('offset',0);limit=args.get('max_chars',12000)
            if type(offset) is not int or not 0<=offset<=100000 or type(limit) is not int or not 1000<=limit<=16000:raise ValueError('Use a bounded source offset/limit')
            result={'module':name,'text':source[offset:offset+limit],'total_chars':len(source),'next_offset':offset+limit if offset+limit<len(source) else None}
    elif action in ('bundle','install'):
        result=bundle(args.get('namespace'))
        if action=='install':
            if install is None:raise ValueError('Installation requires the live Roblox bridge; use bundle for source only.')
            return install(result,args)
    else:raise ValueError('Unsupported OMNI action')
    return {'text':json.dumps(result,ensure_ascii=False),'images':[]}
