"""
Thìn Aptm — Engine tạo VIDEO + ẢNH Google Flow bằng android_bypass (curl thuần, không browser).
Tự chứa (chỉ cần curl_cffi). Auth: cookie labs.google -> bearer. Video: submit -> poll -> tải mp4.
"""
import json, time, base64, os, uuid, urllib.parse
from curl_cffi import requests as cffi

BASE = "https://aisandbox-pa.googleapis.com/v1"
KEY = "AIzaSyBtrm0o5ab1c-Ec8ZuLcGt3oJAA5VWt3pY"
UA_FF = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) Gecko/20100101 Firefox/151.0"
UA_CH = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
BYPASS_TOKEN = "android_bypass"
APP_ANDROID = "RECAPTCHA_APPLICATION_TYPE_ANDROID"
IMP = "chrome"

GEN_T2V = f"{BASE}/video:batchAsyncGenerateVideoText"
GEN_I2V = f"{BASE}/video:batchAsyncGenerateVideoReferenceImages"
CHECK = f"{BASE}/video:batchCheckAsyncVideoGenerationStatus?key={KEY}"

VID_ASPECTS = {"Dọc 9:16 (TikTok)": "VIDEO_ASPECT_RATIO_PORTRAIT", "Ngang 16:9": "VIDEO_ASPECT_RATIO_LANDSCAPE"}
IMG_ASPECTS = {"Dọc 9:16 (TikTok)": "IMAGE_ASPECT_RATIO_PORTRAIT", "Ngang 16:9": "IMAGE_ASPECT_RATIO_LANDSCAPE", "Vuông 1:1": "IMAGE_ASPECT_RATIO_SQUARE"}
VID_MODELS = {"Veo 3.1 (nhanh)": "veo_3_1_t2v_lite_low_priority", "Veo 3.1 (chất lượng)": "veo_3_1_t2v"}
VID_I2V_MODEL = "veo_3_1_r2v_lite_low_priority"


def _kw(t=60):
    return {"impersonate": IMP, "timeout": t}


# ---------- AUTH ----------
def bearer_from_cookie(cookie, timeout=25):
    if not cookie:
        return None, None
    H = {"Cookie": cookie, "User-Agent": UA_CH, "Referer": "https://labs.google/", "Accept": "application/json"}
    try:
        r = cffi.get("https://labs.google/fx/api/auth/session", headers=H, **_kw(timeout))
        if r.status_code == 200:
            j = r.json() or {}
            exp = j.get("expires")
            if exp:
                try:
                    from datetime import datetime
                    if datetime.fromisoformat(str(exp).replace("Z", "+00:00")).timestamp() < time.time() + 120:
                        return None, None
                except Exception:
                    pass
            return j.get("access_token"), (j.get("user") or {}).get("email")
    except Exception:
        pass
    return None, None


def get_project(cookie):
    if not cookie:
        return None
    inp = urllib.parse.quote(json.dumps({"json": {"pageSize": 20, "toolName": "PINHOLE", "cursor": None},
                                         "meta": {"values": {"cursor": ["undefined"]}}}))
    H = {"Cookie": cookie, "User-Agent": UA_CH, "Referer": "https://labs.google/", "Accept": "application/json"}
    try:
        r = cffi.get("https://labs.google/fx/api/trpc/project.searchUserProjects?input=" + inp, headers=H, **_kw())
        projs = (((r.json() or {}).get("result") or {}).get("data") or {}).get("json", {}).get("result", {}).get("projects", [])
        if projs:
            return projs[0]["projectId"]
    except Exception:
        pass
    # tạo mới
    try:
        r = cffi.post("https://labs.google/fx/api/trpc/project.createProject",
                      headers={**H, "Content-Type": "application/json"},
                      data=json.dumps({"json": {"projectTitle": "ThinAptm", "toolName": "PINHOLE"}}), **_kw())
        d = (((r.json() or {}).get("result") or {}).get("data") or {}).get("json") or {}
        return d.get("projectId") or (d.get("result") or {}).get("projectId")
    except Exception:
        return None


