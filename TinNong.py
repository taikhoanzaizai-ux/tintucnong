import concurrent.futures
import datetime as dt
import email.utils
import math
import os
from pathlib import Path
import queue
import re
import threading
import tkinter as tk
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
from tkinter import messagebox, ttk
from urllib.parse import quote, urlsplit

VERSION = (2, 0, 0)
UPDATE_URL = "https://raw.githubusercontent.com/taikhoanzaizai-ux/tintucnong/main/TinNong.py"


def check_update():
    with urllib.request.urlopen(UPDATE_URL, timeout=10) as response:
        body = response.read(250_001)
    if len(body) > 250_000:
        raise ValueError("Tệp cập nhật quá lớn")
    source = body.decode("utf-8-sig")
    match = re.search(r"^VERSION = \((\d+), (\d+), (\d+)\)$", source, re.M)
    if not match:
        raise ValueError("Thiếu phiên bản trong tệp cập nhật")
    compile(source, "TinNong.py", "exec")
    return tuple(map(int, match.groups())), body


def install_update(body, path):
    import tempfile
    import shutil
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temp = Path(handle.name)
        try:
            handle.write(body)
        except BaseException:
            handle.close()
            temp.unlink(missing_ok=True)
            raise
    try:
        shutil.copy2(path, path.with_suffix(".py.bak"))
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)

FEEDS = [
    ("VnExpress", "Thời sự", "https://vnexpress.net/rss/thoi-su.rss"),
    ("VnExpress", "Đời sống", "https://vnexpress.net/rss/doi-song.rss"),
    ("VnExpress", "Pháp luật", "https://vnexpress.net/rss/phap-luat.rss"),
    ("VnExpress", "Thể thao", "https://vnexpress.net/rss/the-thao.rss"),
    ("Tuổi Trẻ", "Tin chung", "https://tuoitre.vn/rss/tin-moi-nhat.rss"),
    ("Thanh Niên", "Tin chung", "https://thanhnien.vn/rss/home.rss"),
    ("Dân trí", "Tin chung", "https://dantri.com.vn/rss/trangchinh.rss"),
]
TOPICS = ("Tất cả", "Thời sự", "Đời sống", "Pháp luật", "Thể thao", "Tin chung")
IGNORE = set("và của có ở là cho khi với một những các đã được từ về trong tại sau trước trên này".split())


def read_feed(feed):
    source, topic, url = feed
    request = urllib.request.Request(url, headers={"User-Agent": "TinNongRSS/1.0"})
    with urllib.request.urlopen(request, timeout=8) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("RSS quá lớn")
    root = ET.fromstring(raw)
    if root.tag != "rss":
        raise ValueError("Định dạng RSS không hợp lệ")
    rows = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        parsed = urlsplit(link)
        if not title or parsed.scheme not in ("http", "https") or not parsed.hostname:
            continue
        try:
            date = email.utils.parsedate_to_datetime(item.findtext("pubDate") or "")
            date = date.replace(tzinfo=dt.timezone.utc) if date.tzinfo is None else date
        except (ValueError, TypeError, OverflowError):
            continue
        rows.append((title, link, date, source, topic))
    return rows


def rank(rows, now):
    unique = {}
    for row in rows:
        key = row[1].split("?")[0].rstrip("/")
        if key not in unique:
            unique[key] = row
    groups = []
    for row in sorted(unique.values(), key=lambda r: r[2], reverse=True):
        age = (now - row[2]).total_seconds() / 3600
        if age > 48 or age < -1:
            continue
        words = set(re.findall(r"\w+", row[0].casefold())) - IGNORE
        for group in groups:
            anchor, items = group
            common = len(words & anchor)
            if common >= 4 and common / len(words | anchor) >= 0.52:
                items.append(row)
                break
        else:
            groups.append((words, [row]))
    ranked = []
    for _, items in groups:
        age = max(0, (now - items[0][2]).total_seconds() / 3600)
        sources = len({r[3] for r in items})
        score = round(65 * math.exp(-age / 12) + min(35, 14 * (sources - 1)))
        ranked.append((score, sources, items))
    return sorted(ranked, key=lambda g: (g[0], g[2][0][2]), reverse=True)


