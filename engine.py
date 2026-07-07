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

ERROR_LOG_FUNC = None

def _log_err(msg):
    if ERROR_LOG_FUNC:
        try:
            ERROR_LOG_FUNC(f"[Engine] {msg}")
        except Exception:
            pass
    else:
        print("[ENGINE ERROR]", msg)


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
                        _log_err("bearer_from_cookie: Cookie expired or close to expiration.")
                        return None, None
                except Exception as e:
                    _log_err(f"bearer_from_cookie date check exception: {e}")
            return j.get("access_token"), (j.get("user") or {}).get("email")
        else:
            _log_err(f"bearer_from_cookie failed status: {r.status_code}, response: {r.text[:200]}")
    except Exception as e:
        _log_err(f"bearer_from_cookie exception: {e}")
    return None, None


def get_project(cookie):
    if not cookie:
        return None
    inp = urllib.parse.quote(json.dumps({"json": {"pageSize": 20, "toolName": "PINHOLE", "cursor": None},
                                         "meta": {"values": {"cursor": ["undefined"]}}}))
    H = {"Cookie": cookie, "User-Agent": UA_CH, "Referer": "https://labs.google/", "Accept": "application/json"}
    try:
        r = cffi.get("https://labs.google/fx/api/trpc/project.searchUserProjects?input=" + inp, headers=H, **_kw())
        if r.status_code == 200:
            projs = (((r.json() or {}).get("result") or {}).get("data") or {}).get("json", {}).get("result", {}).get("projects", [])
            if projs:
                return projs[0]["projectId"]
        else:
            _log_err(f"searchUserProjects request failed with status: {r.status_code}, response: {r.text[:200]}")
    except Exception as e:
        _log_err(f"get_project search user projects exception: {e}")
    # tạo mới
    try:
        r = cffi.post("https://labs.google/fx/api/trpc/project.createProject",
                      headers={**H, "Content-Type": "application/json"},
                      data=json.dumps({"json": {"projectTitle": "ThinAptm", "toolName": "PINHOLE"}}), **_kw())
        if r.status_code == 200:
            d = (((r.json() or {}).get("result") or {}).get("data") or {}).get("json") or {}
            proj_id = d.get("projectId") or (d.get("result") or {}).get("projectId")
            if proj_id:
                return proj_id
        _log_err(f"createProject failed with status: {r.status_code}, response: {r.text[:200]}")
    except Exception as e:
        _log_err(f"get_project create project exception: {e}")
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
    try:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
    except Exception as e:
        _log_err(f"upload_image failed to read file {image_path}: {e}")
        return None
    payload = {"clientContext": {"sessionId": f";{int(time.time()*1000)}", "projectId": project, "tool": "PINHOLE"}, "imageBytes": b64}
    try:
        r = cffi.post(f"{BASE}/flow/uploadImage?key={KEY}", headers=_hc(bearer), data=json.dumps(payload), **_kw(timeout))
        if r.status_code in (200, 201):
            media = (r.json() or {}).get("media") or {}
            media_id = media.get("name") if isinstance(media, dict) else (media[0].get("name") if media else None)
            if media_id:
                return media_id
            else:
                _log_err(f"upload_image success but media ID not found. JSON: {r.json()}")
        else:
            _log_err(f"upload_image failed status: {r.status_code}, response: {r.text[:300]}")
    except Exception as e:
        _log_err(f"upload_image request exception: {e}")
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
    """Phân loại lỗi generate. QUAN TRỌNG: mã 429/RESOURCE_EXHAUSTED KHÔNG đủ để phân biệt —
    phải đọc `reason` trong error.details (đã đo body thật):
      throttle    = USER_REQUESTS_THROTTLED (giới hạn TỐC ĐỘ) -> nghỉ NGẮN vài giây, TỰ HỒI (KHÔNG cách ly dài)
      quota_hard  = hết quota/credit ngày (QUOTA_EXCEEDED/DAILY/CREDIT/OUT_OF...) -> cách ly DÀI + đổi account
      unusual     = reCAPTCHA/UNUSUAL_ACTIVITY -> thử lại nhanh (bypass/token khác)
      ratelimit   = TOO_MUCH_TRAFFIC trần (rate theo IP) -> backoff nhẹ
      ip_block    = HTML "Sorry" (chặn IP) | auth = 401 bearer chết
    RESOURCE_EXHAUSTED không rõ reason -> coi là throttle (thực đo: submit hồi lại sau 1-2 phút, KHÔNG phải hết quota).
    """
    if r.status_code == 401:
        return "auth", None
    txt = r.text
    head = txt[:200].lower()
    if "<html" in head or "sorry" in head:
        return "ip_block", None

    reason = ""
    try:
        err = (r.json() or {}).get("error", {})
        for d in err.get("details", []) or []:
            if isinstance(d, dict) and d.get("reason"):
                reason = d["reason"]; break
    except Exception:
        pass
    U = (reason + " " + txt[:400]).upper()

    if "THROTTLED" in U:
        return "throttle", None                 # giới hạn tốc độ -> nghỉ ngắn, tự hồi
    if "RECAPTCHA" in U or "UNUSUAL_ACTIVITY" in U or "PUBLIC_ERROR_UNUSUAL_ACTIVITY" in U:
        return "unusual", None
    if "TOO_MUCH_TRAFFIC" in U:
        return "ratelimit", None
    if ("QUOTA_EXCEEDED" in U or "OUT_OF_CREDIT" in U or "INSUFFICIENT" in U
            or "DAILY" in U or "QUOTA_LIMIT" in U):
        return "quota_hard", None               # hết quota thật -> cách ly dài
    if r.status_code == 429 or "RESOURCE_EXHAUSTED" in U:
        return "throttle", None                 # RESOURCE_EXHAUSTED không rõ -> throttle (mặc định an toàn)
    if "UNUSUAL" in U:
        return "unusual", None
    return "retry", None