def _hf(bearer):  # headers Firefox cho android_bypass
    return {"Authorization": f"Bearer {bearer}", "Content-Type": "text/plain;charset=UTF-8", "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9,vi;q=0.8", "Origin": "https://labs.google", "Referer": "https://labs.google/",
            "User-Agent": UA_FF, "Cache-Control": "no-cache", "Pragma": "no-cache", "Priority": "u=1, i",
            "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "cross-site", "X-Browser-Channel": "stable"}


def _hc(bearer):  # headers Chrome cho poll/upload
    return {"Authorization": f"Bearer {bearer}", "Content-Type": "text/plain;charset=UTF-8", "Accept": "*/*",
            "Origin": "https://labs.google", "Referer": "https://labs.google/", "User-Agent": UA_CH}


# ---------- UPLOAD ảnh (cho I2V / ảnh tham chiếu) ----------
def upload_image(bearer, project, image_path, timeout=120):
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    payload = {"clientContext": {"sessionId": f";{int(time.time()*1000)}", "projectId": project, "tool": "PINHOLE"}, "imageBytes": b64}
    try:
        r = cffi.post(f"{BASE}/flow/uploadImage?key={KEY}", headers=_hc(bearer), data=json.dumps(payload), **_kw(timeout))
        if r.status_code in (200, 201):
            media = (r.json() or {}).get("media") or {}
            return media.get("name") if isinstance(media, dict) else (media[0].get("name") if media else None)
    except Exception:
        pass
    return None


# ---------- IMAGE (bypass) ----------
def generate_image(bearer, project, prompt, seed, aspect, model="GEM_PIX_2", image_inputs=None, timeout=90):
    ctx = {"recaptchaContext": {"token": BYPASS_TOKEN, "applicationType": APP_ANDROID}, "projectId": project, "tool": "PINHOLE", "sessionId": f";{int(time.time()*1000)}"}
    req = {"clientContext": dict(ctx), "imageModelName": model, "imageAspectRatio": aspect,
           "structuredPrompt": {"parts": [{"text": prompt}]}, "seed": seed, "imageInputs": image_inputs or []}
    payload = {"clientContext": ctx, "mediaGenerationContext": {"batchId": str(uuid.uuid4())}, "useNewMedia": True, "requests": [req]}
    try:
        r = cffi.post(f"{BASE}/projects/{project}/flowMedia:batchGenerateImages", headers=_hf(bearer), data=json.dumps(payload), **_kw(timeout))
    except Exception:
        return "retry", None
    if r.status_code == 200:
        for m in (r.json().get("media") or []):
            gi = (m.get("image") or {}).get("generatedImage") or {}
            if gi.get("fifeUrl") or gi.get("encodedImage"):
                return "ok", {"fife": gi.get("fifeUrl"), "b64": gi.get("encodedImage")}
        return "retry", None
    return _classify(r)


# ---------- VIDEO (bypass): submit -> poll -> download ----------
def _vpayload(prompt, project, seed, aspect, model, ref_media_id=None):
    req = {"aspectRatio": aspect, "seed": seed, "textInput": {"structuredPrompt": {"parts": [{"text": prompt}]}},
           "videoModelKey": model, "metadata": {}}
    if ref_media_id:
        req["referenceImages"] = [{"imageUsageType": "IMAGE_USAGE_TYPE_ASSET", "mediaId": ref_media_id}]
    return {"mediaGenerationContext": {"batchId": str(uuid.uuid4()), "audioFailurePreference": "BLOCK_SILENCED_VIDEOS"},
            "clientContext": {"sessionId": f";{int(time.time()*1000)}", "projectId": project, "tool": "PINHOLE",
                              "userPaygateTier": "PAYGATE_TIER_TWO",
                              "recaptchaContext": {"applicationType": APP_ANDROID, "token": BYPASS_TOKEN}},
            "requests": [req], "useV2ModelConfig": True}


def _classify(r):
    if r.status_code == 401:
        return "auth", None
    b = r.text
    if "UNUSUAL" in b:
        return "unusual", None
    if r.status_code == 429 or "RESOURCE_EXHAUSTED" in b or "TOO_MUCH_TRAFFIC" in b:
        return "quota", None
    return "retry", None


def submit_video(bearer, project, prompt, seed, aspect, model, ref_media_id=None, timeout=120):
    # I2V (có ảnh gốc) BẮT BUỘC dùng model r2v (reference->video); dùng model t2v -> render FAIL.
    if ref_media_id:
        model = VID_I2V_MODEL
    url = GEN_I2V if ref_media_id else GEN_T2V
    payload = _vpayload(prompt, project, seed, aspect, model, ref_media_id)
    try:
        r = cffi.post(url, headers=_hf(bearer), data=json.dumps(payload), **_kw(timeout))
    except Exception:
        return "retry", None
    if r.status_code == 200:
        j = r.json()
        ops = []
        for o in j.get("operations", []):
            n = (o.get("operation") or {}).get("name")
            if n:
                ops.append(n)
        if not ops:
            for m in j.get("media", []):
                if m.get("name"):
                    ops.append(m["name"])
        return ("ok", ops) if ops else ("retry", None)
    return _classify(r)


def _find_status(o, out=None):
    out = out if out is not None else []
    if isinstance(o, dict):
        for k, v in o.items():
            if k == "status" and isinstance(v, str):
                out.append(v)
            else:
                _find_status(v, out)
    elif isinstance(o, list):
        for v in o:
            _find_status(v, out)
    return out


def poll_video(bearer, ops, max_attempts=90, interval=8, timeout=60):
    body = {"operations": [{"operation": {"name": n}} for n in ops]}
    for _ in range(max_attempts):
        try:
            r = cffi.post(CHECK, headers=_hc(bearer), data=json.dumps(body), **_kw(timeout))
        except Exception:
            time.sleep(interval); continue
        if r.status_code == 401:
            return "auth", None
        if r.status_code != 200:
            time.sleep(interval); continue
        st = _find_status(r.json())
        if any(x in s for s in st for x in ("SUCCESSFUL", "SUCCEEDED", "COMPLETE")):
            return "done", ops[0]
        if any("FAIL" in s for s in st):
            return "failed", None
        time.sleep(interval)
    return "timeout", None


def download_video(media_id, cookie, dst, timeout=180):
    H = {"Cookie": cookie, "User-Agent": UA_CH, "Referer": "https://labs.google/", "Accept": "*/*"}
    try:
        r = cffi.get(f"https://labs.google/fx/api/trpc/media.getMediaUrlRedirect?name={media_id}", headers=H,
                     **_kw(timeout), allow_redirects=True)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("video"):
            os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
            with open(dst, "wb") as f:
                f.write(r.content)
            return len(r.content)
    except Exception:
        pass
    return 0


def download_url(url, dst, timeout=120):
    data = cffi.get(url, **_kw(timeout)).content
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    with open(dst, "wb") as f:
        f.write(data)
    return len(data)
