"""Tự cập nhật bản mới nhất từ GitHub (chạy trước khi mở tool). Offline thì bỏ qua, dùng bản local."""
import urllib.request, os

REPO = "manhthang1905-hub/thinaptm"
BASE = f"https://raw.githubusercontent.com/{REPO}/main/"
FILES = ["thin_aptm.py", "engine.py", "login.py", "requirements.txt", "update.py", "CHAY.bat", "HUONG_DAN.txt"]
HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    print("Kiem tra ban moi tren GitHub...")
    updated = 0
    for f in FILES:
        try:
            req = urllib.request.Request(BASE + f + f"?t={os.urandom(4).hex()}",
                                         headers={"Cache-Control": "no-cache", "User-Agent": "thinaptm-updater"})
            data = urllib.request.urlopen(req, timeout=12).read()
            if not data or len(data) < 30:
                continue
            local = os.path.join(HERE, f)
            old = open(local, "rb").read() if os.path.exists(local) else b""
            if data != old:
                with open(local, "wb") as fp:
                    fp.write(data)
                print(f"  da cap nhat {f}")
                updated += 1
        except Exception:
            pass   # offline / chua co file tren repo -> dung ban local
    print(f"Xong ({updated} file cap nhat)." if updated else "Da la ban moi nhat.")


if __name__ == "__main__":
    main()
