"""
login — 2 cách lấy cookie labs.google:
  1. manual_login(): mở Chrome, người dùng TỰ đăng nhập + vào Flow -> có cookie thì tự lấy + tắt Chrome.
  2. login_get_cookie(): TỰ đăng nhập bằng email|password|2fa (DrissionPage + pyotp).
Cần: DrissionPage, pyotp. QUAN TRỌNG: dùng co.auto_port() để mở Chrome RIÊNG (không đụng Chrome cá nhân).
"""
import time

LABS = "https://labs.google/fx/tools/flow"
GOOGLE_SIGNIN = ("https://accounts.google.com/signin/v2/identifier?"
                 "continue=https%3A%2F%2Flabs.google%2Ffx%2Ftools%2Fflow&flowName=GlifWebSignIn&flowEntry=ServiceLogin")
_KEEP = ("next-auth", "__Secure", "__Host", "_ga", "email")


def _opts(profile_dir=None):
    from DrissionPage import ChromiumOptions
    co = ChromiumOptions()
    co.auto_port()                       # <-- mở Chrome RIÊNG, không đụng Chrome đang mở của user
    co.set_argument("--no-first-run"); co.set_argument("--no-default-browser-check")
    if profile_dir:
        try: co.set_user_data_path(profile_dir)
        except Exception: pass
    return co


def _labs_cookie(cks):
    parts = []
    for c in cks or []:
        if "labs.google" in c.get("domain", "") and any(k in c.get("name", "") for k in _KEEP):
            parts.append(f"{c.get('name')}={c.get('value','')}")
    return "; ".join(parts)


def _totp_now(secret):
    try:
        import pyotp
        return pyotp.TOTP(str(secret).replace(" ", "")).now()
    except Exception:
        return None


# ============ 1) NHẬP THỦ CÔNG: user tự đăng nhập ============
def manual_login(log=print, timeout=360, poll=2):
    """Mở Chrome -> user tự đăng nhập Google + vào Flow. Khi có cookie labs (đã login) -> lấy + TẮT Chrome.
    Trả cookie (str) hoặc None (hết giờ / user đóng)."""
    try:
        from DrissionPage import ChromiumPage
    except Exception:
        log("Thiếu DrissionPage -> chạy SETUP.bat"); return None
    page = None
    try:
        page = ChromiumPage(_opts())
        page.get(LABS)
        log("👉 Đăng nhập Google trong cửa sổ Chrome vừa mở, rồi vào Flow. Tool tự nhận cookie...")
        end = time.time() + timeout
        while time.time() < end:
            try:
                ck = _labs_cookie(page.cookies(all_domains=True))
            except Exception:
                return None   # user đã đóng Chrome
            if ck and "next-auth.session-token" in ck:
                log("✅ Đã nhận cookie -> đóng Chrome.")
                return ck
            time.sleep(poll)
        log("⌛ Hết giờ chờ đăng nhập.")
        return None
    except Exception as e:
        log(f"Lỗi: {e}"); return None
    finally:
        try:
            if page: page.quit()
        except Exception:
            pass


# ============ 2) AUTO LOGIN: email|password|2fa ============
def login_get_cookie(email, password, totp_secret="", profile_dir=None, log=print):
    try:
        from DrissionPage import ChromiumPage
    except Exception:
        log("Thiếu DrissionPage -> chạy SETUP.bat"); return None
    page = None
    try:
        log(f"🔑 Mở Chrome login {email}...")
        page = ChromiumPage(_opts(profile_dir))
        page.get(GOOGLE_SIGNIN)
        time.sleep(2)
        if not ("myaccount.google" in page.url or "labs.google" in page.url):
            e = page.ele("tag:input@type=email", timeout=12) or page.ele("#identifierId", timeout=4)
            if e:
                e.input(email); time.sleep(0.5)
                btn = page.ele("#identifierNext", timeout=5) or page.ele("text:Tiếp theo", timeout=3) or page.ele("text:Next", timeout=3)
                if btn: btn.click()
                time.sleep(3)
            p = page.ele("tag:input@type=password", timeout=14) or page.ele("tag:input@name=Passwd", timeout=4)
            if p:
                p.input(password); time.sleep(0.5)
                btn = page.ele("#passwordNext", timeout=5) or page.ele("text:Tiếp theo", timeout=3) or page.ele("text:Next", timeout=3)
                if btn: btn.click()
                time.sleep(3)
            if totp_secret:
                for _ in range(3):
                    tot = page.ele("tag:input@type=tel", timeout=5) or page.ele("#totpPin", timeout=3)
                    if tot:
                        code = _totp_now(totp_secret)
                        if code:
                            tot.input(code); time.sleep(0.4)
                            btn = page.ele("#totpNext", timeout=4) or page.ele("text:Tiếp theo", timeout=3) or page.ele("text:Next", timeout=3)
                            if btn: btn.click()
                            time.sleep(3)
                        break
                    time.sleep(1.5)
        page.get(LABS); time.sleep(4)
        ck = _labs_cookie(page.cookies(all_domains=True))
        if ck and "next-auth.session-token" in ck:
            log(f"✅ {email}: login xong.")
            return ck
        log(f"⚠️ {email}: chưa lấy được cookie (có thể cần xác minh thủ công).")
        return None
    except Exception as e:
        log(f"login lỗi ({email}): {e}"); return None
    finally:
        try:
            if page: page.quit()
        except Exception:
            pass
