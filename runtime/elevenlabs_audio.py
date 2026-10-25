#!/usr/bin/env python3
"""Secure local ElevenLabs sound-effects integration for Multi-Script."""
from pathlib import Path
import hashlib, json, os, re, time, math, random, struct, wave
from urllib import error, parse, request

HERE = Path(__file__).resolve().parent
ENV_FILE = HERE / ".env"
OUTPUT_DIR = HERE / "generated" / "audio"
ENDPOINT = "https://api.elevenlabs.io/v1/sound-generation"
MODEL_ID = "eleven_text_to_sound_v2"


def _api_key():
    value = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if value:
        return value
    if ENV_FILE.is_file():
        for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "ELEVENLABS_API_KEY":
                return value.strip().strip('"').strip("'")
    return ""


def configure_api_key(value):
    """Store one user's key only in the local bridge runtime/.env."""
    key = str(value or "").strip()
    if len(key) < 10 or any(c in key for c in "\r\n"):
        raise RuntimeError("Enter a valid ElevenLabs API key")
    lines = []
    if ENV_FILE.is_file():
        lines = [x for x in ENV_FILE.read_text(encoding="utf-8").splitlines()
                 if not x.strip().startswith("ELEVENLABS_API_KEY=")]
    lines.append(f"ELEVENLABS_API_KEY={key}")
    temp = ENV_FILE.with_suffix(".env.tmp")
    temp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try: os.chmod(temp, 0o600)
    except OSError: pass
    temp.replace(ENV_FILE)
    try: os.chmod(ENV_FILE, 0o600)
    except OSError: pass
    return status()


def clear_api_key():
    if ENV_FILE.is_file():
        lines = [x for x in ENV_FILE.read_text(encoding="utf-8").splitlines()
                 if not x.strip().startswith("ELEVENLABS_API_KEY=")]
        if lines:
            ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
            try: os.chmod(ENV_FILE, 0o600)
            except OSError: pass
        else:
            ENV_FILE.unlink(missing_ok=True)
    return status()


def status():
    cloud = bool(_api_key())
    return {
        "provider": "Multi-Script Audio",
        "configured": True,
        "defaultProvider": "local",
        "noApiKeyRequired": True,
        "elevenLabsConfigured": cloud,
        "elevenLabsConfigured": cloud,
        "providers": {
            "local": {"available": True, "cost": "free", "network": False, "apiKey": False, "format": "wav_44100_pcm16"},
            "elevenlabs": {"available": cloud, "configured": cloud, "model": MODEL_ID, "endpoint": ENDPOINT, "apiKey": True},
        },
        "outputDirectory": str(OUTPUT_DIR),
        "optionalElevenLabsSetupCommand": "python runtime/configure_elevenlabs.py",
        "secretStorage": "Optional ELEVENLABS_API_KEY environment variable or runtime/.env (local bridge only)",
    }


def _safe_name(value):
    value = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "sound-effect")).strip("-.")
    return (value[:80] or "sound-effect")


def _http_error(exc):
    try:
        body = exc.read().decode("utf-8", "replace")
        parsed = json.loads(body)
        detail = parsed.get("detail", parsed)
        if isinstance(detail, dict):
            detail = detail.get("message") or detail.get("status") or json.dumps(detail)
        return f"ElevenLabs HTTP {exc.code}: {detail}"
    except Exception:
        return f"ElevenLabs HTTP {getattr(exc, 'code', 'error')}: {getattr(exc, 'reason', exc)}"


