"""
Thìn Aptm — Tạo VIDEO Google Flow (android_bypass). GUI 3 tab: Tài khoản / Tạo video / Hàng đợi.
Chạy: SETUP.bat (cài đủ) rồi CHAY.bat.
"""
import os, sys, json, time, threading, traceback
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


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Thìn Aptm — Tạo Video Google Flow")
        self.geometry("1080x720"); self.minsize(940, 640); self.configure(fg_color=BG)
        self.accounts = load_accs()
        self.jobs = []           # {type, prompt, ref, aspect, model, out, status}
        self._stop = False; self._running = False

        # ----- SIDEBAR -----
        side = ctk.CTkFrame(self, width=210, corner_radius=0, fg_color="#ffffff"); side.pack(side="left", fill="y")
        side.pack_propagate(False)
        ctk.CTkLabel(side, text="🐉 Thìn Aptm", font=("", 20, "bold"), text_color=AC).pack(pady=(22, 2), padx=18, anchor="w")
        ctk.CTkLabel(side, text="Tạo video Google Flow", font=("", 11), text_color=T2).pack(padx=18, anchor="w", pady=(0, 8))
        # LOGO cá nhân hóa: bỏ ảnh tên logo.png vào folder tool là tự hiện
        _lp = os.path.join(HERE, "logo.png")
        if os.path.exists(_lp):
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
        self.txt_acc = ctk.CTkTextbox(f, height=340, font=("Consolas", 11)); self.txt_acc.pack(fill="both", expand=True, pady=(4, 8))
        self.lbl_acc_prog = ctk.CTkLabel(f, text="", font=("", 12), text_color=T2); self.lbl_acc_prog.pack(anchor="w")
        self._refresh_acc()

    def _refresh_acc(self):
        self.txt_acc.delete("1.0", "end")
        live = sum(1 for a in self.accounts if a.get("cookie") and a.get("status") == "ok")
        self.lbl_live.configure(text=f"{live}/{len(self.accounts)} dùng được")
        self.txt_acc.insert("end", f"{'#':<4}{'Email':<34}{'Trạng thái':<16}{'Có cookie':<10}{'2FA':<6}\n")
        self.txt_acc.insert("end", "-" * 74 + "\n")
        for i, a in enumerate(self.accounts, 1):
            st = {"ok": "✅ Hoạt động", "dead": "❌ Chết", "new": "⏳ Chưa login"}.get(a.get("status"), "⏳ Chưa login")
            self.txt_acc.insert("end", f"{i:<4}{(a.get('email') or a.get('id') or '?')[:32]:<34}{st:<16}{'có' if a.get('cookie') else 'không':<10}{'có' if a.get('totp') else '-':<6}\n")

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
        def logp(m): self.after(0, lambda: self.lbl_acc_prog.configure(text=m))
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
        def logp(m): self.after(0, lambda: self.lbl_acc_prog.configure(text=m))
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
        self.gen_mode = ctk.StringVar(value="i2v")   # MẶC ĐỊNH Image → Video
        ctk.CTkRadioButton(top, text="Image → Video", variable=self.gen_mode, value="i2v", command=self._gen_mode).pack(side="right", padx=(12, 0))
        ctk.CTkRadioButton(top, text="Text → Video", variable=self.gen_mode, value="t2v", command=self._gen_mode).pack(side="right")
        # I2V: thư mục ảnh gốc
        self.r_ref = ctk.CTkFrame(f, fg_color="transparent")
        ctk.CTkLabel(self.r_ref, text="📁 Thư mục ảnh gốc:", width=150, anchor="w").pack(side="left")
        self.ent_ref = ctk.CTkEntry(self.r_ref); self.ent_ref.pack(side="left", fill="x", expand=True, padx=6)
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
        self.opt_aspect = ctk.CTkOptionMenu(rs, values=list(E.VID_ASPECTS.keys()), width=150); self.opt_aspect.pack(side="left", padx=(4, 12)); self.opt_aspect.set("Dọc 9:16 (TikTok)")
        ctk.CTkLabel(rs, text="Veo 3.1 Lite (miễn phí)", font=("", 11, "bold"), text_color=GR).pack(side="left", padx=(0, 12))
        ctk.CTkLabel(rs, text="Lưu:").pack(side="left")
        self.ent_out = ctk.CTkEntry(rs, width=170); self.ent_out.pack(side="left", padx=4)
        ctk.CTkButton(rs, text="Chọn", width=56, command=lambda: self._pick(self.ent_out)).pack(side="left", padx=(0, 10))
        # MIDDLE: 1 ô prompt duy nhất (KHÔNG thumbnail -> nhẹ, chịu 25k ảnh)
        self.txt_prompts = ctk.CTkTextbox(f, font=("Consolas", 11))
        self.ref_images = []; self.ref_promptfile = None
        self._gen_mode()

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
        self.ref_promptfile = None
        for cand in ("prompt.txt", "prompts.txt"):
            p = os.path.join(d, cand)
            if os.path.exists(p):
                lines = open(p, encoding="utf-8", errors="replace").read().splitlines()
                if len(lines) <= 3000:   # nhỏ -> hiện vào ô để xem/sửa
                    self.txt_prompts.delete("1.0", "end"); self.txt_prompts.insert("1.0", "\n".join(l for l in lines if l.strip()))
                else:                    # lớn -> chỉ tham chiếu file (không render, tránh treo)
                    self.ref_promptfile = p
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
        return [l.strip() for l in self.txt_prompts.get("1.0", "end").splitlines() if l.strip() and not l.startswith("(Đã nạp")]

    def _add_queue(self):
        out = self.ent_out.get().strip()
        if not out: messagebox.showwarning("Thiếu", "Chọn thư mục lưu."); return
        aspect = E.VID_ASPECTS[self.opt_aspect.get()]; model = "veo_3_1_t2v_lite_low_priority"  # bản miễn phí (I2V engine tự đổi r2v)
        mode = self.gen_mode.get(); base = len(self.jobs); added = 0
        prompts = self._read_prompts()
        if mode == "i2v":
            if not self.ref_images: messagebox.showwarning("Thiếu ảnh", "Bấm 'Chọn' để chọn thư mục ảnh gốc."); return
            for i, ref in enumerate(self.ref_images):
                pr = prompts[i] if i < len(prompts) else (prompts[-1] if prompts else "")
                if not pr: continue
                self.jobs.append({"type": "i2v", "prompt": pr, "ref": ref, "aspect": aspect, "model": model,
                                  "out": os.path.join(out, f"{base+added+1:05d}.mp4"), "status": "chờ"}); added += 1
        else:
            for pr in prompts:
                self.jobs.append({"type": "t2v", "prompt": pr, "ref": None, "aspect": aspect, "model": model,
                                  "out": os.path.join(out, f"{base+added+1:05d}.mp4"), "status": "chờ"}); added += 1
        if not added: messagebox.showwarning("Thiếu prompt", "Chưa có prompt."); return
        self._refresh_queue(); self._show("queue")

    # ============ TAB HÀNG ĐỢI ============
    def _build_queue(self):
        f = ctk.CTkFrame(self.content, fg_color=BG); self.frames["queue"] = f
        st = ctk.CTkFrame(f, fg_color="transparent"); st.pack(fill="x")
        self.stat_lbl = {}
        for key, txt, col in [("tong", "Tổng", "#3949AB"), ("xuly", "Xử lý", "#F9A825"), ("xong", "Xong", GR), ("loi", "Lỗi", RD)]:
            c = ctk.CTkFrame(st, fg_color=CARD, corner_radius=10); c.pack(side="left", expand=True, fill="x", padx=4)
            ctk.CTkLabel(c, text=txt, font=("", 12), text_color=T2).pack(pady=(10, 0))
            lb = ctk.CTkLabel(c, text="0", font=("", 24, "bold"), text_color=col); lb.pack(pady=(0, 10)); self.stat_lbl[key] = lb
        bar = ctk.CTkFrame(f, fg_color="transparent"); bar.pack(fill="x", pady=10)
        self.btn_run = ctk.CTkButton(bar, text="▶ Bắt đầu", command=self._start, fg_color=AC, hover_color=AC2, height=38, width=120, font=("", 14, "bold")); self.btn_run.pack(side="left")
        ctk.CTkButton(bar, text="■ Dừng", command=self._stop_run, fg_color="#5f6368", height=38, width=90).pack(side="left", padx=6)
        ctk.CTkLabel(bar, text="Luồng:").pack(side="left", padx=(16, 2))
        self.ent_thr = ctk.CTkEntry(bar, width=50); self.ent_thr.pack(side="left"); self.ent_thr.insert(0, "6")
        ctk.CTkButton(bar, text="↻ Retry lỗi", command=self._retry, fg_color="#9aa0a6", height=38, width=100).pack(side="left", padx=(16, 4))
        ctk.CTkButton(bar, text="🗑 Xóa xong", command=self._clear_done, fg_color="#9aa0a6", height=38, width=100).pack(side="left", padx=4)
        self.progress = ctk.CTkProgressBar(f); self.progress.pack(fill="x", pady=4); self.progress.set(0)
        self.txt_queue = ctk.CTkTextbox(f, height=250, font=("Consolas", 10)); self.txt_queue.pack(fill="both", expand=True, pady=(6, 6))
        self.txt_log = ctk.CTkTextbox(f, height=110, font=("Consolas", 10), fg_color="#0f1b3d", text_color="#8be9c0"); self.txt_log.pack(fill="x")

    def _refresh_queue(self, force=False):
        # THROTTLE: 25k job -> chỉ refresh tối đa 1 lần/giây (tránh treo khi mỗi job xong gọi 1 lần)
        now = time.time()
        if not force and now - getattr(self, "_last_qref", 0) < 1.0:
            return
        self._last_qref = now
        tong = len(self.jobs); xong = loi = xuly = 0
        for j in self.jobs:                      # đếm 1 LẦN (thay vì 4 lần)
            s = j["status"]
            if s == "xong": xong += 1
            elif s == "lỗi": loi += 1
            elif s == "đang": xuly += 1
        self.stat_lbl["tong"].configure(text=str(tong)); self.stat_lbl["xong"].configure(text=str(xong))
        self.stat_lbl["loi"].configure(text=str(loi)); self.stat_lbl["xuly"].configure(text=str(xuly))
        self.lbl_qcount.configure(text=f"Hàng đợi: {tong}")
        if tong: self.progress.set((xong + loi) / tong)
        # chỉ hiện 300 dòng đầu (đủ để theo dõi; 25k dòng sẽ treo textbox)
        self.txt_queue.delete("1.0", "end")
        self.txt_queue.insert("end", f"Hiển thị 300/{tong} job đầu · Xong {xong} · Lỗi {loi}\n" + "-" * 90 + "\n")
        for i, j in enumerate(self.jobs[:300], 1):
            ic = {"chờ": "⏳", "đang": "🔄", "xong": "✅", "lỗi": "❌"}.get(j["status"], "")
            self.txt_queue.insert("end", f"{i:<5}{('T2V' if j['type']=='t2v' else 'I2V'):<5}{ic+' '+j['status']:<11}{os.path.basename(j['out']):<14}{j['prompt'][:48]}\n")

    def _log(self, m):
        self.after(0, lambda: (self.txt_log.insert("end", m + "\n"), self.txt_log.see("end")))

    def _stop_run(self): self._stop = True; self._log("⏹ Đang dừng...")
    def _retry(self):
        for j in self.jobs:
            if j["status"] == "lỗi": j["status"] = "chờ"
        self._refresh_queue()
    def _clear_done(self):
        self.jobs = [j for j in self.jobs if j["status"] != "xong"]; self._refresh_queue()

    def _start(self):
        if self._running: return
        accs = [a for a in self.accounts if a.get("cookie") and a.get("status") == "ok"]
        if not accs: messagebox.showwarning("Thiếu tài khoản", "Vào tab Tài khoản, thêm + Check/Chuẩn bị."); return
        todo = [j for j in self.jobs if j["status"] in ("chờ", "lỗi")]
        if not todo: messagebox.showinfo("Trống", "Không có job chờ."); return
        try: thr = max(1, min(20, int(self.ent_thr.get() or "6")))
        except Exception: thr = 6
        self._stop = False; self._running = True
        self.btn_run.configure(state="disabled")
        threading.Thread(target=self._run, args=(accs, todo, thr), daemon=True).start()

    def _run(self, accs, todo, thr):
        try:
            self._log(f"🔑 Chuẩn bị {len(accs)} tài khoản...")
            prep = []
            for a in accs:
                b, _ = E.bearer_from_cookie(a["cookie"])
                if not b: continue
                pj = E.get_project(a["cookie"])
                if pj: prep.append({"bearer": b, "cookie": a["cookie"], "project": pj, "email": a["email"], "refcache": {}})
            if not prep:
                self._log("❌ Không tài khoản dùng được."); return
            self._log(f"✅ {len(prep)} tài khoản sẵn sàng. Bắt đầu {len(todo)} job, {thr} luồng.")
            lock = threading.Lock(); idx = [0]

            def work(job):
                if self._stop: return
                with lock:
                    acc = prep[idx[0] % len(prep)]; idx[0] += 1
                job["status"] = "đang"; self.after(0, self._refresh_queue)
                if os.path.exists(job["out"]):
                    job["status"] = "xong"; self.after(0, self._refresh_queue); return
                ref_mid = None
                if job["type"] == "i2v" and job.get("ref"):
                    if job["ref"] in acc["refcache"]:
                        ref_mid = acc["refcache"][job["ref"]]
                    else:
                        ref_mid = E.upload_image(acc["bearer"], acc["project"], job["ref"])
                        acc["refcache"][job["ref"]] = ref_mid
                seed = (abs(hash(job["prompt"])) % 900000) + 1
                for attempt in range(5):
                    if self._stop: return
                    kind, ops = E.submit_video(acc["bearer"], acc["project"], job["prompt"], seed, job["aspect"], job["model"], ref_mid)
                    if kind == "ok":
                        pk, mid = E.poll_video(acc["bearer"], ops)
                        if pk == "done":
                            n = E.download_video(mid, acc["cookie"], job["out"])
                            if n > 0:
                                job["status"] = "xong"; self._log(f"  ✅ {os.path.basename(job['out'])} ({n//1024}KB) [{acc['email'][:16]}]")
                                self.after(0, self._refresh_queue); return
                        elif pk == "failed":
                            self._log(f"  ❌ render fail: {job['prompt'][:30]}"); break
                    elif kind == "auth":
                        break
                    time.sleep(2 + attempt)
                job["status"] = "lỗi"; self.after(0, self._refresh_queue)

            with ThreadPoolExecutor(max_workers=thr) as ex:
                list(ex.map(work, todo))
            self._log("🎉 XONG hàng đợi.")
            self.after(0, lambda: self._refresh_queue(force=True))
        except Exception:
            self._log("LỖI: " + traceback.format_exc())
        finally:
            self._running = False
            self.after(0, lambda: self.btn_run.configure(state="normal"))


if __name__ == "__main__":
    App().mainloop()