class App:
    def __init__(self, root):
        self.root = root
        self.results = []
        self.visible = {}
        self.mailbox = queue.Queue()
        self.updates = queue.Queue()
        self.busy = False
        root.title("Tin Nóng | " + ".".join(map(str, VERSION)))
        root.geometry("1120x690")
        root.minsize(760, 520)
        root.configure(bg="#101b2d")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("Treeview", rowheight=32, font=("Segoe UI", 10), background="#f8fafc")
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), padding=8,
                        background="#dae6f5", foreground="#14253e")
        style.map("Treeview", background=[("selected", "#205ca5")])
        style.configure("TButton", padding=(10, 6))
        tk.Label(root, text="TIN NÓNG", bg="#101b2d", fg="#ffbb66",
                 font=("Segoe UI", 25, "bold")).pack(anchor="w", padx=22, pady=(14, 0))
        tk.Label(root, text="Bàn biên tập  /  Tin trong 48 giờ qua", bg="#101b2d",
                 fg="#d7e4fa", font=("Segoe UI", 11)).pack(anchor="w", padx=24, pady=(0, 14))
        panel = ttk.Frame(root, padding=12)
        panel.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        bar = ttk.Frame(panel)
        bar.pack(fill="x", pady=(0, 10))
        self.scan_button = ttk.Button(bar, text="Quét ngay", command=self.scan)
        self.scan_button.pack(side="left")
        self.update_button = ttk.Button(bar, text="Kiểm tra cập nhật", command=self.start_update)
        self.update_button.pack(side="right", padx=(8, 0))
        self.auto = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Tự quét mỗi 15 phút", variable=self.auto).pack(side="left", padx=12)
        self.topic = ttk.Combobox(bar, values=TOPICS, state="readonly", width=13)
        self.topic.current(0)
        self.topic.pack(side="left")
        self.topic.bind("<<ComboboxSelected>>", self.render)
        ttk.Label(bar, text="Từ khóa").pack(side="left", padx=(15, 6))
        self.search = tk.StringVar()
        ttk.Entry(bar, textvariable=self.search).pack(side="left", fill="x", expand=True)
        self.search.trace_add("write", self.render)
        social = ttk.Frame(panel)
        social.pack(fill="x", pady=(0, 10))
        for name, url in (
            ("Facebook công khai", "https://www.google.com/search?tbs=qdr:w&q="),
            ("YouTube", "https://www.youtube.com/results?search_query="),
            ("TikTok", "https://www.tiktok.com/search?q="),
        ):
            ttk.Button(social, text=name, command=lambda n=name, u=url: self.social_search(n, u)).pack(side="left", padx=(0, 6))
        ttk.Button(social, text="TikTok thịnh hành VN", command=lambda: webbrowser.open(
            "https://ads.tiktok.com/creative/creativeCenter/trends?region=VN")).pack(side="left")
        area = ttk.Frame(panel)
        area.pack(fill="both", expand=True)
        self.table = ttk.Treeview(area, columns=("score", "time", "sources", "headline"), show="headings")
        for column, label, width in (("score", "Điểm", 55), ("time", "Giờ đăng", 95),
                                     ("sources", "Số báo", 60), ("headline", "Tiêu đề", 550)):
            self.table.heading(column, text=label)
            self.table.column(column, width=width, stretch=column == "headline")
        scroll = ttk.Scrollbar(area, command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        self.table.tag_configure("even", background="#eaf1fb")
        scroll.pack(side="right", fill="y")
        self.table.pack(side="left", fill="both", expand=True)
        self.table.bind("<<TreeviewSelect>>", self.show_links)
        links = ttk.Frame(panel)
        links.pack(fill="x", pady=8)
        self.links = ttk.Combobox(links, state="readonly")
        self.links.pack(side="left", fill="x", expand=True)
        ttk.Button(links, text="Mở bài gốc", command=self.open_link).pack(side="left", padx=6)
        self.status = tk.StringVar(value="Đang chuẩn bị quét")
        ttk.Label(panel, textvariable=self.status, wraplength=950).pack(anchor="w")
        root.after(150, self.poll)
        root.after(900_000, self.periodic)
        self.scan()

    def social_search(self, name, url):
        selected = self.table.selection()
        headline = self.table.set(selected[0], "headline") if selected else ""
        keyword = self.search.get().strip() or headline or "tin nóng đang lan truyền Việt Nam"
        if name == "Facebook công khai":
            keyword = "site:facebook.com " + keyword
        webbrowser.open(url + quote(keyword))

    def start_update(self):
        self.update_button.state(["disabled"])
        self.status.set("Đang kiểm tra bản mới trên GitHub…")
        threading.Thread(target=self.fetch_update, daemon=True).start()

    def fetch_update(self):
        try:
            self.updates.put((check_update(), None))
        except Exception as error:
            self.updates.put((None, str(error)))

    def finish_update(self):
        try:
            result, error = self.updates.get_nowait()
        except queue.Empty:
            return
        self.update_button.state(["!disabled"])
        if error:
            self.status.set("Lỗi cập nhật: " + error)
            return
        version, body = result
        label = ".".join(map(str, version))
        if version <= VERSION:
            self.status.set("Bạn đang dùng bản mới nhất.")
        elif messagebox.askyesno("Cập nhật Tin Nóng", f"Cài bản {label} từ GitHub?"):
            try:
                install_update(body, Path(__file__).resolve())
            except OSError as error:
                self.status.set("Lỗi cài cập nhật: " + str(error))
                return
            messagebox.showinfo("Tin Nóng", f"Đã cài bản {label}. Mở lại Mo-Tin-Nong.bat để sử dụng.")
            self.root.destroy()
        else:
            self.status.set(f"Có bản {label} trên GitHub.")

    def scan(self):
        if self.busy:
            return
        self.busy = True
        self.scan_button.state(["disabled"])
        self.status.set("Đang tải RSS từ các báo…")
        threading.Thread(target=self.collect, daemon=True).start()

    def collect(self):
        rows, failed = [], []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(FEEDS)) as pool:
            for feed, future in zip(FEEDS, [pool.submit(read_feed, f) for f in FEEDS]):
                try:
                    rows.extend(future.result())
                except Exception:
                    failed.append(f"{feed[0]} / {feed[1]}")
        self.mailbox.put((rank(rows, dt.datetime.now(dt.timezone.utc)), failed))

    def poll(self):
        self.root.after(150, self.poll)
        try:
            results, failed = self.mailbox.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.scan_button.state(["!disabled"])
            stamp = dt.datetime.now().strftime("%H:%M:%S")
            if len(failed) == len(FEEDS):
                self.status.set(f"{stamp} · Không tải được RSS. Kiểm tra mạng rồi bấm Quét ngay. Danh sách cũ được giữ lại.")
            else:
                self.results = results
                self.render()
                details = " · Lỗi: " + ", ".join(failed) if failed else ""
                self.status.set(f"{stamp} · {len(results)} nhóm tin · {len(FEEDS)-len(failed)}/{len(FEEDS)} luồng RSS{details}")
        self.finish_update()

    def periodic(self):
        if self.auto.get():
            self.scan()
        self.root.after(900_000, self.periodic)

    def render(self, *_):
        self.table.delete(*self.table.get_children())
        self.visible.clear()
        self.links.configure(values=[])
        self.links.set("")
        query = self.search.get().strip().casefold()
        topic = self.topic.get()
        local = dt.timezone(dt.timedelta(hours=7))
        for score, sources, rows in self.results:
            matches = [r for r in rows if (topic == "Tất cả" or r[4] == topic) and query in r[0].casefold()]
            if matches:
                title, _, date, _, _ = matches[0]
                tags = ("even",) if len(self.visible) % 2 else ()
                node = self.table.insert("", "end", tags=tags,
                                         values=(score, date.astimezone(local).strftime("%d/%m %H:%M"), sources, title))
                self.visible[node] = rows

    def show_links(self, _):
        selected = self.table.selection()
        rows = self.visible.get(selected[0], []) if selected else []
        self.links.configure(values=[f"{r[3]} | {r[0]}" for r in rows])
        if rows:
            self.links.current(0)
        else:
            self.links.set("")

    def open_link(self):
        selected = self.table.selection()
        index = self.links.current()
        if selected and index >= 0:
            webbrowser.open(self.visible[selected[0]][index][1])


if __name__ == "__main__":
    window = tk.Tk()
    App(window)
    window.mainloop()