def _generate_elevenlabs_sound_effect(text, name="sound-effect", duration_seconds=None, loop=False,
                          prompt_influence=0.3, output_format="mp3_44100_128", opener=None):
    text = str(text or "").strip()
    if not text:
        raise RuntimeError("text is required")
    if len(text) > 2500:
        raise RuntimeError("text must be 2500 characters or fewer")
    key = _api_key()
    if not key:
        raise RuntimeError("ElevenLabs is not configured. Run: python runtime/configure_elevenlabs.py")
    if duration_seconds is not None:
        duration_seconds = float(duration_seconds)
        if duration_seconds < 0.5 or duration_seconds > 30:
            raise RuntimeError("duration_seconds must be between 0.5 and 30")
    influence = float(prompt_influence)
    if influence < 0 or influence > 1:
        raise RuntimeError("prompt_influence must be between 0 and 1")
    allowed_formats = {"mp3_22050_32", "mp3_44100_64", "mp3_44100_96", "mp3_44100_128", "mp3_44100_192", "pcm_16000", "pcm_22050", "pcm_24000", "pcm_44100"}
    if output_format not in allowed_formats:
        raise RuntimeError("unsupported output_format")
    payload = {"text": text, "loop": bool(loop), "prompt_influence": influence, "model_id": MODEL_ID}
    if duration_seconds is not None:
        payload["duration_seconds"] = duration_seconds
    url = ENDPOINT + "?" + parse.urlencode({"output_format": output_format})
    req = request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST", headers={
        "xi-api-key": key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg, audio/wav, application/octet-stream",
        "User-Agent": "Multi-Script/6.30.0",
    })
    open_fn = opener or request.urlopen
    try:
        with open_fn(req, timeout=120) as response:
            audio = response.read()
            content_type = response.headers.get("Content-Type", "audio/mpeg").split(";", 1)[0].strip().lower()
            character_cost = response.headers.get("character-cost")
    except error.HTTPError as exc:
        raise RuntimeError(_http_error(exc)) from exc
    except error.URLError as exc:
        raise RuntimeError(f"Could not reach ElevenLabs: {exc.reason}") from exc
    if not audio:
        raise RuntimeError("ElevenLabs returned an empty audio response")
    extension = ".wav" if output_format.startswith("pcm_") or "wav" in content_type else ".mp3"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    digest = hashlib.sha256(audio).hexdigest()[:10]
    path = OUTPUT_DIR / f"{_safe_name(name)}-{stamp}-{digest}{extension}"
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(audio)
    temporary.replace(path)
    metadata = {
        "provider": "ElevenLabs", "model": MODEL_ID, "created": str(path), "format": output_format,
        "contentType": content_type, "bytes": len(audio), "sha256": hashlib.sha256(audio).hexdigest(),
        "durationSeconds": duration_seconds, "loop": bool(loop), "promptInfluence": influence,
        "characterCost": character_cost, "prompt": text,
        "engineHandoff": "Import this local file through the connected engine MCP, configure loop/spatial/compression settings, then test it in context.",
    }
    path.with_suffix(path.suffix + ".json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def _local_kind(text):
    low=text.lower()
    groups=[
        ("explosion",("explosion","blast","boom","grenade")),
        ("impact",("punch","impact","hit","slam","thud","kick")),
        ("laser",("laser","blaster","ray","sci-fi shot","magic bolt")),
        ("whoosh",("whoosh","swoosh","dash","swing","swipe")),
        ("footstep",("footstep","step","walking","run step")),
        ("coin",("coin","reward","success","pickup","collect","level up")),
        ("alarm",("alarm","warning","siren","error","danger")),
        ("rain",("rain","storm","water ambience")),
        ("wind",("wind","air ambience","forest ambience")),
        ("engine",("engine","motor","machine","generator","hum")),
        ("click",("click","button","ui","menu","toggle","tap")),
    ]
    return next((kind for kind,words in groups if any(w in low for w in words)),"generic")


def _generate_local_sound_effect(text,name="sound-effect",duration_seconds=None,loop=False,seed=None):
    text=str(text or "").strip()
    if not text: raise RuntimeError("text is required")
    if len(text)>2500: raise RuntimeError("text must be 2500 characters or fewer")
    kind=_local_kind(text); defaults={"click":0.16,"impact":0.55,"explosion":1.8,"laser":0.55,"whoosh":0.75,"footstep":0.32,"coin":0.7,"alarm":1.5,"rain":6.0,"wind":6.0,"engine":4.0,"generic":1.0}
    duration=float(duration_seconds if duration_seconds is not None else defaults[kind])
    if duration<0.05 or duration>30: raise RuntimeError("local duration_seconds must be between 0.05 and 30")
    rate=44100;n=max(1,int(rate*duration));rng=random.Random(seed if seed is not None else int(hashlib.sha256(text.encode()).hexdigest()[:16],16))
    out=[];lp=0.0
    def env(t,attack=0.01,release=0.3): return min(1.0,t/max(attack,1e-4))*min(1.0,max(0.0,(duration-t))/max(release,1e-4))
    for i in range(n):
        t=i/rate; noise=rng.uniform(-1,1); x=0.0
        if kind=="click": x=(math.sin(2*math.pi*(1700-900*t/duration)*t)*0.8+noise*0.18)*math.exp(-28*t)
        elif kind=="impact": x=(math.sin(2*math.pi*(115-70*t/duration)*t)*0.85+noise*0.45)*math.exp(-7*t)
        elif kind=="explosion":
            lp=lp*0.92+noise*0.08;x=(lp*1.5+math.sin(2*math.pi*(62-24*t/duration)*t)*0.45)*math.exp(-2.6*t)
        elif kind=="laser": x=(math.sin(2*math.pi*(1400-1100*t/duration)*t)+0.22*math.sin(2*math.pi*(2800-1800*t/duration)*t))*math.exp(-5*t)
        elif kind=="whoosh":
            lp=lp*0.7+noise*0.3;x=lp*math.sin(math.pi*min(1,t/duration))*0.9
        elif kind=="footstep": x=(noise*0.38+math.sin(2*math.pi*92*t)*0.7)*math.exp(-14*t)
        elif kind=="coin": x=(math.sin(2*math.pi*988*t)+0.65*math.sin(2*math.pi*1319*t))*math.exp(-3.8*t)
        elif kind=="alarm": x=(math.sin(2*math.pi*(650+180*math.sin(2*math.pi*2.2*t))*t))*env(t,0.02,0.08)*0.72
        elif kind=="rain":
            lp=lp*0.22+noise*0.78;x=(lp*0.42+(0.7 if rng.random()<0.0007 else 0))*env(t,0.08,0.15)
        elif kind=="wind":
            lp=lp*0.985+noise*0.015;x=lp*(0.55+0.25*math.sin(2*math.pi*0.17*t))*env(t,0.2,0.25)*2.0
        elif kind=="engine": x=(math.sin(2*math.pi*82*t)+0.35*math.sin(2*math.pi*164*t)+noise*0.06)*env(t,0.08,0.12)*0.62
        else: x=(math.sin(2*math.pi*330*t)*0.55+noise*0.16)*env(t,0.02,0.25)*math.exp(-1.8*t)
        out.append(max(-1.0,min(1.0,x)))
    if loop and n>256:
        fade=min(int(rate*0.12),n//4)
        for i in range(fade):
            a=i/max(1,fade-1);mixed=out[i]*a+out[n-fade+i]*(1-a);out[i]=out[n-fade+i]=mixed
    peak=max(abs(x) for x in out) or 1;gain=min(0.95/peak,1.8)
    OUTPUT_DIR.mkdir(parents=True,exist_ok=True);stamp=time.strftime("%Y%m%d-%H%M%S");digest=hashlib.sha256((text+str(seed)).encode()).hexdigest()[:10]
    path=OUTPUT_DIR/f"{_safe_name(name)}-{stamp}-{digest}.wav";tmp=path.with_suffix('.wav.part')
    with wave.open(str(tmp),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate);w.writeframes(b''.join(struct.pack('<h',int(max(-1,min(1,x*gain))*32767)) for x in out))
    tmp.replace(path);audio=path.read_bytes()
    meta={"provider":"Multi-Script Local Audio","model":"deterministic-procedural-v1","created":str(path),"format":"wav_44100_pcm16","contentType":"audio/wav","bytes":len(audio),"sha256":hashlib.sha256(audio).hexdigest(),"durationSeconds":duration,"loop":bool(loop),"prompt":text,"soundClass":kind,"seed":seed,"cost":"free","networkUsed":False,"apiKeyUsed":False,"limitations":"Procedural synthesis is strongest for UI, impacts, ambience and stylized effects; use optional ElevenLabs for complex natural recordings or speech-like material.","engineHandoff":"Import this local WAV through the connected engine MCP, configure loop/spatial/compression/bus settings, then test it in context."}
    path.with_suffix('.wav.json').write_text(json.dumps(meta,indent=2),encoding='utf-8');return meta


def generate_sound_effect(text,name="sound-effect",duration_seconds=None,loop=False,prompt_influence=0.3,output_format="mp3_44100_128",opener=None,provider="auto",seed=None):
    provider=str(provider or "auto").strip().lower()
    if provider not in {"auto","local","elevenlabs"}: raise RuntimeError("provider must be auto, local, or elevenlabs")
    # Keyless local synthesis is the safe default. An injected opener implies an
    # explicit cloud transport test and preserves backward-compatible testing.
    if provider in {"auto","local"} and opener is None:
        return _generate_local_sound_effect(text,name,duration_seconds,loop,seed)
    return _generate_elevenlabs_sound_effect(text,name,duration_seconds,loop,prompt_influence,output_format,opener)


def list_generated_audio(limit=50):
    limit = max(1, min(200, int(limit)))
    if not OUTPUT_DIR.is_dir():
        return {"count": 0, "assets": []}
    rows = []
    for path in sorted(OUTPUT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
            if Path(item.get("created", "")).is_file():
                rows.append(item)
        except Exception:
            continue
        if len(rows) >= limit:
            break
    return {"count": len(rows), "assets": rows}
