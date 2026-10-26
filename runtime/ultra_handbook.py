# SPDX-License-Identifier: GPL-3.0-or-later
"""Project-aware skill application; no new tool permissions or model training."""
from pathlib import Path
import json,re
_CACHE=None
PHASES=('inspect','design','build','integrate','verify','failures')
def load():
    global _CACHE
    path=Path(__file__).with_name('ultra-handbook.json');stat=path.stat();fingerprint=(stat.st_mtime_ns,stat.st_size)
    if _CACHE is None or _CACHE[0]!=fingerprint:
        data=json.loads(path.read_text(encoding='utf-8'))
        if set(data.get('phases',[]))!=set(PHASES) or len(data.get('manuals',{}))!=12:raise ValueError('Invalid Ultra handbook pack')
        _CACHE=(fingerprint,data)
    return _CACHE[1]
def manual_for(skill_id,skill):
    # A legacy metadata category is not sufficient: model-routing and export
    # skills have historically been assigned unrelated generic domains.
    text=(skill_id+' '+str(skill.get('name',''))).lower()
    if re.search(r'notion-|provider-|prompt-economy|tool-call|tool-result|mcp-orchestrator|cross-engine|multi-app|repository|security|architecture|serialization|developer-handoff',text):return 'ultraengineering'
    patterns=[(r'accessib|cross-platform-input|responsive-constraints','ultraaccessibility'),(r'profil|performance|optimi|context-budget','ultraperformance'),(r'test|debug|fix-errors|quality-score|batch-validation|build-release','ultraqa'),(r'datastore|data-store|session-lock|network|remote-security|save-system|save-progression|netcode|receipt','ultranetwork'),(r'animat|rigging|shape-keys|playables|timeline','ultraanimation'),(r'audio|sound|music','ultraaudio'),(r'vfx|particle|shader|lighting|effects','ultravfx'),(r'\b(ui|ux|gui|hud)\b|auto-layout|components|design-tokens|prototype|prototyping|canvas-svg','ultragui'),(r'model|mesh|sculpt|retopolog|baking|uv|material|gltf|fbx|export-pipeline|lod|collision-mesh','ultramodelling'),(r'world|terrain|level|blockout|scene-composition|gridmap|tilemap|scatter|path-fence','ultraworld'),(r'gameplay|combat|ability|character|input-map|quest|npc|navigation|physics','ultragameplay')]
    for pattern,mid in patterns:
        if re.search(pattern,text):return mid
    domain=skill.get('capabilityDomain','')
    return {'ui-ux':'ultragui','animation':'ultraanimation','vfx':'ultravfx','modeling':'ultramodelling','textures-art':'ultramodelling','world-levels':'ultraworld','audio':'ultraaudio','multiplayer-networking':'ultranetwork','persistence-economy':'ultranetwork','performance-platform':'ultraperformance','testing-release':'ultraqa','combat-abilities':'ultragameplay','ai-navigation':'ultragameplay','input-camera-character':'ultragameplay','physics-simulation':'ultragameplay'}.get(domain,'ultraengineering')
def skill_application(skill_id,skill,objective='',sections=None):
    pack=load();mid=manual_for(skill_id,skill);m=pack['manuals'][mid]
    engine=str(skill.get('engine') or 'general').lower()
    if skill_id in {'check-clean-ui','check-props','code-quality','scripting-power','npc-pathfinding','game-systems','vfx-assets','fix-errors'}:engine='roblox'
    phases=list(dict.fromkeys(sections or ('inspect','build','verify')))
    if any(p not in PHASES for p in phases):raise ValueError('manual_sections must use inspect, design, build, integrate, verify or failures')
    explicit_read=bool(re.search(r"\b(read.only|inspect only|review only|do not (?:edit|change|build)|don't (?:edit|change|build)|without (?:editing|changing))\b",objective,re.I))
    query=bool(re.search(r'^\s*(explain|describe|compare|review|inspect|list|what|how|why)\b',objective,re.I))
    followup_write=bool(re.search(r'\b(?:then|and|afterwards)\s+(?:actually\s+)?(?:build|create|implement|edit|fix|write|change|make|improve|polish|refine|integrate)\b',objective,re.I))
    read_only=skill_id=='discover-project' or explicit_read or (query and not followup_write)
    if read_only:phases=['inspect','verify']
    full=bool(sections) and not read_only
    # Keep the familiar entry checks and include the directly expanded portion
    # of this same manual. Appended guidance must reach ordinary skill reads,
    # not only a rarely requested full handbook dump.
    starts=m.get('referenceExpansionBaseline',{})
    checks={p:list(m['phases'][p] if full else m['phases'][p][:2]+(m['phases'][p][starts[p]:] if p in starts else [])) for p in phases}
    if read_only:checks={'inspect':['Inspect only the requested scope and record actual paths, state and uncertainties. Do not mutate source, scenes, accounts or files.'],'verify':['Verify observations with relevant read-only evidence. A failed/truncated read is unknown, not proof that the project is empty. Report findings and boundaries without unrequested implementation.']}
    return {'revision':pack['revision'],'manual_id':mid,'resourceApplication':m.get('resourceApplication',{}),'engine':engine,'mode':'inspection-only' if read_only else 'apply-within-request','policy':pack['policy'],'skillUse':pack['skillPolicy'],'phaseChecklists':checks,'phaseExitCriteria':({p:('The requested read-only observations and uncertainty are recorded.' if p=='inspect' else 'Findings have read-only evidence or explicit limits; no unrequested edits were made.') for p in phases} if read_only else {p:m['phaseExitCriteria'][p] for p in phases}),'engineNotes':m['engineNotes'].get(engine),'acceptance':m['acceptance'] if full and 'verify' in phases else [],'diagnostics':m['diagnostics'] if full and 'failures' in phases else [],'availableSections':list(PHASES),'fullDetail':{'tool':'ms_get_skill','params':{'skill_id':skill_id,'objective':objective,'manual_sections':list(PHASES)},'manualTool':'When ms_ultra_manual is advertised and Ultra is active, its read action can retrieve this manual by manual_id and the relevant engine.'},'evidenceRule':'A loaded method is guidance, not proof of implementation. Reuse it, apply the authorized slice, then check the actual deliverable. Do not load every manual/skill or repeat the same guidance unchanged.'}

def expand_existing_workflow(skill_id,workflow):
    """Apply additions to the two existing production skills without rewriting v24."""
    domain={'roblox-studio-gui-composition':'gui','roblox-pro-animation':'animation'}.get(skill_id)
    if not domain or not isinstance(workflow,dict):return workflow
    path=Path(__file__).parent/'skill-resources/roblox-production/methods.json'
    data=json.loads(path.read_text(encoding='utf-8'))[domain];baseline=data.get('expansionBaselineChars',{})
    result=dict(workflow)
    for target,phases in {'inspect':['inspect'],'craft':['design'],'execute':['build','integrate'],'verify':['verify'],'recovery':['failures']}.items():
        additions=' '.join(data[p][baseline[p]:].strip() for p in phases if p in baseline)
        if additions:result[target]=str(result.get(target,'')).rstrip()+'\n\n'+additions
    return result