def submit_video(bearer, project, prompt, seed, aspect, model, ref_media_id=None, timeout=120):
    # I2V (có ảnh gốc) BẮT BUỘC dùng model r2v (reference->video); dùng model t2v -> render FAIL.
    if ref_media_id:
        model = VID_I2V_MODEL
    url = GEN_I2V if ref_media_id else GEN_T2V
    payload = _vpayload(prompt, project, seed, aspect, model, ref_media_id)
    try:
        r = cffi.post(url, headers=_hf(bearer), data=json.dumps(payload), **_kw(timeout))
    except Exception as e:
        _log_err(f"submit_video HTTP client exception: {e}")
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
        if ops:
            return "ok", ops
        else:
            _log_err(f"submit_video succeeded but no operations found in JSON: {j}")
            return "retry", None
    if r.status_code != 429:
        _log_err(f"submit_video API failed status: {r.status_code}, response: {r.text[:300]}")
    else:
        _log_err(f"submit_video API failed status: 429")
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
    for attempt in range(max_attempts):
        try:
            r = cffi.post(CHECK, headers=_hc(bearer), data=json.dumps(body), **_kw(timeout))
        except Exception as e:
            _log_err(f"poll_video network exception (attempt {attempt+1}/{max_attempts}): {e}")
            time.sleep(interval); continue
        if r.status_code == 401:
            _log_err(f"poll_video unauthorized (401)")
            return "auth", None
        if r.status_code != 200:
            _log_err(f"poll_video check failed status {r.status_code}, response: {r.text[:300]}")
            time.sleep(interval); continue
        st = _find_status(r.json())
        if any(x in s for s in st for x in ("SUCCESSFUL", "SUCCEEDED", "COMPLETE")):
            return "done", ops[0]
        if any("FAIL" in s for s in st):
            err_msg = "UNKNOWN_ERROR"
            try:
                for o in r.json().get("operations", []):
                    op_err = (o.get("operation") or {}).get("error") or {}
                    msg = op_err.get("message")
                    if msg:
                        err_msg = msg
                        break
            except Exception:
                pass
            _log_err(f"poll_video generation failed. API response: {r.json()}")
            return "failed", err_msg
        time.sleep(interval)
    _log_err(f"poll_video timeout after {max_attempts} attempts.")
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
        else:
            _log_err(f"download_video failed. status: {r.status_code}, content-type: {r.headers.get('content-type')}, response: {r.text[:200]}")
    except Exception as e:
        _log_err(f"download_video exception: {e}")
    return 0


def download_url(url, dst, timeout=120):
    data = cffi.get(url, **_kw(timeout)).content
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    with open(dst, "wb") as f:
        f.write(data)
    return len(data)
