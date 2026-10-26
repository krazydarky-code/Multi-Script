"""Permit requested additive improvements while preserving every prior skill/step."""
from pathlib import Path
import gzip,hashlib,json
ROOT=Path(__file__).resolve().parents[2]
def assert_preserved_skills(current,legacy_base_sha=None,legacy_file_sha=None):
    with gzip.open(ROOT/'tests/fixtures/skills-before-650.json.gz','rt',encoding='utf-8') as stream:baseline=json.load(stream)
    if legacy_base_sha:assert baseline['legacyBaseSha256']==legacy_base_sha
    if legacy_file_sha:assert baseline['sourceFileSha256']==legacy_file_sha
    assert len(current)==249 and set(current)==set(baseline['skills']),'Existing skill IDs were replaced, deleted or duplicated'
    for ident,previous in baseline['skills'].items():
        skill=current[ident]
        assert skill['name']==previous['name'] and skill.get('engine')==previous['engine'],ident
        hashes={hashlib.sha256(step.encode()).hexdigest() for step in skill['steps']}
        assert set(previous['steps'])<=hashes,(ident,'A useful prior skill step was removed/replaced')
