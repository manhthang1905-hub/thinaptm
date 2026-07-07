"""
Thìn Aptm — Tạo VIDEO Google Flow (android_bypass). GUI 3 tab: Tài khoản / Tạo video / Hàng đợi.
Chạy: SETUP.bat (cài đủ) rồi CHAY.bat.
"""
import os, sys, json, time, threading, traceback, queue, random
from concurrent.futures import ThreadPoolExecutor

try:
    import customtkinter as ctk
    from tkinter import filedialog, messagebox
except Exception:
    print("Thiếu customtkinter -> chạy SETUP.bat"); sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import engine as E
try:
    import login as L
except Exception:
    L = None

ACC_FILE = os.path.join(HERE, "accounts.json")
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
ctk.set_appearance_mode("light"); ctk.set_default_color_theme("blue")
AC = "#1a73e8"; AC2 = "#1557b0"; GR = "#00897B"; RD = "#EA4335"; BG = "#f4f6fb"; CARD = "#ffffff"; T1 = "#202124"; T2 = "#5f6368"


def load_accs():
    try: return json.load(open(ACC_FILE, encoding="utf-8"))
    except Exception: return []

def save_accs(a):
    json.dump(a, open(ACC_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

SETTINGS_FILE = os.path.join(HERE, "settings.json")

def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_settings(s):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def clean_filename(s):
    for c in r'\/:*?"<>|':
        s = s.replace(c, "_")
    s = s.replace("\n", " ").replace("\r", " ")
    return s.strip()


def get_unique_out_path(directory, filename, existing_set):
    base_name, ext = os.path.splitext(filename)
    candidate = filename
    counter = 1
    full_path = os.path.join(directory, candidate)
    while os.path.exists(full_path) or full_path in existing_set:
        candidate = f"{base_name}_{counter}{ext}"
        full_path = os.path.join(directory, candidate)
        counter += 1
    return full_path


def _find_brand():
    """Tên tool + logo = file png trong thư mục (vd ThinAptm.png -> 'ThinAptm').
    Ưu tiên png trùng tên thư mục; nếu không có thì lấy png đầu tiên. Không có png -> tên mặc định."""
    try:
        pngs = [f for f in os.listdir(HERE) if f.lower().endswith(".png")]
    except Exception:
        pngs = []
    if not pngs:
        return "Thìn Aptm", None
    folder = os.path.basename(HERE.rstrip("\\/"))
    pick = next((f for f in pngs if os.path.splitext(f)[0].lower() == folder.lower()), pngs[0])
    return os.path.splitext(pick)[0], os.path.join(HERE, pick)


# ============ THAM SỐ ĐỘNG CƠ CHẠY (đo thực từ API Google Flow) ============
WORKERS_PER_ACCOUNT = 20   # số luồng render/tài khoản (cố định) — tốc độ SUBMIT thì AIMD tự điều chỉnh
GEN_ATTEMPTS = 60          # số lần thử submit/1 job trước khi trả job về hàng đợi (throttle hồi nhanh nên kiên nhẫn)
# --- Cổng submit THÍCH ỨNG (AIMD như điều khiển tắc nghẽn TCP): bị throttle -> giảm nhanh; chạy mượt -> tăng dần.
#     Tự tìm tốc độ tối đa của TỪNG account (fresh chạy nhanh, gần cạn tự chậm) -> ra nhiều video nhất mà ít 429.
SUBMIT_START = 3.0         # số submit đồng thời/account BAN ĐẦU
SUBMIT_MIN = 1.0           # sàn (luôn còn 1 submit chạy)
SUBMIT_MAX = 10.0          # trần
SUBMIT_UP_AFTER = 5        # bao nhiêu submit OK liên tiếp thì +1 (tăng cộng — additive increase)
SUBMIT_DOWN = 0.5          # gặp throttle thì nhân giới hạn với số này (giảm nhân — multiplicative decrease)
BYPASS_QUICK = 0.4         # bypass/token trượt -> thử lại NHANH (giây)
THROTTLE_SLEEP = 1.5       # 429 USER_REQUESTS_THROTTLED = giới hạn tốc độ -> nghỉ NGẮN (giây) rồi thử lại, TỰ HỒI
QUOTA_HARD_REST = 6 * 3600 # CHỈ khi HẾT QUOTA THẬT (reason quota/credit/daily) -> cách ly dài, đổi account
AUTH_REST = 1800           # nghỉ 30' khi 401 không cứu được bằng refresh cookie
BEARER_TTL = 1200          # refresh bearer từ cookie sau 20' (bearer Google chết ~30')
JOB_MAX_CYCLES = 40        # 1 job được chuyền/thử tối đa bao nhiêu lượt trước khi bỏ (chống kẹt vô hạn)
POLL_MAX = 60              # số lần poll trạng thái render / job
AUTO_RETRY_ROUNDS = 2      # sau khi chạy xong, TỰ retry các job lỗi thêm bao nhiêu vòng
MAX_REWRITES = 3           # prompt vi phạm -> nhờ Gemini viết lại tối đa bao nhiêu lần trước khi bỏ
# LƯU Ý: model lite (t2v_lite / r2v_lite) MIỄN PHÍ -> không tốn credit -> KHÔNG cách ly theo credit.
# Account chỉ bị throttle (giới hạn tốc độ) và tự hồi; AIMD tự giảm tốc là đủ.


def _dur_label(secs):
    """'6h' / '1.5h' / '30p' cho nhãn hiển thị."""
    if secs >= 3600:
        h = secs / 3600.0
        return f"{int(h)}h" if h == int(h) else f"{h:.1f}h"
    return f"{int(secs // 60)}p"


class AccountState:
    """1 tài khoản trong pool + trạng thái runtime (auth, cooldown, cache ảnh). Nhiều worker dùng chung."""
    def __init__(self, acc):
        self.acc = acc
        self.email = acc.get("email") or acc.get("id") or "?"
        self.cookie = acc.get("cookie") or ""
        self.bearer = None
        self.project = None
        self.ts = 0.0             # thời điểm lấy bearer (để biết khi nào refresh)
        self.resume_at = 0.0      # nghỉ tới thời điểm này (cooldown khi throttle)
        self.rest_reason = ""     # "credit"/"quota" (cạn) | "throttle" | "auth" | "" (đang chạy)
        self.busy = 0             # số worker đang tạo video trên account này (⚡ Đang tạo)
        self._last_thr_log = 0.0  # lần cuối ghi log throttle (giới hạn 1 dòng / 30s / account)
        self.wins = 0
        self.fails = 0
        self.refcache = {}        # ref image path -> media_id (khỏi upload lại khi retry)
        self.lock = threading.Lock()   # serialize refresh-auth + refcache (KHÔNG serialize submit!)
        self.blk = threading.Lock()    # bảo vệ busy counter
        # --- Cổng submit THÍCH ỨNG (AIMD) ---
        self.submit_limit = SUBMIT_START   # số submit đồng thời cho phép (tự điều chỉnh)
        self.inflight = 0                  # số submit đang bay
        self._ok_streak = 0                # số submit OK liên tiếp (để tăng dần)
        self._gate = threading.Condition()

    def busy_inc(self):
        with self.blk: self.busy += 1

    def busy_dec(self):
        with self.blk: self.busy = max(0, self.busy - 1)

    # ---- cổng submit thích ứng: chờ tới lượt, tự nới/thắt theo throttle ----
    def acquire_submit(self, stop_check):
        with self._gate:
            while self.inflight >= int(self.submit_limit):
                if stop_check():
                    return False
                self._gate.wait(0.5)
            self.inflight += 1
            return True

    def release_submit(self):
        with self._gate:
            self.inflight = max(0, self.inflight - 1)
            self._gate.notify()

    def on_submit_ok(self):
        """Submit trót lọt -> tăng dần giới hạn (additive increase) khi đủ chuỗi OK."""
        with self._gate:
            self._ok_streak += 1
            if self._ok_streak >= SUBMIT_UP_AFTER and self.submit_limit < SUBMIT_MAX:
                self.submit_limit = min(SUBMIT_MAX, self.submit_limit + 1)
                self._ok_streak = 0
                self._gate.notify_all()

    def on_throttle(self):
        """Bị throttle -> giảm nhanh giới hạn (multiplicative decrease) để hạ nhiệt."""
        with self._gate:
            self._ok_streak = 0
            self.submit_limit = max(SUBMIT_MIN, self.submit_limit * SUBMIT_DOWN)

    def should_log_throttle(self):
        """True nếu nên ghi 1 dòng log throttle (giới hạn 1 dòng / 30s / account) — tránh ngập log."""
        now = time.time()
        if now - self._last_thr_log > 30:
            self._last_thr_log = now
            return True
        return False

    def rest_remaining(self):
        return max(0.0, self.resume_at - time.time())

    def rest(self, secs, reason=""):
        self.resume_at = time.time() + secs
        self.rest_reason = reason

    def clear_rest(self):
        self.resume_at = 0.0
        self.rest_reason = ""

    def ensure_auth(self, force=False):
        """Bảo đảm bearer còn hạn (refresh TỪ COOKIE, không mở trình duyệt). Trả True nếu có bearer+project."""
        with self.lock:
            if not force and self.bearer and (time.time() - self.ts < BEARER_TTL):
                return True
            b, em = E.bearer_from_cookie(self.cookie)
            if not b:
                return False
            self.bearer = b
            self.ts = time.time()
            if em:
                self.email = em
            if not self.project:
                self.project = E.get_project(self.cookie)
            return bool(self.project)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        # TÊN TOOL + LOGO lấy từ file png trong thư mục: vd ThinAptm.png -> tên "ThinAptm".
        brand, _lp = _find_brand()
        self.title(f"{brand} — Tạo Video Google Flow")
        self.geometry("1080x720"); self.minsize(940, 640); self.configure(fg_color=BG)
        self.accounts = load_accs()
        self.settings = load_settings()
        self.jobs = self.settings.get("jobs", [])           # {type, prompt, ref, aspect, model, out, status}
        # Khi khởi động lại, job nào đang chạy dở (bị ngắt) -> đặt lại "chờ" để chạy lại
        for j in self.jobs:
            if j.get("status") == "đang":
                j["status"] = "chờ"
        # TỰ DỌN hàng đợi cũ khi mở app: bỏ job ĐÃ CÓ VIDEO (out tồn tại) hoặc THIẾU ẢNH GỐC
        # (ổ rời rút / file bị xóa/di chuyển) -> không còn dữ liệu cũ rác trỏ sai chỗ.
        self._startup_clean_msg = ""
        if self.jobs:
            keep = []; n_done = n_miss = 0
            for j in self.jobs:
                o = j.get("out")
                if o and os.path.exists(o):
                    n_done += 1; continue
                r = j.get("ref")
                if j.get("type") == "i2v" and r and not os.path.exists(r):
                    n_miss += 1; continue
                keep.append(j)
            if n_done or n_miss:
                self.jobs = keep
                save_settings({**self.settings, "jobs": self.jobs})   # lưu ngay để lần sau sạch
                self._startup_clean_msg = f"🧹 Tự dọn hàng đợi: bỏ {n_done} job đã có video, {n_miss} job thiếu ảnh gốc."
        self.image_paths = self.settings.get("image_paths", [])
        self.loaded_prompts = self.settings.get("custom_prompts", [])
        self._stop = False; self._running = False
        self.check_vars = []  # BooleanVar cho mỗi job trong hàng đợi
        self._pool_states = []  # AccountState[] của phiên chạy hiện tại (cho panel trạng thái pool)
        # Gemini: viết lại prompt vi phạm (nhiều key, xoay tìm key dùng được)
        self.gemini_keys = self.settings.get("gemini_keys", [])
        self._gemini_bad = set()       # key sai/hết quyền -> loại
        self._gemini_lock = threading.Lock()
        self._gemini_active = []       # danh sách key dùng cho phiên chạy hiện tại

        # Khởi tạo file log.txt và xóa trắng dữ liệu cũ
        self.log_path = os.path.join(HERE, "log.txt")
        try:
            with open(self.log_path, "w", encoding="utf-8") as f:
                f.write(f"--- BẮT ĐẦU PHẦN MỀM ({time.strftime('%Y-%m-%d %H:%M:%S')}) ---\n")
        except Exception as e:
            print(f"Không thể khởi tạo log.txt: {e}")

        self.protocol("WM_DELETE_WINDOW", self._on_closing)
        E.ERROR_LOG_FUNC = self._log

        # ----- SIDEBAR -----
        side = ctk.CTkFrame(self, width=210, corner_radius=0, fg_color="#ffffff"); side.pack(side="left", fill="y")
        side.pack_propagate(False)
        ctk.CTkLabel(side, text=brand, font=("", 20, "bold"), text_color=AC).pack(pady=(22, 2), padx=18, anchor="w")
        ctk.CTkLabel(side, text="Tạo video Google Flow", font=("", 11), text_color=T2).pack(padx=18, anchor="w", pady=(0, 8))
        if _lp:
            try:
                from PIL import Image
                _im = Image.open(_lp); _im.thumbnail((160, 160))
                self._logo = ctk.CTkImage(light_image=_im, size=_im.size)
                ctk.CTkLabel(side, image=self._logo, text="").pack(pady=(4, 14))
            except Exception:
                pass
        else:
            ctk.CTkLabel(side, text="", height=6).pack()
        self.nav = {}
        for key, txt, icon in [("acc", "Tài khoản", "👤"), ("gen", "Tạo video", "🎬"), ("queue", "Hàng đợi", "📋")]:
            b = ctk.CTkButton(side, text=f"  {icon}  {txt}", anchor="w", height=44, corner_radius=8,
                               fg_color="transparent", text_color=T1, hover_color="#eef2fb", font=("", 14),
                               command=lambda k=key: self._show(k))
            b.pack(fill="x", padx=12, pady=3); self.nav[key] = b
        self.lbl_qcount = ctk.CTkLabel(side, text="", font=("", 12, "bold"), text_color=GR); self.lbl_qcount.pack(pady=8)

        # ----- CONTENT -----
        self.content = ctk.CTkFrame(self, fg_color=BG); self.content.pack(side="left", fill="both", expand=True)
        self.frames = {}
        self._build_acc(); self._build_gen(); self._build_queue()
        self._show("acc")
        self.after(2000, self._update_pool)   # panel trạng thái pool video (live)
        if self._startup_clean_msg:
            self._log(self._startup_clean_msg)

    def _show(self, key):
        for f in self.frames.values(): f.pack_forget()
        self.frames[key].pack(fill="both", expand=True, padx=18, pady=16)
        for k, b in self.nav.items():
            b.configure(fg_color=("#e8f0fe" if k == key else "transparent"), text_color=(AC if k == key else T1))

    # ============ TAB TÀI KHOẢN ============
    def _build_acc(self):
        f = ctk.CTkFrame(self.content, fg_color=BG); self.frames["acc"] = f
        card = ctk.CTkFrame(f, fg_color="#0f1b3d", corner_radius=12); card.pack(fill="x")
        ctk.CTkLabel(card, text="Google Flow Accounts", font=("", 17, "bold"), text_color="#fff").pack(side="left", padx=20, pady=16)
        self.lbl_live = ctk.CTkLabel(card, text="0 tài khoản", font=("", 13), text_color="#7ee0c0"); self.lbl_live.pack(side="right", padx=20)
        bar = ctk.CTkFrame(f, fg_color="transparent"); bar.pack(fill="x", pady=10)
        ctk.CTkButton(bar, text="➕ Import (email|pass|2fa)", command=self._import_accs, fg_color=AC, hover_color=AC2, height=34).pack(side="left", padx=(0, 6))
        ctk.CTkButton(bar, text="🖐 Nhập thủ công", command=self._manual_login, fg_color="#3949AB", hover_color="#283593", height=34).pack(side="left", padx=6)
        ctk.CTkButton(bar, text="✔ Check", command=self._check_accs, fg_color=GR, hover_color="#00695C", height=34, width=90).pack(side="left", padx=6)
        ctk.CTkButton(bar, text="🔑 Auto login", command=self._auto_login, fg_color="#00897B", hover_color="#00695C", height=34).pack(side="left", padx=6)
        ctk.CTkButton(bar, text="🗑 Xóa tất cả", command=self._clear_accs, fg_color="#9aa0a6", hover_color="#5f6368", height=34, width=100).pack(side="left", padx=6)
        # Header row
        hdr = ctk.CTkFrame(f, fg_color="#e8eaf6", corner_radius=6, height=32); hdr.pack(fill="x", pady=(4, 0)); hdr.pack_propagate(False)
        for txt, w in [("Dùng", 50), ("#", 30), ("Email", 250), ("Trạng thái", 130), ("Cookie", 70), ("2FA", 50), ("", 70)]:
            ctk.CTkLabel(hdr, text=txt, font=("Consolas", 11, "bold"), text_color=T1, width=w, anchor="w").pack(side="left", padx=(6, 0))
        self.acc_scroll = ctk.CTkScrollableFrame(f, fg_color=CARD, corner_radius=8)
        self.acc_scroll.pack(fill="both", expand=True, pady=(2, 8))
        self.lbl_acc_prog = ctk.CTkLabel(f, text="", font=("", 12), text_color=T2); self.lbl_acc_prog.pack(anchor="w")

        # --- API GEMINI: viết lại prompt vi phạm chính sách (nhiều key, mỗi dòng 1 key) ---
        gcard = ctk.CTkFrame(f, fg_color=CARD, corner_radius=10); gcard.pack(fill="x", pady=(6, 0))
        ctk.CTkLabel(gcard, text="🔑 API Gemini — tự viết lại prompt vi phạm rồi thử lại (mỗi dòng 1 key)",
                     font=("", 12, "bold"), text_color=T1).pack(anchor="w", padx=12, pady=(8, 2))
        self.txt_gemini = ctk.CTkTextbox(gcard, height=54, font=("Consolas", 11))
        self.txt_gemini.pack(fill="x", padx=12, pady=(0, 10))
        if self.gemini_keys:
            self.txt_gemini.insert("1.0", "\n".join(self.gemini_keys))
        self._refresh_acc()

    def _refresh_acc(self):
        for w in self.acc_scroll.winfo_children():
            w.destroy()
        live = sum(1 for a in self.accounts if a.get("cookie") and a.get("status") == "ok")
        self.lbl_live.configure(text=f"{live}/{len(self.accounts)} dùng được")
        for i, a in enumerate(self.accounts):
            if "enabled" not in a: a["enabled"] = True
            st = {"ok": "✅ Hoạt động", "dead": "❌ Chết", "new": "⏳ Chưa login"}.get(a.get("status"), "⏳ Chưa login")
            row_bg = "#ffffff" if i % 2 == 0 else "#f8f9fc"
            row = ctk.CTkFrame(self.acc_scroll, fg_color=row_bg, corner_radius=4, height=30)
            row.pack(fill="x", pady=1); row.pack_propagate(False)
            var = ctk.BooleanVar(value=a.get("enabled", True))
            cb = ctk.CTkCheckBox(row, text="", variable=var, width=40, checkbox_width=18, checkbox_height=18,
                                 command=lambda idx=i, v=var: self._toggle_acc(idx, v))
            cb.pack(side="left", padx=(6, 0))
            ctk.CTkLabel(row, text=str(i + 1), font=("Consolas", 11), width=30, anchor="w", text_color=T2).pack(side="left", padx=(6, 0))
            txt_color = T1 if a.get("enabled", True) else "#bdbdbd"
            ctk.CTkLabel(row, text=(a.get('email') or a.get('id') or '?')[:32], font=("Consolas", 11), width=250, anchor="w", text_color=txt_color).pack(side="left", padx=(6, 0))
            st_color = {"ok": GR, "dead": RD, "new": "#F9A825"}.get(a.get("status"), "#F9A825")
            ctk.CTkLabel(row, text=st, font=("", 11), width=130, anchor="w", text_color=st_color if a.get("enabled", True) else "#bdbdbd").pack(side="left", padx=(6, 0))
            ctk.CTkLabel(row, text='có' if a.get('cookie') else 'không', font=("Consolas", 11), width=70, anchor="w", text_color=T2).pack(side="left", padx=(6, 0))
            ctk.CTkLabel(row, text='có' if a.get('totp') else '-', font=("Consolas", 11), width=50, anchor="w", text_color=T2).pack(side="left", padx=(6, 0))
            ctk.CTkButton(row, text="🗑", width=36, height=24, fg_color="#ef5350", hover_color="#c62828",
                          font=("", 12), corner_radius=4,
                          command=lambda idx=i: self._delete_acc(idx)).pack(side="left", padx=(6, 6))

    def _toggle_acc(self, idx, var):
        if idx < 0 or idx >= len(self.accounts): return
        self.accounts[idx]["enabled"] = var.get()
        save_accs(self.accounts)
        self._refresh_acc()

    def _delete_acc(self, idx):
        if idx < 0 or idx >= len(self.accounts): return
        email = self.accounts[idx].get('email') or self.accounts[idx].get('id') or '?'
        if messagebox.askyesno("Xóa tài khoản", f"Xóa tài khoản '{email}'?"):
            del self.accounts[idx]
            save_accs(self.accounts)
            self._refresh_acc()

    def _import_accs(self):
        dlg = ctk.CTkInputDialog(text="Dán mỗi dòng: email|password|2fa_secret", title="Import tài khoản")
        raw = dlg.get_input()
        if not raw: return
        for line in raw.splitlines():
            p = [x.strip() for x in line.strip().split("|")]
            if p and p[0]:
                self.accounts.append({"id": p[0], "email": p[0], "password": p[1] if len(p) > 1 else "",
                                      "totp": p[2] if len(p) > 2 else "", "cookie": "", "status": "new"})
        save_accs(self.accounts); self._refresh_acc()

    def _manual_login(self):
        if L is None:
            messagebox.showerror("Thiếu thư viện", "Chưa cài DrissionPage. Chạy SETUP.bat trước."); return
        def logp(m):
            self.after(0, lambda: self.lbl_acc_prog.configure(text=m))
            self._log(f"[Manual Login] {m}")
        def work():
            logp("🖐 Đang mở Chrome — hãy đăng nhập Google + vào Flow...")
            ck = L.manual_login(log=logp)
            if ck:
                b, em = E.bearer_from_cookie(ck)
                if b:
                    found = next((a for a in self.accounts if a.get("email") == em), None)
                    if found:
                        found["cookie"] = ck; found["status"] = "ok"; found["email"] = em
                    else:
                        self.accounts.append({"id": em, "email": em, "password": "", "totp": "", "cookie": ck, "status": "ok"})
                    save_accs(self.accounts)
                    self.after(0, lambda: (self._refresh_acc(), logp(f"✅ Đã thêm {em}")))
                else:
                    logp("⚠️ Có cookie nhưng chưa dùng được — thử lại.")
            else:
                logp("Chưa lấy được cookie (chưa đăng nhập xong / đã đóng Chrome).")
        threading.Thread(target=work, daemon=True).start()

    def _clear_accs(self):
        if messagebox.askyesno("Xóa", "Xóa tất cả tài khoản?"):
            self.accounts = []; save_accs(self.accounts); self._refresh_acc()

    def _check_accs(self):
        def work():
            def one(a):
                if a.get("cookie"):
                    b, em = E.bearer_from_cookie(a["cookie"])
                    a["status"] = "ok" if b else "dead"
                    if em: a["email"] = em
                return a
            self.lbl_acc_prog.configure(text="⏳ Đang check...")
            with ThreadPoolExecutor(max_workers=8) as ex:
                list(ex.map(one, [a for a in self.accounts if a.get("cookie")]))
            save_accs(self.accounts)
            self.after(0, lambda: (self._refresh_acc(), self.lbl_acc_prog.configure(text="Check xong")))
        threading.Thread(target=work, daemon=True).start()

    def _auto_login(self):
        if L is None:
            messagebox.showerror("Thiếu thư viện", "Chưa cài DrissionPage. Chạy SETUP.bat trước."); return
        todo = [a for a in self.accounts if a.get("password") and not (a.get("cookie") and a.get("status") == "ok")]
        if not todo:
            messagebox.showinfo("Không cần", "Không có tài khoản cần auto login (đã có cookie hoặc thiếu mật khẩu).\nDùng 'Nhập thủ công' để tự đăng nhập."); return
        def logp(m):
            self.after(0, lambda: self.lbl_acc_prog.configure(text=m))
            self._log(f"[Auto Login] {m}")
        def work():
            for i, a in enumerate(todo, 1):
                if self._stop: break
                logp(f"🔑 [{i}/{len(todo)}] đang login {a.get('email')}...")
                ck = L.login_get_cookie(a["email"], a["password"], a.get("totp", ""),
                                        profile_dir=os.path.join(HERE, "_profiles", a["email"].replace("@", "_")), log=logp)
                if ck:
                    b, em = E.bearer_from_cookie(ck)
                    a["cookie"] = ck; a["status"] = "ok" if b else "dead"
                    if em: a["email"] = em
                else:
                    a["status"] = "dead"
                save_accs(self.accounts); self.after(0, self._refresh_acc)
            logp("✅ Auto login xong.")
        threading.Thread(target=work, daemon=True).start()

    # ============ TAB TẠO VIDEO ============
    def _build_gen(self):
        f = ctk.CTkFrame(self.content, fg_color=BG); self.frames["gen"] = f
        top = ctk.CTkFrame(f, fg_color="transparent"); top.pack(fill="x")
        ctk.CTkLabel(top, text="🎬 Tạo Video", font=("", 20, "bold"), text_color=T1).pack(side="left")
        self.gen_mode = ctk.StringVar(value=self.settings.get("gen_mode", "i2v"))   # MẶC ĐỊNH Image → Video
        ctk.CTkRadioButton(top, text="Image → Video", variable=self.gen_mode, value="i2v", command=self._gen_mode).pack(side="right", padx=(12, 0))
        ctk.CTkRadioButton(top, text="Text → Video", variable=self.gen_mode, value="t2v", command=self._gen_mode).pack(side="right")
        # I2V: thư mục ảnh gốc
        self.r_ref = ctk.CTkFrame(f, fg_color="transparent")
        ctk.CTkLabel(self.r_ref, text="📁 Thư mục ảnh gốc:", width=150, anchor="w").pack(side="left")
        self.ent_ref = ctk.CTkEntry(self.r_ref); self.ent_ref.pack(side="left", fill="x", expand=True, padx=6)
        if "ref_dir" in self.settings:
            self.ent_ref.insert(0, self.settings["ref_dir"])
        ctk.CTkButton(self.r_ref, text="Chọn & Nạp ảnh", width=130, command=self._load_ref_images, fg_color=GR, hover_color="#00695C").pack(side="left")
        # thanh prompt
        rowb = ctk.CTkFrame(f, fg_color="transparent"); rowb.pack(fill="x", pady=(8, 2))
        ctk.CTkButton(rowb, text="📂 Nạp prompt .txt", command=self._load_prompts, fg_color="#5f6368", height=30, width=140).pack(side="left")
        self.lbl_gen_info = ctk.CTkLabel(rowb, text="Mỗi dòng .txt = prompt cho 1 ảnh (theo thứ tự). Sửa trực tiếp bên dưới.", text_color=T2, font=("", 11)); self.lbl_gen_info.pack(side="left", padx=10)
        # BOTTOM: nút thêm + cài đặt (pack trước -> nằm dưới)
        ctk.CTkButton(f, text="➕ Thêm vào hàng đợi", command=self._add_queue, fg_color=AC, hover_color=AC2, height=42, font=("", 15, "bold")).pack(side="bottom", fill="x", pady=(8, 0))
        
        rs = ctk.CTkFrame(f, fg_color=CARD, corner_radius=10); rs.pack(side="bottom", fill="x", pady=8)
        ctk.CTkLabel(rs, text="⚙", font=("", 15)).pack(side="left", padx=(12, 4), pady=10)
        ctk.CTkLabel(rs, text="Tỉ lệ:").pack(side="left")
        self.opt_aspect = ctk.CTkOptionMenu(rs, values=list(E.VID_ASPECTS.keys()), width=140)
        self.opt_aspect.pack(side="left", padx=(4, 12))
        self.opt_aspect.set(self.settings.get("aspect", "Dọc 9:16 (TikTok)"))
        
        ctk.CTkLabel(rs, text="Đặt tên:").pack(side="left")
        self.opt_naming = ctk.CTkOptionMenu(rs, values=["Đặt tên theo ảnh", "13 ký tự đầu prompt", "Số thứ tự (001...)"], width=150)
        self.opt_naming.pack(side="left", padx=(4, 12))
        self.opt_naming.set(self.settings.get("naming", "13 ký tự đầu prompt"))
        
        ctk.CTkLabel(rs, text="Lưu:").pack(side="left")
        self.ent_out = ctk.CTkEntry(rs, width=170)
        self.ent_out.pack(side="left", padx=4)
        if "out_dir" in self.settings:
            self.ent_out.insert(0, self.settings["out_dir"])
        ctk.CTkButton(rs, text="Chọn", width=56, command=lambda: self._pick(self.ent_out)).pack(side="left", padx=(0, 10))
        
        ctk.CTkLabel(rs, text="Veo 3.1 Lite (miễn phí)", font=("", 11, "bold"), text_color=GR).pack(side="left", padx=(0, 12))

        # MIDDLE: 1 ô prompt duy nhất (KHÔNG thumbnail -> nhẹ, chịu 25k ảnh)
        self.txt_prompts = ctk.CTkTextbox(f, font=("Consolas", 11))
        self.ref_images = self.image_paths
        self.ref_promptfile = None
        self._gen_mode()

        # Phục hồi dữ liệu ảnh & prompt đã nạp của phiên trước
        if self.gen_mode.get() == "t2v":
            t2v_p = self.settings.get("t2v_prompts", "")
            if t2v_p:
                self.txt_prompts.insert("1.0", t2v_p)
        else:
            # i2v mode
            # Phục hồi prompt từ bộ nhớ
            if self.loaded_prompts:
                if len(self.loaded_prompts) <= 3000:
                    self.txt_prompts.insert("1.0", "\n".join(self.loaded_prompts))
                else:
                    self.txt_prompts.insert("1.0", f"(Đã nạp {len(self.loaded_prompts)} prompt — file lớn nên không hiển thị.)")
            self._update_gen_info()

    def _gen_mode(self):
        self.txt_prompts.pack_forget(); self.r_ref.pack_forget()
        if self.gen_mode.get() == "i2v":
            self.r_ref.pack(fill="x", pady=(6, 0), after=self.frames["gen"].winfo_children()[0])
        self.txt_prompts.pack(fill="both", expand=True, pady=(4, 0))
        self._update_gen_info()

    def _pick(self, ent):
        d = filedialog.askdirectory()
        if d: ent.delete(0, "end"); ent.insert(0, d)

    def _load_ref_images(self):
        d = filedialog.askdirectory()
        if not d: return
        self.ent_ref.delete(0, "end"); self.ent_ref.insert(0, d)
        # CHỈ liệt kê tên file (nhanh, KHÔNG tạo thumbnail) -> chịu được 25k ảnh không treo
        self.ref_images = [os.path.join(d, x) for x in sorted(os.listdir(d)) if x.lower().endswith(IMG_EXT)]
        self.image_paths = self.ref_images
        self.ref_promptfile = None
        for cand in ("prompt.txt", "prompts.txt"):
            p = os.path.join(d, cand)
            if os.path.exists(p):
                lines = open(p, encoding="utf-8", errors="replace").read().splitlines()
                if len(lines) <= 3000:   # nhỏ -> hiện vào ô để xem/sửa
                    self.txt_prompts.delete("1.0", "end"); self.txt_prompts.insert("1.0", "\n".join(l for l in lines if l.strip()))
                    self.loaded_prompts = [l.strip() for l in lines if l.strip()]
                else:                    # lớn -> chỉ tham chiếu file (không render, tránh treo)
                    self.ref_promptfile = p
                    self.loaded_prompts = [l.strip() for l in lines if l.strip()]
                break
        self._update_gen_info()

    def _update_gen_info(self):
        if self.gen_mode.get() != "i2v":
            self.lbl_gen_info.configure(text="Text → Video: mỗi dòng = 1 video."); return
        n = len(self.ref_images)
        if self.ref_promptfile:
            self.lbl_gen_info.configure(text=f"📁 {n} ảnh · prompt từ {os.path.basename(self.ref_promptfile)} (file lớn — ghép theo thứ tự khi tạo)")
        else:
            self.lbl_gen_info.configure(text=f"📁 {n} ảnh — mỗi dòng prompt bên dưới ghép cho 1 ảnh theo thứ tự (ảnh 1↔dòng 1...)")

    def _load_prompts(self):
        fp = filedialog.askopenfilename(filetypes=[("Text", "*.txt")])
        if not fp: return
        lines = open(fp, encoding="utf-8", errors="replace").read().splitlines()
        self.loaded_prompts = [l.strip() for l in lines if l.strip()]
        if len(lines) <= 3000:
            self.ref_promptfile = None
            self.txt_prompts.delete("1.0", "end"); self.txt_prompts.insert("1.0", "\n".join(l for l in lines if l.strip()))
        else:
            self.ref_promptfile = fp
            self.txt_prompts.delete("1.0", "end")
            self.txt_prompts.insert("1.0", f"(Đã nạp {len(lines)} prompt từ {os.path.basename(fp)} — file lớn nên không hiển thị. Ghép theo thứ tự khi tạo.)")
        self._update_gen_info()

    def _read_prompts(self):
        if self.ref_promptfile:
            return [l.strip() for l in open(self.ref_promptfile, encoding="utf-8", errors="replace").read().splitlines() if l.strip()]
        raw = [l.strip() for l in self.txt_prompts.get("1.0", "end").splitlines() if l.strip() and not l.startswith("(Đã nạp")]
        if raw:
            return raw
        return self.loaded_prompts

    def _add_queue(self):
        out = self.ent_out.get().strip()
        if not out: messagebox.showwarning("Thiếu", "Chọn thư mục lưu."); return
        aspect = E.VID_ASPECTS[self.opt_aspect.get()]; model = "veo_3_1_t2v_lite_low_priority"  # bản miễn phí (I2V engine tự đổi r2v)
        mode = self.gen_mode.get(); base = len(self.jobs); added = 0; skipped = 0
        prompts = self._read_prompts()
        naming = self.opt_naming.get()
        existing_set = {j["out"] for j in self.jobs}

        if mode == "i2v":
            if not self.ref_images: messagebox.showwarning("Thiếu ảnh", "Bấm 'Chọn & Nạp ảnh' để nạp ảnh gốc."); return
            for i, ref in enumerate(self.ref_images):
                pr = prompts[i] if i < len(prompts) else (prompts[-1] if prompts else "")
                if not pr: continue

                # RESUME: đặt tên theo ảnh -> tên output CỐ ĐỊNH = tên ảnh. Rà soát thư mục output:
                # nếu video đã có -> BỎ QUA ảnh này (không làm lại). KHÔNG thêm hậu tố _1 (giữ tên ổn định
                # để lần chạy sau nhận ra "đã xong").
                if naming == "Đặt tên theo ảnh":
                    fn = clean_filename(os.path.splitext(os.path.basename(ref))[0]) or f"{base+added+1:03d}"
                    unique_out = os.path.join(out, fn + ".mp4")
                    if os.path.exists(unique_out):
                        skipped += 1; continue                 # đã có video ở output -> bỏ qua
                    if unique_out in existing_set:
                        continue                               # đã có trong hàng đợi -> bỏ qua
                    existing_set.add(unique_out)
                    self.jobs.append({"type": "i2v", "prompt": pr, "ref": ref, "aspect": aspect, "model": model,
                                      "out": unique_out, "status": "chờ"}); added += 1
                    continue

                # Các chế độ đặt tên khác (không ổn định cho resume) -> giữ hậu tố chống trùng.
                if naming == "13 ký tự đầu prompt":
                    fn = clean_filename(pr[:13])
                else:  # Số thứ tự
                    fn = f"{base+added+1:03d}"
                if not fn:
                    fn = f"{base+added+1:03d}"
                fn = fn + ".mp4"
                unique_out = get_unique_out_path(out, fn, existing_set)
                existing_set.add(unique_out)
                self.jobs.append({"type": "i2v", "prompt": pr, "ref": ref, "aspect": aspect, "model": model,
                                  "out": unique_out, "status": "chờ"}); added += 1
        else:
            for pr in prompts:
                if naming == "Đặt tên theo ảnh" or naming == "13 ký tự đầu prompt":
                    fn = clean_filename(pr[:13])
                else: # Số thứ tự
                    fn = f"{base+added+1:03d}"
                if not fn:
                    fn = f"{base+added+1:03d}"

                fn = fn + ".mp4"
                unique_out = get_unique_out_path(out, fn, existing_set)
                existing_set.add(unique_out)

                self.jobs.append({"type": "t2v", "prompt": pr, "ref": None, "aspect": aspect, "model": model,
                                  "out": unique_out, "status": "chờ"}); added += 1
        if skipped:
            self._log(f"⏭ Bỏ qua {skipped} ảnh đã có video ở thư mục lưu (resume).")
        if not added:
            if skipped:
                messagebox.showinfo("Đã xong", f"Tất cả {skipped} ảnh đã có video ở thư mục lưu — không còn gì để làm.")
            else:
                messagebox.showwarning("Thiếu prompt", "Chưa có prompt.")
            return
        if skipped:
            messagebox.showinfo("Đã thêm", f"Thêm {added} job. Bỏ qua {skipped} ảnh đã có video (resume).")
        self._refresh_queue(force=True); self._show("queue")

    # ============ TAB HÀNG ĐỢI ============
    def _build_queue(self):
        f = ctk.CTkFrame(self.content, fg_color=BG); self.frames["queue"] = f
        st = ctk.CTkFrame(f, fg_color="transparent"); st.pack(fill="x")
        self.stat_lbl = {}
        for key, txt, col in [("tong", "Tổng", "#3949AB"), ("xuly", "Xử lý", "#F9A825"), ("xong", "Xong", GR), ("loi", "Lỗi", RD)]:
            c = ctk.CTkFrame(st, fg_color=CARD, corner_radius=10); c.pack(side="left", expand=True, fill="x", padx=4)
            ctk.CTkLabel(c, text=txt, font=("", 12), text_color=T2).pack(pady=(10, 0))
            lb = ctk.CTkLabel(c, text="0", font=("", 24, "bold"), text_color=col); lb.pack(pady=(0, 10)); self.stat_lbl[key] = lb
        # --- PANEL POOL VIDEO (đồng bộ thiết kế: card trắng + số to màu như ô thống kê trên) ---
        poolcard = ctk.CTkFrame(f, fg_color=CARD, corner_radius=12); poolcard.pack(fill="x", pady=(8, 0))
        ctk.CTkLabel(poolcard, text="🎬  Pool khai thác", font=("", 14, "bold"), text_color=T1).pack(anchor="w", padx=16, pady=(12, 2))
        prow = ctk.CTkFrame(poolcard, fg_color="transparent"); prow.pack(fill="x", padx=10, pady=(2, 4))
        self.pool_stat_lbl = {}
        for key, txt, col in [("acc", "Tài khoản", AC), ("run", "Đang chạy", GR), ("gen", "Đang tạo", "#F9A825"), ("rest", "Nghỉ", T2)]:
            c = ctk.CTkFrame(prow, fg_color=BG, corner_radius=8); c.pack(side="left", expand=True, fill="x", padx=4)
            ctk.CTkLabel(c, text=txt, font=("", 11), text_color=T2).pack(pady=(6, 0))
            lb = ctk.CTkLabel(c, text="0", font=("", 20, "bold"), text_color=col); lb.pack(pady=(0, 6))
            self.pool_stat_lbl[key] = lb
        self.pool_rows_frame = ctk.CTkFrame(poolcard, fg_color="transparent"); self.pool_rows_frame.pack(fill="x", padx=14, pady=(2, 12))
        self._pool_rows = {}          # email -> {nhãn giá trị}
        self._pool_row_sig = None     # chữ ký tập tài khoản (để biết khi nào dựng lại hàng)
        bar = ctk.CTkFrame(f, fg_color="transparent"); bar.pack(fill="x", pady=10)
        self.btn_run = ctk.CTkButton(bar, text="▶ Bắt đầu", command=self._start, fg_color=AC, hover_color=AC2, height=38, width=120, font=("", 14, "bold")); self.btn_run.pack(side="left")
        ctk.CTkButton(bar, text="■ Dừng", command=self._stop_run, fg_color="#5f6368", height=38, width=90).pack(side="left", padx=6)
        ctk.CTkLabel(bar, text="⚡ Tốc độ tự động", font=("", 11), text_color=GR).pack(side="left", padx=(16, 2))
        ctk.CTkButton(bar, text="↻ Retry lỗi", command=self._retry, fg_color="#9aa0a6", height=38, width=100).pack(side="left", padx=(16, 4))
        ctk.CTkButton(bar, text="🗑 Xóa xong", command=self._clear_done, fg_color="#9aa0a6", height=38, width=100).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="🗑 Xóa Vi Phạm CS", command=self._clear_violation, fg_color="#E57373", hover_color="#EF5350", height=38, width=130).pack(side="left", padx=4)

        # --- THANH CHỌN (CHECK) ---
        bar2 = ctk.CTkFrame(f, fg_color=CARD, corner_radius=8); bar2.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(bar2, text="☑ Chọn:", font=("", 12, "bold"), text_color=T1).pack(side="left", padx=(10, 4), pady=6)
        ctk.CTkLabel(bar2, text="Từ dòng:", font=("", 11), text_color=T2).pack(side="left", padx=(4, 2))
        self.ent_check_from = ctk.CTkEntry(bar2, width=60, height=30); self.ent_check_from.pack(side="left", padx=(0, 4))
        self.ent_check_from.insert(0, "1")
        ctk.CTkLabel(bar2, text="Đến dòng:", font=("", 11), text_color=T2).pack(side="left", padx=(4, 2))
        self.ent_check_to = ctk.CTkEntry(bar2, width=60, height=30); self.ent_check_to.pack(side="left", padx=(0, 6))
        ctk.CTkButton(bar2, text="☑ Check", command=self._check_range, fg_color=AC, hover_color=AC2, height=30, width=80, font=("", 11, "bold")).pack(side="left", padx=2)
        ctk.CTkButton(bar2, text="☐ Bỏ chọn", command=self._uncheck_range, fg_color="#9aa0a6", hover_color="#5f6368", height=30, width=90, font=("", 11)).pack(side="left", padx=2)
        ctk.CTkButton(bar2, text="Chọn tất cả", command=self._select_all, fg_color="#3949AB", hover_color="#283593", height=30, width=90, font=("", 11)).pack(side="left", padx=2)
        ctk.CTkButton(bar2, text="Bỏ tất cả", command=self._deselect_all, fg_color="#9aa0a6", hover_color="#5f6368", height=30, width=80, font=("", 11)).pack(side="left", padx=2)
        self.lbl_checked = ctk.CTkLabel(bar2, text="Đã chọn: 0", font=("", 11, "bold"), text_color=AC); self.lbl_checked.pack(side="left", padx=(10, 4))
        ctk.CTkButton(bar2, text="🗑 Xóa đã chọn", command=self._delete_checked, fg_color=RD, hover_color="#c62828", height=30, width=110, font=("", 11, "bold")).pack(side="right", padx=(2, 10))
        ctk.CTkButton(bar2, text="↻ Retry đã chọn", command=self._retry_checked, fg_color=GR, hover_color="#00695C", height=30, width=120, font=("", 11, "bold")).pack(side="right", padx=2)
        ctk.CTkButton(bar2, text="📁 Đổi folder", command=self._change_folder_checked, fg_color="#5C6BC0", hover_color="#3949AB", height=30, width=100, font=("", 11)).pack(side="right", padx=2)
        ctk.CTkButton(bar2, text="✏ Đổi tên", command=self._rename_checked, fg_color="#5C6BC0", hover_color="#3949AB", height=30, width=90, font=("", 11)).pack(side="right", padx=2)

        self.progress = ctk.CTkProgressBar(f); self.progress.pack(fill="x", pady=4); self.progress.set(0)
        self.txt_queue = ctk.CTkTextbox(f, height=250, font=("Consolas", 10)); self.txt_queue.pack(fill="both", expand=True, pady=(6, 6))
        self.txt_log = ctk.CTkTextbox(f, height=110, font=("Consolas", 10), fg_color="#0f1b3d", text_color="#8be9c0"); self.txt_log.pack(fill="x")

        # Phục hồi dữ liệu hàng đợi hiển thị của phiên trước
        self._refresh_queue(force=True)

    def _refresh_queue(self, force=False):
        # THROTTLE: 25k job -> chỉ refresh các ô đếm tối đa 1 lần/giây
        now = time.time()
        if not force and now - getattr(self, "_last_qref", 0) < 1.0:
            return
        self._last_qref = now
        tong = len(self.jobs); xong = loi = xuly = 0
        for j in self.jobs:                      # đếm 1 LẦN
            s = j["status"]
            if s == "xong": xong += 1
            elif s in ("lỗi", "vi phạm cs"): loi += 1
            elif s == "đang": xuly += 1
        self.stat_lbl["tong"].configure(text=str(tong)); self.stat_lbl["xong"].configure(text=str(xong))
        self.stat_lbl["loi"].configure(text=str(loi)); self.stat_lbl["xuly"].configure(text=str(xuly))
        self.lbl_qcount.configure(text=f"Hàng đợi: {tong}")
        if tong: self.progress.set((xong + loi) / tong)

        # Đồng bộ check_vars với số lượng jobs
        while len(self.check_vars) < len(self.jobs):
            self.check_vars.append(ctk.BooleanVar(value=False))
        if len(self.check_vars) > len(self.jobs):
            self.check_vars = self.check_vars[:len(self.jobs)]
        # Cập nhật nhãn đã chọn
        checked_count = sum(1 for v in self.check_vars if v.get())
        try:
            self.lbl_checked.configure(text=f"Đã chọn: {checked_count}")
        except Exception:
            pass

        # Cập nhật ô "Đến dòng" mặc định = tổng số dòng
        try:
            cur_to = self.ent_check_to.get().strip()
            if not cur_to:
                self.ent_check_to.insert(0, str(tong))
        except Exception:
            pass
        
        # Tránh đơ UI khi cập nhật hàng chục ngàn dòng chữ:
        # Chỉ vẽ lại khung Textbox chi tiết khi force=True hoặc sau mỗi 5 giây trong lúc đang chạy
        is_running = getattr(self, "_running", False)
        if not force and is_running and now - getattr(self, "_last_txt_ref", 0) < 5.0:
            return
        self._last_txt_ref = now

        self.txt_queue.configure(state="normal")
        self.txt_queue.delete("1.0", "end")
        # Cấu hình tag màu (chỉ 1 lần)
        self.txt_queue.tag_config("dang", foreground="#E53935")      # đỏ — đang chạy
        self.txt_queue.tag_config("xong", foreground="#2E7D32")      # xanh lá — thành công
        self.txt_queue.tag_config("loi", foreground="#E65100")        # cam đậm — lỗi
        self.txt_queue.tag_config("vipham", foreground="#AD1457")     # hồng đậm — vi phạm cs
        self.txt_queue.tag_config("cho", foreground="#555555")        # xám — chờ

        def _fmt(i, j):
            chk = "☑" if (i-1 < len(self.check_vars) and self.check_vars[i-1].get()) else "☐"
            ic = {"chờ": "⏳", "đang": "🔄", "xong": "✅", "lỗi": "❌", "vi phạm cs": "⚠️"}.get(j["status"], "")
            return f"{chk} {i:<5}{('T2V' if j['type']=='t2v' else 'I2V'):<5}{ic+' '+j['status']:<11}{os.path.basename(j['out']):<14}{j['prompt'][:48]}"

        header = f"Hàng đợi: {tong} job · Xong {xong} · Lỗi {loi}\n" + "-" * 90
        MAX_SHOW = 300  # Giới hạn hiển thị để UI không đơ

        if tong <= MAX_SHOW:
            # Đủ nhỏ → hiển thị toàn bộ
            lines = [header]
            tags_map = [None]  # header không cần tag
            for i, j in enumerate(self.jobs, 1):
                lines.append(_fmt(i, j))
                tags_map.append({"đang": "dang", "xong": "xong", "lỗi": "loi", "vi phạm cs": "vipham"}.get(j["status"], "cho"))
        else:
            # Quá nhiều → hiển thị thông minh: đang chạy + lỗi + đầu/cuối
            lines = [header]
            tags_map = [None]
            # 1) Jobs đang chạy (ưu tiên cao nhất)
            running = [(i, j) for i, j in enumerate(self.jobs, 1) if j["status"] == "đang"]
            if running:
                lines.append(f"\n━━━ ĐANG CHẠY ({len(running)}) ━━━")
                tags_map.append(None)
                for i, j in running:
                    lines.append(_fmt(i, j))
                    tags_map.append("dang")
            # 2) Jobs lỗi / vi phạm (cần chú ý)
            errors = [(i, j) for i, j in enumerate(self.jobs, 1) if j["status"] in ("lỗi", "vi phạm cs")]
            if errors:
                lines.append(f"\n━━━ LỖI ({len(errors)}) ━━━")
                tags_map.append(None)
                for i, j in errors[:50]:  # Giới hạn 50 lỗi
                    lines.append(_fmt(i, j))
                    tags_map.append("loi" if j["status"] == "lỗi" else "vipham")
                if len(errors) > 50:
                    lines.append(f"  ... và {len(errors) - 50} lỗi khác")
                    tags_map.append(None)
            # 3) 100 dòng đầu + 100 dòng cuối
            show_head = 100; show_tail = 100
            lines.append(f"\n━━━ DANH SÁCH (hiện {show_head} đầu + {show_tail} cuối / {tong} job) ━━━")
            tags_map.append(None)
            for i, j in enumerate(self.jobs[:show_head], 1):
                lines.append(_fmt(i, j))
                tags_map.append({"đang": "dang", "xong": "xong", "lỗi": "loi", "vi phạm cs": "vipham"}.get(j["status"], "cho"))
            if tong > show_head + show_tail:
                lines.append(f"  ... ẩn {tong - show_head - show_tail} dòng giữa ...")
                tags_map.append(None)
            for idx in range(max(show_head, tong - show_tail), tong):
                i = idx + 1; j = self.jobs[idx]
                lines.append(_fmt(i, j))
                tags_map.append({"đang": "dang", "xong": "xong", "lỗi": "loi", "vi phạm cs": "vipham"}.get(j["status"], "cho"))

        # Insert toàn bộ 1 lần (nhanh hơn insert từng dòng rất nhiều)
        full_text = "\n".join(lines)
        self.txt_queue.insert("1.0", full_text)
        # Apply tag màu theo từng dòng (bắt đầu từ dòng 1 trong textbox)
        for line_idx, tag in enumerate(tags_map):
            if tag:
                self.txt_queue.tag_add(tag, f"{line_idx+1}.0", f"{line_idx+1}.end")

    def _update_pool(self):
        """Panel POOL VIDEO (cập nhật mỗi 2s): 4 ô tổng quan + bảng tài khoản. Tốc độ TỰ ĐỘNG (AIMD)."""
        try:
            states = getattr(self, "_pool_states", None) or []
            total = len(states)
            resting = sum(1 for s in states if s.rest_remaining() > 0)
            running = total - resting
            generating = sum(1 for s in states if getattr(s, "busy", 0) > 0)
            self.pool_stat_lbl["acc"].configure(text=str(total))
            self.pool_stat_lbl["run"].configure(text=str(running))
            self.pool_stat_lbl["gen"].configure(text=str(generating))
            self.pool_stat_lbl["rest"].configure(text=str(resting))

            # Dựng lại bảng tài khoản khi tập tài khoản thay đổi (mỗi phiên chạy 1 lần)
            sig = tuple(s.email for s in states)
            if sig != self._pool_row_sig:
                self._pool_row_sig = sig
                for w in self.pool_rows_frame.winfo_children():
                    w.destroy()
                self._pool_rows = {}
                if not states:
                    ctk.CTkLabel(self.pool_rows_frame, text="Chưa chạy — bấm ▶ Bắt đầu.",
                                 font=("", 11), text_color=T2).pack(anchor="w", pady=6)
                else:
                    cols = [("Tài khoản", 160), ("✅ Xong", 70), ("❌ Lỗi", 60),
                            ("⚡ Tạo", 60), ("🚀 Tốc độ", 80), ("Trạng thái", 130)]
                    hdr = ctk.CTkFrame(self.pool_rows_frame, fg_color="transparent"); hdr.pack(fill="x", pady=(0, 2))
                    for txt, w in cols:
                        ctk.CTkLabel(hdr, text=txt, font=("", 10, "bold"), text_color=T2, width=w, anchor="w").pack(side="left", padx=(2, 0))
                    for i, s in enumerate(states):
                        row = ctk.CTkFrame(self.pool_rows_frame, fg_color=("#f6f8fc" if i % 2 else CARD), corner_radius=6)
                        row.pack(fill="x", pady=1)
                        ctk.CTkLabel(row, text=str(s.email).split("@")[0][:22], font=("", 11), text_color=T1, width=160, anchor="w").pack(side="left", padx=(2, 0))
                        wl = ctk.CTkLabel(row, text="0", font=("", 11, "bold"), text_color=GR, width=70, anchor="w"); wl.pack(side="left", padx=(2, 0))
                        fl = ctk.CTkLabel(row, text="0", font=("", 11), text_color=RD, width=60, anchor="w"); fl.pack(side="left", padx=(2, 0))
                        bl = ctk.CTkLabel(row, text="0", font=("", 11), text_color=T1, width=60, anchor="w"); bl.pack(side="left", padx=(2, 0))
                        rl = ctk.CTkLabel(row, text="0", font=("", 11), text_color=AC, width=80, anchor="w"); rl.pack(side="left", padx=(2, 0))
                        sl = ctk.CTkLabel(row, text="", font=("", 11), text_color=GR, width=130, anchor="w"); sl.pack(side="left", padx=(2, 0))
                        self._pool_rows[s.email] = {"w": wl, "f": fl, "b": bl, "r": rl, "s": sl}

            # Cập nhật giá trị từng tài khoản
            for s in states:
                r = self._pool_rows.get(s.email)
                if not r:
                    continue
                r["w"].configure(text=str(s.wins))
                r["f"].configure(text=str(s.fails))
                r["b"].configure(text=str(s.busy))
                r["r"].configure(text=str(int(s.submit_limit)))
                rem = s.rest_remaining()
                if rem > 0:
                    if s.rest_reason == "quota":
                        r["s"].configure(text=f"⛔ cách ly {int(rem//60)}p", text_color=RD)
                    else:
                        r["s"].configure(text=f"😴 nghỉ {int(rem)}s", text_color="#F9A825")
                else:
                    r["s"].configure(text="🟢 đang chạy", text_color=GR)
        except Exception:
            pass
        finally:
            self.after(2000, self._update_pool)

    def _rewrite_prompt(self, prompt):
        """Xoay qua các key Gemini còn tốt, nhờ viết lại prompt vi phạm. Trả prompt mới hoặc None.
        Key sai/hết quyền (dead) -> loại; key bận/hết quota (busy) -> thử key kế."""
        with self._gemini_lock:
            keys = [k for k in self._gemini_active if k not in self._gemini_bad]
        for k in keys:
            status, text = E.rewrite_prompt(k, prompt)
            if status == "ok" and text:
                return text
            if status == "dead":
                with self._gemini_lock:
                    self._gemini_bad.add(k)
        return None

    def _log(self, m):
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {m}\n")
        except Exception:
            pass
        self.after(0, lambda: (self.txt_log.insert("end", m + "\n"), self.txt_log.see("end")))

    def _stop_run(self): self._stop = True; self._log("⏹ Đang dừng...")
    def _retry(self):
        for j in self.jobs:
            if j["status"] == "lỗi": j["status"] = "chờ"
        self._refresh_queue(force=True)
    def _clear_done(self):
        self.jobs = [j for j in self.jobs if j["status"] != "xong"]
        self.check_vars = []; self._refresh_queue(force=True)
    def _clear_violation(self):
        self.jobs = [j for j in self.jobs if j["status"] != "vi phạm cs"]
        self.check_vars = []; self._refresh_queue(force=True)

    # --- CÁC HÀM CHECK / CHỌN DÒNG ---
    def _check_range(self):
        """Check (chọn) các dòng từ 'Từ dòng' đến 'Đến dòng'."""
        try:
            fr = int(self.ent_check_from.get().strip() or "1")
            to_val = self.ent_check_to.get().strip()
            to = int(to_val) if to_val else len(self.jobs)
        except ValueError:
            messagebox.showwarning("Lỗi", "Nhập số dòng hợp lệ."); return
        fr = max(1, fr); to = min(to, len(self.jobs))
        if fr > to:
            messagebox.showwarning("Lỗi", f"Từ dòng ({fr}) phải ≤ Đến dòng ({to})."); return
        for i in range(fr - 1, to):
            if i < len(self.check_vars):
                self.check_vars[i].set(True)
        self._refresh_queue(force=True)

    def _uncheck_range(self):
        """Bỏ chọn các dòng từ 'Từ dòng' đến 'Đến dòng'."""
        try:
            fr = int(self.ent_check_from.get().strip() or "1")
            to_val = self.ent_check_to.get().strip()
            to = int(to_val) if to_val else len(self.jobs)
        except ValueError:
            messagebox.showwarning("Lỗi", "Nhập số dòng hợp lệ."); return
        fr = max(1, fr); to = min(to, len(self.jobs))
        for i in range(fr - 1, to):
            if i < len(self.check_vars):
                self.check_vars[i].set(False)
        self._refresh_queue(force=True)

    def _select_all(self):
        for v in self.check_vars: v.set(True)
        self._refresh_queue(force=True)

    def _deselect_all(self):
        for v in self.check_vars: v.set(False)
        self._refresh_queue(force=True)

    def _delete_checked(self):
        """Xóa các job đã được check (chọn)."""
        indices = [i for i, v in enumerate(self.check_vars) if v.get()]
        if not indices:
            messagebox.showinfo("Không có", "Chưa chọn dòng nào."); return
        if not messagebox.askyesno("Xóa", f"Xóa {len(indices)} job đã chọn?"):
            return
        # Xóa từ cuối lên để không bị lệch index
        for i in sorted(indices, reverse=True):
            if i < len(self.jobs):
                del self.jobs[i]
        self.check_vars = []
        self._refresh_queue(force=True)
        self._log(f"🗑 Đã xóa {len(indices)} job đã chọn.")

    def _retry_checked(self):
        """Retry (chạy lại) các job đã được check mà có status lỗi hoặc vi phạm cs."""
        indices = [i for i, v in enumerate(self.check_vars) if v.get()]
        if not indices:
            messagebox.showinfo("Không có", "Chưa chọn dòng nào."); return
        count = 0
        for i in indices:
            if i < len(self.jobs) and self.jobs[i]["status"] in ("lỗi", "vi phạm cs", "xong", "chờ"):
                self.jobs[i]["status"] = "chờ"
                count += 1
        # Bỏ chọn sau khi retry
        for v in self.check_vars: v.set(False)
        self._refresh_queue(force=True)
        self._log(f"↻ Retry {count} job đã chọn.")

    def _change_folder_checked(self):
        """Đổi thư mục output cho các job đã chọn."""
        indices = [i for i, v in enumerate(self.check_vars) if v.get()]
        if not indices:
            messagebox.showinfo("Không có", "Chưa chọn dòng nào."); return
        new_dir = filedialog.askdirectory(title="Chọn thư mục output mới")
        if not new_dir: return
        count = 0
        for i in indices:
            if i < len(self.jobs):
                old_name = os.path.basename(self.jobs[i]["out"])
                self.jobs[i]["out"] = os.path.join(new_dir, old_name)
                count += 1
        self._refresh_queue(force=True)
        self._log(f"📁 Đã đổi folder cho {count} job → {new_dir}")

    def _rename_checked(self):
        """Đổi tên file output cho các job đã chọn theo quy tắc đặt tên hiện tại."""
        indices = [i for i, v in enumerate(self.check_vars) if v.get()]
        if not indices:
            messagebox.showinfo("Không có", "Chưa chọn dòng nào."); return
        naming = self.opt_naming.get()
        existing_set = {self.jobs[i]["out"] for i in range(len(self.jobs)) if i not in set(indices)}
        count = 0
        for i in indices:
            if i >= len(self.jobs): continue
            j = self.jobs[i]
            out_dir = os.path.dirname(j["out"])
            if naming == "Đặt tên theo ảnh" and j.get("ref"):
                fn_base = os.path.splitext(os.path.basename(j["ref"]))[0]
                fn = clean_filename(fn_base)
            elif naming == "13 ký tự đầu prompt":
                fn = clean_filename(j["prompt"][:13])
            else:  # Số thứ tự
                fn = f"{i+1:03d}"
            if not fn:
                fn = f"{i+1:03d}"
            fn = fn + ".mp4"
            new_out = get_unique_out_path(out_dir, fn, existing_set)
            existing_set.add(new_out)
            j["out"] = new_out
            count += 1
        self._refresh_queue(force=True)
        self._log(f"✏ Đã đổi tên {count} job theo '{naming}'")

    def _start(self):
        if self._running: return
        accs = [a for a in self.accounts if a.get("cookie") and a.get("status") == "ok" and a.get("enabled", True)]
        if not accs: messagebox.showwarning("Thiếu tài khoản", "Vào tab Tài khoản, thêm + Check/Chuẩn bị."); return
        # Nếu có dòng đang được check → chỉ chạy các dòng đã check
        checked_indices = [i for i, v in enumerate(self.check_vars) if v.get()]
        if checked_indices:
            todo = [self.jobs[i] for i in checked_indices if i < len(self.jobs) and self.jobs[i]["status"] in ("chờ", "lỗi")]
            if not todo: messagebox.showinfo("Trống", "Các dòng đã chọn không có job chờ/lỗi."); return
            self._log(f"▶ Chạy {len(todo)} job đã chọn (từ {checked_indices[0]+1} đến {checked_indices[-1]+1})")
        else:
            todo = [j for j in self.jobs if j["status"] in ("chờ", "lỗi")]
            if not todo: messagebox.showinfo("Trống", "Không có job chờ."); return
        wpa = WORKERS_PER_ACCOUNT   # số luồng render/tài khoản cố định; tốc độ submit do AIMD tự chỉnh
        # Chốt danh sách key Gemini cho phiên chạy (mỗi dòng 1 key) + reset key hỏng
        self._gemini_active = [l.strip() for l in self.txt_gemini.get("1.0", "end").splitlines() if l.strip()]
        self._gemini_bad = set()
        if self._gemini_active:
            self._log(f"🔑 Gemini: {len(self._gemini_active)} key — sẽ tự viết lại prompt vi phạm.")
        self._stop = False; self._running = True
        self.btn_run.configure(state="disabled")
        threading.Thread(target=self._run, args=(accs, todo, wpa), daemon=True).start()

    def _run(self, accs, todo, wpa):
        """Mô hình veo3top: 1 HÀNG ĐỢI CHUNG + mỗi tài khoản chạy wpa worker, tất cả pull từ hàng đợi chung.
        Account throttle -> nghỉ (cooldown), account khác gánh; job requeue. Submit KHÔNG khóa/không sleep —
        poll inline tự giãn nhịp (worker bận ~60-90s/video), tận dụng render server-side song song."""
        try:
            # ---- Chuẩn bị auth từng tài khoản (refresh bearer từ cookie, không mở trình duyệt) ----
            self._log(f"🔑 Chuẩn bị {len(accs)} tài khoản...")
            states = []
            for a in accs:
                st = AccountState(a)
                if st.ensure_auth(force=True):
                    states.append(st)
                    self._log(f"  ✅ {st.email[:20]} sẵn sàng (project {str(st.project)[:8]})")
                else:
                    self._log(f"  ⚠️ {a.get('email')}: cookie/project lỗi -> bỏ qua")
            if not states:
                self._log("❌ Không tài khoản dùng được."); return
            self._pool_states = states   # cho panel trạng thái pool đọc (live)

            total = len(states) * wpa
            self._log(f"🚀 {len(states)} tài khoản × {wpa} luồng = {total} luồng. Bắt đầu {len(todo)} job.")

            jobq = queue.Queue()
            for j in todo:
                j["_cycles"] = 0
                jobq.put(j)
            done_flag = [False]

            def process(st, job):
                """Trả 'success' | 'retry_soft' (đổi account) | ('fail', reason)."""
                if not st.ensure_auth():
                    st.rest(AUTH_REST, "auth"); return "retry_soft"
                bearer, project, cookie = st.bearer, st.project, st.cookie
                seed = (abs(hash(job["prompt"])) % 900000) + 1
                aspect, model = job["aspect"], job["model"]

                # 1) Upload ảnh reference (I2V) -> media_id, cache theo account (khỏi upload lại khi retry)
                ref_mid = None
                if job["type"] == "i2v" and job.get("ref"):
                    if not os.path.exists(job["ref"]):
                        return ("fail", "noimg")   # ảnh gốc không đọc được (ổ rời rút / file bị xóa) -> bỏ gọn, KHÔNG retry
                    with st.lock:
                        ref_mid = st.refcache.get(job["ref"])
                    if not ref_mid:
                        ref_mid = E.upload_image(bearer, project, job["ref"])
                        if not ref_mid and st.ensure_auth(force=True):   # có thể 401 -> refresh + thử lại 1 lần
                            bearer, project = st.bearer, st.project
                            ref_mid = E.upload_image(bearer, project, job["ref"])
                        if not ref_mid:
                            return ("fail", "upload ảnh lỗi")
                        with st.lock:
                            st.refcache[job["ref"]] = ref_mid

                # 2) Generate — cổng submit THÍCH ỨNG (tự nới/thắt theo throttle), phân loại lỗi để xử lý ĐÚNG
                for attempt in range(GEN_ATTEMPTS):
                    if self._stop: return "retry_soft"
                    if not st.acquire_submit(lambda: self._stop):
                        return "retry_soft"
                    try:
                        kind, ops = E.submit_video(bearer, project, job["prompt"], seed, aspect, model, ref_mid)
                    finally:
                        st.release_submit()
                    if kind == "ok":
                        st.on_submit_ok()                         # trót lọt -> nới dần tốc độ (AIMD +)
                        pk, mid, _ = E.poll_video(bearer, ops, max_attempts=POLL_MAX, interval=8)
                        if pk == "done":
                            n = E.download_video(mid, cookie, job["out"])
                            if n <= 0:                          # tải hụt -> thử lại vài lần (refresh cookie nếu cần)
                                for _ in range(4):
                                    if self._stop: return "retry_soft"
                                    time.sleep(3); n = E.download_video(mid, cookie, job["out"])
                                    if n > 0: break
                            if n > 0:
                                self._log(f"  ✅ {os.path.basename(job['out'])} ({n//1024}KB) [{st.email[:16]}]")
                                return "success"
                            return ("fail", "tải video lỗi")
                        elif pk == "failed":
                            m = mid or ""
                            if "FILTER" in m or "PROMINENT_PEOPLE" in m:   # lỗi lọc nội dung (vi phạm chính sách)
                                # Có key Gemini -> nhờ VIẾT LẠI prompt cho an toàn rồi thử lại (đến khi ra video).
                                if self._gemini_active and job.get("_rewrites", 0) < MAX_REWRITES:
                                    new = self._rewrite_prompt(job["prompt"])
                                    if new and new.strip() != job["prompt"].strip():
                                        job["_rewrites"] = job.get("_rewrites", 0) + 1
                                        self._log(f"  ✏️ Viết lại prompt vi phạm (lần {job['_rewrites']}) -> thử lại: {new[:40]}…")
                                        job["prompt"] = new
                                        return "retry_soft"   # requeue, làm lại với prompt mới
                                self._log(f"  ⚠️ Vi phạm chính sách: {job['prompt'][:30]} ({m})")
                                return ("fail", "policy")
                            self._log(f"  ❌ render fail: {job['prompt'][:30]} ({m})")
                            return ("fail", m or "render fail")
                        elif pk == "auth":
                            if st.ensure_auth(force=True): bearer = st.bearer
                            continue
                        else:  # timeout
                            return ("fail", "render timeout")
                    elif kind == "auth":
                        if attempt == 0 and st.ensure_auth(force=True):
                            bearer, project = st.bearer, st.project; continue
                        st.rest(AUTH_REST, "auth")
                        self._log(f"  🔒 {st.email[:16]} 401 -> nghỉ {AUTH_REST//60}p, đổi tài khoản.")
                        return "retry_soft"
                    elif kind == "throttle":
                        # GIỚI HẠN TỐC ĐỘ (USER_REQUESTS_THROTTLED) -> tự GIẢM tốc độ submit + nghỉ ngắn, TỰ HỒI.
                        st.on_throttle()                          # AIMD - : giảm nhanh giới hạn submit
                        if st.should_log_throttle():
                            self._log(f"  ⏳ {st.email[:16]}: 429 GIỚI HẠN TỐC ĐỘ — tự giảm tốc (còn {int(st.submit_limit)} luồng submit), sẽ hồi.")
                        time.sleep(THROTTLE_SLEEP + random.uniform(0, 1.0))
                    elif kind == "quota_hard":
                        # HẾT QUOTA THẬT (reason quota/credit/daily) -> cách ly DÀI + đổi account (grind vô ích).
                        st.rest(QUOTA_HARD_REST, "quota")
                        self._log(f"  ⛔ {st.email[:16]} HẾT QUOTA -> cách ly {_dur_label(QUOTA_HARD_REST)}, đổi tài khoản.")
                        return "retry_soft"
                    elif kind in ("ratelimit", "ip_block"):
                        st.on_throttle()
                        if st.should_log_throttle():
                            self._log(f"  🌐 {st.email[:16]}: 429 rate theo IP — tự giảm tốc.")
                        time.sleep(1.5 + random.uniform(0, 1.0))
                    else:  # unusual / retry -> bypass trượt lượt, thử lại NHANH
                        time.sleep(BYPASS_QUICK + random.uniform(0, 0.4))
                return "retry_soft"   # hết lượt thử -> trả job về hàng đợi (không đổ lỗi account)

            def worker(st):
                while not self._stop:
                    w = st.rest_remaining()
                    if w > 0:
                        time.sleep(min(w, 3)); continue        # account đang nghỉ -> không pull job
                    try:
                        job = jobq.get(timeout=2)
                    except queue.Empty:
                        if done_flag[0]: return
                        continue
                    if job.get("status") == "xong":
                        continue
                    if os.path.exists(job["out"]):
                        job["status"] = "xong"; self.after(0, self._refresh_queue); continue
                    job["_cycles"] = job.get("_cycles", 0) + 1
                    if job["_cycles"] > JOB_MAX_CYCLES:
                        job["status"] = "lỗi"; self.after(0, self._refresh_queue); continue
                    job["status"] = "đang"; self.after(0, self._refresh_queue)
                    st.busy_inc()
                    try:
                        outcome = process(st, job)
                    except Exception as e:
                        self._log(f"  ❌ Lỗi bất ngờ [{job['prompt'][:30]}]: {e}")
                        outcome = ("fail", str(e))
                    finally:
                        st.busy_dec()
                    if outcome == "success":
                        job["status"] = "xong"; st.wins += 1; st.clear_rest()
                    elif outcome == "retry_soft":
                        job["status"] = "chờ"; jobq.put(job)   # requeue -> account SỐNG khác nhặt
                    else:
                        st.fails += 1
                        reason = outcome[1] if isinstance(outcome, tuple) and len(outcome) > 1 else "lỗi"
                        if reason == "policy":
                            job["status"] = "vi phạm cs"        # vi phạm chính sách -> không retry
                        elif reason == "noimg":
                            job["status"] = "lỗi"; job["_noretry"] = True   # thiếu ảnh gốc -> không retry vô ích
                        else:
                            job["status"] = "lỗi"
                    self.after(0, self._refresh_queue)

            threads = []
            for st in states:
                for _ in range(wpa):
                    t = threading.Thread(target=worker, args=(st,), daemon=True)
                    t.start(); threads.append(t)

            def _drain():
                while not self._stop:
                    if all(j["status"] in ("xong", "lỗi", "vi phạm cs") for j in todo):
                        return
                    time.sleep(1.5)

            # Chờ tới khi mọi job kết thúc (xong/lỗi/vi phạm) hoặc user bấm Dừng
            _drain()

            # TỰ RETRY job lỗi sau khi chạy xong (bỏ qua vi phạm cs + thiếu ảnh — retry vô ích).
            for rnd in range(AUTO_RETRY_ROUNDS):
                if self._stop:
                    break
                retry = [j for j in todo if j["status"] == "lỗi" and not j.get("_noretry")]
                if not retry:
                    break
                self._log(f"↻ Tự retry {len(retry)} job lỗi (vòng {rnd+1}/{AUTO_RETRY_ROUNDS})...")
                for j in retry:
                    j["status"] = "chờ"; j["_cycles"] = 0; jobq.put(j)   # worker vẫn sống -> nhặt lại
                self.after(0, lambda: self._refresh_queue(force=True))
                _drain()

            done_flag[0] = True
            for t in threads:
                t.join(timeout=5)

            done = sum(1 for j in todo if j["status"] == "xong")
            err = sum(1 for j in todo if j["status"] == "lỗi")
            noimg = sum(1 for j in todo if j["status"] == "lỗi" and j.get("_noretry"))
            self._log(f"🎉 XONG hàng đợi. Thành công {done}/{len(todo)} · lỗi {err}"
                      + (f" (trong đó {noimg} thiếu ảnh gốc)" if noimg else "")
                      + (" (đã dừng)" if self._stop else "") + ".")
            for st in states:
                self._log(f"   [{st.email[:20]}] xong {st.wins} · lỗi {st.fails}")
            self.after(0, lambda: self._refresh_queue(force=True))
        except Exception:
            self._log("LỖI: " + traceback.format_exc())
        finally:
            self._running = False
            self.after(0, lambda: self.btn_run.configure(state="normal"))

    def _on_closing(self):
        try:
            # Lấy prompt của chế độ i2v (từ giao diện hoặc từ bộ nhớ)
            raw_prompts = [l.strip() for l in self.txt_prompts.get("1.0", "end").splitlines() if l.strip() and not l.startswith("(Đã nạp")]
            if raw_prompts:
                custom_prompts = raw_prompts
            else:
                custom_prompts = self.loaded_prompts

            s = {
                "gen_mode": self.gen_mode.get(),
                "ref_dir": self.ent_ref.get(),
                "aspect": self.opt_aspect.get(),
                "naming": self.opt_naming.get(),
                "out_dir": self.ent_out.get(),
                "gemini_keys": [l.strip() for l in self.txt_gemini.get("1.0", "end").splitlines() if l.strip()],
                "image_paths": self.image_paths,
                "custom_prompts": custom_prompts,
                "t2v_prompts": self.txt_prompts.get("1.0", "end-1c") if self.gen_mode.get() == "t2v" else "",
                "jobs": self.jobs
            }
            save_settings(s)
        except Exception as e:
            self._log(f"Lỗi lưu cài đặt: {e}")
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
