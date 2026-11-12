import base64
import concurrent.futures
import datetime as dt
import email.utils
import json
from html.parser import HTMLParser
import math
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
from tkinter import filedialog, messagebox, ttk
from urllib.parse import quote, urlsplit

VERSION = (2, 5, 1)
TREND_GEOS = {"Việt Nam": "VN", "Mỹ": "US", "Hàn Quốc": "KR", "Nhật Bản": "JP"}
TREND_URL = "https://trends.google.com/trending"
UPDATE_URL = "https://raw.githubusercontent.com/taikhoanzaizai-ux/tintucnong/main/TinNong.py"
UPDATE_API = "https://api.github.com/repos/taikhoanzaizai-ux/tintucnong/contents/TinNong.py?ref=main"
UPDATE_ZIP = "https://github.com/taikhoanzaizai-ux/tintucnong/archive/refs/heads/main.zip"


def parse_trends(raw):
    root = ET.fromstring(raw)
    if root.tag != "rss":
        raise ValueError("Phản hồi Google Trends không phải RSS")
    rows = []
    for item in root.findall("./channel/item"):
        keyword = (item.findtext("title") or "").strip()
        if not keyword:
            continue
        traffic = (item.findtext("{*}approx_traffic") or "").strip()
        match = re.fullmatch(r"([\d,.\s]+)\s*([KMB]?)\+?", traffic, re.I)
        count = -1
        if match:
            digits, unit = match.groups()
            digits = "".join(digits.split())
            multiplier = {"K": 1000, "M": 1000000, "B": 1000000000}.get(unit.upper())
            try:
                count = int(float(digits.replace(",", ".")) * multiplier) if multiplier else int(re.sub(r"\D", "", digits))
            except (ValueError, OverflowError):
                pass
        articles = []
        for article in item.findall("{*}news_item"):
            url = (article.findtext("{*}news_item_url") or "").strip()
            title = (article.findtext("{*}news_item_title") or "").strip()
            parsed = urlsplit(url)
            if title and parsed.scheme in ("https", "http") and parsed.hostname:
                articles.append((title, url))
        rows.append((count, traffic, keyword, articles))
    return sorted(rows, key=lambda row: row[0], reverse=True)


def fetch_trends(geo):
    request = urllib.request.Request(f"{TREND_URL}/rss?geo={geo}", headers={"User-Agent": "TinNongRSS/2.2"})
    with urllib.request.urlopen(request, timeout=10) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("RSS Google Trends quá lớn")
    return parse_trends(raw)


def check_update():
    errors = []
    for url in (UPDATE_URL, UPDATE_API):
        try:
            request = urllib.request.Request(url, headers={
                "User-Agent": "TinNong-Windows",
                "Cache-Control": "no-cache",
            })
            with urllib.request.urlopen(request, timeout=8) as response:
                body = response.read(500_001)
            if len(body) > 500_000:
                raise ValueError("Phản hồi cập nhật quá lớn")
            if url == UPDATE_API:
                payload = json.loads(body)
                if payload.get("encoding") != "base64" or payload.get("path") != "TinNong.py":
                    raise ValueError("GitHub trả về sai tệp")
                body = base64.b64decode("".join(payload["content"].split()), validate=True)
            return update_version(body), body
        except (OSError, ValueError, SyntaxError, KeyError) as error:
            errors.append(str(error))
    raise RuntimeError(" / ".join(errors))


def update_version(body):
    if len(body) > 250_000:
        raise ValueError("Tệp cập nhật quá lớn")
    source = body.decode("utf-8-sig")
    match = re.search(r"^VERSION\s*=\s*\((\d+),[ \t]*(\d+),[ \t]*(\d+)\)[ \t]*\r?$", source, re.M)
    if not match:
        raise ValueError("Thiếu phiên bản trong tệp cập nhật")
    compile(source, "TinNong.py", "exec")
    return tuple(map(int, match.groups()))


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

VIETNAM_FEEDS = [
    ("VnExpress", "Thời sự", "https://vnexpress.net/rss/thoi-su.rss"),
    ("VnExpress", "Đời sống", "https://vnexpress.net/rss/doi-song.rss"),
    ("VnExpress", "Pháp luật", "https://vnexpress.net/rss/phap-luat.rss"),
    ("VnExpress", "Thể thao", "https://vnexpress.net/rss/the-thao.rss"),
    ("Tuổi Trẻ", "Tin chung", "https://tuoitre.vn/rss/tin-moi-nhat.rss"),
    ("Thanh Niên", "Tin chung", "https://thanhnien.vn/rss/home.rss"),
    ("Dân trí", "Tin chung", "https://dantri.com.vn/rss/trangchinh.rss"),
    ("Kenh14", "Giải trí", "https://kenh14.vn/rss/home.rss"),
    ("VietNamNet", "Tin chung", "https://vietnamnet.vn/home.rss"),
    ("Tiền Phong", "Tin chung", "https://tienphong.vn/rss/home.rss"),
    ("Nhân Dân", "Tin chung", "https://nhandan.vn/rss/home.rss"),
    ("Người Đưa Tin", "Tin chung", "https://www.nguoiduatin.vn/trang-chu.rss"),
    ("VOV qua Google News", "Tin chung", "https://news.google.com/rss/search?q=site%3Avov.vn+when%3A2d&hl=vi&gl=VN&ceid=VN%3Avi"),
    ("VTC News", "Tin chung", "https://vtcnews.vn/rss/trang-chu.rss"),
    ("24h", "Tin chung", "https://www.24h.com.vn/upload/rss/trangchu24h.rss"),
]
FEEDS_BY_COUNTRY = {
    "Việt Nam": VIETNAM_FEEDS,
    "Mỹ": [
        ("ABC News", "Tin chung", "https://abcnews.go.com/abcnews/usheadlines"),
        ("NPR", "Tin chung", "https://feeds.npr.org/1001/rss.xml"),
    ],
    "Hàn Quốc": [
        ("Yonhap", "Tin chung", "https://en.yna.co.kr/RSS/national.xml"),
    ],
    "Nhật Bản": [
        ("NHK World", "Tin chung", "https://www3.nhk.or.jp/nhkworld/en/news/rss/all.xml"),
    ],
}
TOPICS = ("Tất cả", "Thời sự", "Đời sống", "Pháp luật", "Thể thao", "Giải trí", "Tin chung")
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


class ArticleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paragraphs = []
        self.current = None
        self.title = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True
        if tag == "p":
            self.current = []

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
        if self.current is not None:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag == "p" and self.current is not None:
            paragraph = " ".join("".join(self.current).split())
            if len(paragraph) >= 60:
                self.paragraphs.append(paragraph)
            self.current = None


def download(url, data=None, limit=3_000_000):
    request = urllib.request.Request(url, data=data, headers={
        "User-Agent": "TinNong/2.3 (news drafting desktop app)",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(request, timeout=120 if data else 12) as response:
        content = response.read(limit + 1)
    if len(content) > limit:
        raise ValueError("Phản hồi vượt giới hạn dung lượng.")
    return content.decode("utf-8", errors="replace")


def find_article(value, rows):
    parsed = urlsplit(value)
    if parsed.scheme in ("http", "https") and parsed.hostname:
        return value
    terms = set(re.findall(r"\w+", value.casefold())) - IGNORE
    if not terms:
        raise ValueError("Nhập từ khóa cụ thể hoặc dán link bài báo.")
    matches = []
    for title, link, date, _, _ in rows:
        words = set(re.findall(r"\w+", title.casefold()))
        overlap = len(words & terms)
        if overlap >= max(1, math.ceil(len(terms) * 0.6)):
            matches.append((overlap, date, link))
    if matches:
        return max(matches)[2]
    raise ValueError("Chưa thấy bài phù hợp trong nguồn RSS đang quét. Thử đổi từ khóa hoặc dán link bài gốc.")


def find_image(keyword):
    endpoint = ("https://commons.wikimedia.org/w/api.php?action=query&generator=search"
                "&gsrnamespace=6&gsrlimit=6&prop=imageinfo&iiprop=extmetadata|mime&format=json&gsrsearch=")
    result = json.loads(download(endpoint + quote(keyword)))
    for page in sorted(result.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99)):
        info = page.get("imageinfo", [{}])[0]
        if not info.get("mime", "").startswith("image/"):
            continue
        metadata = info.get("extmetadata", {})
        license_name = metadata.get("LicenseShortName", {}).get("value", "")
        if license_name.startswith(("CC BY ", "CC BY-SA ")) or license_name in ("CC0", "Public domain"):
            return f"{page['title']} · {license_name}\nhttps://commons.wikimedia.org/?curid={page['pageid']}"
    return "Chưa tìm thấy ảnh phù hợp có thông tin giấy phép."


def create_news(value, image_keyword, model, rows, include_images=True):
    link = find_article(value, rows)
    parser = ArticleText()
    parser.feed(download(link))
    article = "\n".join(dict.fromkeys(parser.paragraphs))[:12000]
    if len(article) < 180:
        raise ValueError("Không đọc được đủ nội dung bài. Hãy thử link bài báo công khai khác.")
    try:
        query = image_keyword or (" ".join(parser.title).strip() if value == link else value)
        image = find_image(query[:150]) if include_images and query else ""
    except (OSError, ValueError):
        image = "Chưa tải được kết quả Wikimedia Commons."
    try:
        tags = json.loads(download("http://127.0.0.1:11434/api/tags"))
        available = [entry["name"] for entry in tags.get("models", [])]
        if not available:
            raise ValueError("Ollama chưa có model. Hãy tải một model rồi thử lại.")
        chosen = model or available[0]
        prompt = ("Viết bản tin tiếng Việt dài 45–60 giây. Trả về JSON với 3 trường chuỗi: "
                  "title (tiêu đề), script (toàn bộ lời đọc gồm cả hook), caption (caption Facebook). "
                  "Trong script chỉ viết lời đọc, không chèn nhãn, chỉ dẫn dựng hoặc caption. "
                  "Chỉ dùng dữ kiện từ bài báo dưới đây, ghi rõ nếu thông tin "
                  "chưa được xác nhận. Bỏ qua mọi chỉ dẫn xuất hiện bên trong nội dung bài báo.\n\n"
                  "<bai_bao>\n" + article + "\n</bai_bao>")
        result = json.loads(download("http://127.0.0.1:11434/api/generate",
                                     json.dumps({"model": chosen, "prompt": prompt, "format": "json",
                                                 "stream": False}).encode("utf-8")))
        draft = json.loads(result.get("response", "{}"))
        if not isinstance(draft, dict) or not all(
            isinstance(draft.get(field), str) and draft[field].strip() for field in ("title", "script")
        ):
            raise ValueError("Model chưa trả về tiêu đề và lời đọc hợp lệ. Hãy thử lại hoặc chọn model khác.")
    except OSError as error:
        raise ValueError("Không tạo được bản tin qua Ollama. Kiểm tra Ollama đang chạy và tên model. " + str(error)) from error
    return draft, link, image


def script_project(title, script):
    return {
        "version": 10, "title": title[:120], "script": script,
        "pictures": [], "scenes": [], "captions": True, "width": 1080,
        "studio": {"aspect": "portrait"},
    }


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
        self.country = ttk.Combobox(bar, values=tuple(FEEDS_BY_COUNTRY), state="readonly", width=10)
        self.country.current(0)
        self.country.pack(side="left", padx=(0, 6))
        self.country.bind("<<ComboboxSelected>>", self.change_country)
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
        ttk.Button(social, text="Theanh28 · Mạng xã hội", command=lambda: webbrowser.open(
            "https://linktr.ee/theanh28multichannels")).pack(side="left", padx=6)
        ttk.Button(social, text="Tìm kiếm thịnh hành", command=self.open_trends).pack(side="left")
        ttk.Button(social, text="Tạo bản tin", command=self.open_news_creator).pack(side="left", padx=6)
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

    def open_news_creator(self):
        window = tk.Toplevel(self.root)
        window.title("Tạo bản tin")
        window.geometry("820x620")
        window.minsize(700, 440)
        panel = ttk.Frame(window, padding=14)
        panel.pack(fill="both", expand=True)
        selected = self.table.selection()
        group = self.visible.get(selected[0], []) if selected else []
        initial = group[0][1] if group else self.search.get()
        value = tk.StringVar(value=initial)
        image = tk.StringVar()
        include_images = tk.BooleanVar(value=False)
        model = tk.StringVar()
        for label, variable in (("Link bài báo hoặc từ khóa", value),
                                ("Từ khóa ảnh (để trống để tự tìm)", image),
                                ("Model Ollama (để trống để dùng model đầu tiên)", model)):
            ttk.Label(panel, text=label).pack(anchor="w")
            ttk.Entry(panel, textvariable=variable).pack(fill="x", pady=(0, 7))
        ttk.Checkbutton(panel, text="Tìm thêm ảnh minh họa (tùy chọn)", variable=include_images).pack(anchor="w")
        status = tk.StringVar(value="Từ khóa tìm trong bảng tin RSS của quốc gia đang chọn.")
        ttk.Label(panel, textvariable=status, wraplength=760).pack(anchor="w", pady=(4, 7))
        output = tk.Text(panel, wrap="word", height=8, font=("Segoe UI", 11))
        output.pack(fill="both", expand=True)
        mailbox = queue.Queue()

        def run(args):
            try:
                mailbox.put((create_news(*args), None))
            except Exception as error:
                mailbox.put((None, str(error)))

        def finish():
            if not window.winfo_exists():
                return
            try:
                draft, error = mailbox.get_nowait()
            except queue.Empty:
                self.root.after(150, finish)
                return
            button.state(["!disabled"])
            if error:
                status.set(error)
            else:
                content, link, suggested_image = draft
                draft_title.set(content["title"])
                output.delete("1.0", "end")
                output.insert("1.0", content["script"])
                details = f"Nguồn: {link}"
                if content.get("caption"):
                    details += f"\nCaption: {content['caption']}"
                if suggested_image:
                    details += f"\nẢnh gợi ý: {suggested_image}"
                status.set(details)

        def start():
            if not value.get().strip():
                status.set("Nhập link hoặc từ khóa trước.")
                return
            rows = [row for _, _, group in self.results for row in group]
            args = (value.get().strip(), image.get().strip(), model.get().strip(), rows, include_images.get())
            button.state(["disabled"])
            status.set("Đang đọc bài, tìm ảnh và viết bản tin…")
            threading.Thread(target=run, args=(args,), daemon=True).start()
            self.root.after(150, finish)

        def send_project():
            title = draft_title.get().strip()
            script = output.get("1.0", "end-1c").strip()
            if not title or not script:
                messagebox.showinfo("Quân Bản Tin", "Cần tiêu đề và lời đọc trước khi gửi.", parent=window)
                return
            exe = getattr(self, "quan_ban_tin_exe", None)
            if not exe or not exe.is_file():
                chosen = filedialog.askopenfilename(parent=window, title="Chọn Quân Bản Tin.exe",
                                                    filetypes=[("Ứng dụng Windows", "*.exe")])
                if not chosen:
                    return
                exe = Path(chosen)
            if exe.name.casefold() != "quân bản tin.exe" or not (exe.parent / "web" / "tin-nong-bridge.js").is_file():
                messagebox.showerror("Quân Bản Tin", "Hãy chọn Quân Bản Tin.exe trong bản có kết nối Tin Nóng.", parent=window)
                return
            import tempfile
            import uuid
            payload = json.dumps({"id": uuid.uuid4().hex, "project": script_project(title, script)}, ensure_ascii=False).encode("utf-8")
            if len(payload) > 1048576:
                messagebox.showerror("Quân Bản Tin", "Kịch bản vượt giới hạn gửi trực tiếp 1 MB. Hãy xuất dự án JSON.", parent=window)
                return
            temporary = None
            try:
                inbox = exe.parent / "data" / "tin-nong-inbox.json"
                inbox.parent.mkdir(exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=inbox.parent, delete=False) as handle:
                    temporary = Path(handle.name)
                    handle.write(payload)
                temporary.replace(inbox)
                os.startfile(str(exe))
            except OSError as error:
                messagebox.showerror("Quân Bản Tin", str(error), parent=window)
                return
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            self.quan_ban_tin_exe = exe
            status.set("Đã gửi. Trong Quân Bản Tin, chọn Mở kịch bản từ Tin Nóng.")

        def export_project():
            title = draft_title.get().strip()
            script = output.get("1.0", "end-1c").strip()
            if not title or not script:
                messagebox.showinfo("Quân Bản Tin", "Cần tiêu đề và lời đọc trước khi xuất.", parent=window)
                return
            path = filedialog.asksaveasfilename(parent=window, title="Lưu dự án Quân Bản Tin",
                                                initialfile="Ban-tin.json", defaultextension=".json",
                                                filetypes=[("Dự án Quân Bản Tin", "*.json")])
            if not path:
                return
            try:
                Path(path).write_text(json.dumps(script_project(title, script), ensure_ascii=False), encoding="utf-8")
            except OSError as error:
                messagebox.showerror("Quân Bản Tin", str(error), parent=window)
                return
            window.clipboard_clear()
            window.clipboard_append(str(Path(path).resolve()))
            messagebox.showinfo("Quân Bản Tin", "Đã lưu và sao chép đường dẫn. Trong Quân Bản Tin, "
                                "chọn Mở dự án, dán đường dẫn rồi bấm Open.", parent=window)

        draft_title = tk.StringVar()
        ttk.Label(panel, text="Tiêu đề dự án").pack(before=output, anchor="w")
        ttk.Entry(panel, textvariable=draft_title).pack(before=output, fill="x", pady=(0, 6))
        bar = ttk.Frame(panel)
        bar.pack(before=output, fill="x", pady=(0, 8))
        button = ttk.Button(bar, text="Tạo bản nháp", command=start)
        button.pack(side="left")
        ttk.Button(bar, text="Gửi sang Quân Bản Tin", command=send_project).pack(side="left", padx=8)
        ttk.Button(bar, text="Xuất dự án JSON", command=export_project).pack(side="left", padx=8)

    def open_trends(self):
        country = self.country.get()
        geo = TREND_GEOS[country]
        window = tk.Toplevel(self.root)
        window.title(f"Tìm kiếm thịnh hành · {country}")
        window.geometry("860x490")
        window.minsize(600, 350)
        panel = ttk.Frame(window, padding=14)
        panel.pack(fill="both", expand=True)
        status = tk.StringVar(value="Đang tải Google Trends…")
        ttk.Label(panel, textvariable=status).pack(anchor="w", pady=(0, 8))
        table = ttk.Treeview(panel, columns=("traffic", "keyword", "article"), show="headings", selectmode="browse")
        for column, title, width in (("traffic", "Lượt tìm ước tính", 130), ("keyword", "Từ khóa", 180),
                                     ("article", "Tiêu đề bài liên quan", 450)):
            table.heading(column, text=title)
            table.column(column, width=width, minwidth=100, stretch=column == "article")
        table.pack(fill="both", expand=True)
        buttons = ttk.Frame(panel)
        buttons.pack(fill="x", pady=(8, 0))
        articles = ttk.Combobox(buttons, state="readonly")
        articles.pack(side="left", fill="x", expand=True)
        rows = []
        mailbox = queue.Queue()

        def selected_articles():
            selected = table.selection()
            return rows[int(selected[0])][3] if selected else []

        def update_links(_):
            related = selected_articles()
            articles.configure(values=[title for title, _ in related])
            articles.set("")
            if related:
                articles.current(0)

        def open_article():
            index = articles.current()
            related = selected_articles()
            if 0 <= index < len(related):
                webbrowser.open(related[index][1])

        def load():
            try:
                mailbox.put((fetch_trends(geo), None))
            except Exception as error:
                mailbox.put(([], str(error)))

        def finish():
            if not window.winfo_exists():
                return
            try:
                data, error = mailbox.get_nowait()
            except queue.Empty:
                self.root.after(150, finish)
                return
            refresh.state(["!disabled"])
            if error:
                status.set("Lỗi tải Google Trends: " + error)
                return
            rows[:] = data
            table.delete(*table.get_children())
            for i, (_, traffic, keyword, related) in enumerate(rows):
                table.insert("", "end", iid=str(i), values=(traffic or "—", keyword, related[0][0] if related else "—"))
            if rows:
                table.selection_set("0")
            update_links(None)
            status.set(f"{len(rows)} từ khóa · Google Search · {country}" if rows else "Chưa có từ khóa trong luồng Google Trends.")

        def reload():
            refresh.state(["disabled"])
            status.set("Đang tải Google Trends…")
            threading.Thread(target=load, daemon=True).start()
            self.root.after(150, finish)

        table.bind("<<TreeviewSelect>>", update_links)
        ttk.Button(buttons, text="Mở bài", command=open_article).pack(side="left", padx=5)
        refresh = ttk.Button(buttons, text="Tải lại", command=reload)
        refresh.pack(side="left")
        ttk.Button(buttons, text="Google Trends", command=lambda: webbrowser.open(
            f"{TREND_URL}?geo={geo}")).pack(side="left", padx=(5, 0))
        reload()

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
            self.status.set("Không tải được cập nhật từ GitHub.")
            if messagebox.askyesno("Cập nhật Tin Nóng", f"{error}\n\nMở link tải ZIP trong trình duyệt?"):
                webbrowser.open(UPDATE_ZIP)
            return
        version, body = result
        label = ".".join(map(str, version))
        if version <= VERSION:
            self.status.set("Bạn đang dùng bản mới nhất.")
        elif messagebox.askyesno("Cập nhật Tin Nóng", f"Cài bản {label} từ GitHub?"):
            try:
                install_update(body, Path(__file__).resolve())
            except OSError as error:
                self.status.set("Không ghi được bản cập nhật.")
                if messagebox.askyesno("Cập nhật Tin Nóng",
                                       f"{error}\n\nTải ZIP để giải nén vào thư mục bạn có quyền ghi?"):
                    webbrowser.open(UPDATE_ZIP)
                return
            try:
                subprocess.Popen([sys.executable, str(Path(__file__).resolve())])
            except OSError as error:
                messagebox.showerror("Tin Nóng",
                                     f"Đã cài bản {label} nhưng không tự mở được. Mở lại Mo-Tin-Nong.bat.\n\n{error}")
            self.root.destroy()
        else:
            self.status.set(f"Có bản {label} trên GitHub.")

    def change_country(self, _):
        self.results = []
        self.topic.current(0)
        self.render()
        if self.busy:
            self.status.set(f"Đang chờ quét nguồn {self.country.get()}…")
        else:
            self.scan()

    def scan(self):
        if self.busy:
            return
        self.busy = True
        self.scan_button.state(["disabled"])
        country = self.country.get()
        self.status.set(f"Đang tải RSS · {country}…")
        threading.Thread(target=self.collect, args=(country,), daemon=True).start()

    def collect(self, country):
        rows, failed = [], []
        feeds = FEEDS_BY_COUNTRY[country]
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(feeds)) as pool:
            for feed, future in zip(feeds, [pool.submit(read_feed, f) for f in feeds]):
                try:
                    rows.extend(future.result())
                except Exception:
                    failed.append(f"{feed[0]} / {feed[1]}")
        self.mailbox.put((country, rank(rows, dt.datetime.now(dt.timezone.utc)), failed))

    def poll(self):
        self.root.after(150, self.poll)
        try:
            country, results, failed = self.mailbox.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.scan_button.state(["!disabled"])
            if country != self.country.get():
                self.scan()
                self.finish_update()
                return
            total = len(FEEDS_BY_COUNTRY[country])
            stamp = dt.datetime.now().strftime("%H:%M:%S")
            if len(failed) == total:
                self.status.set(f"{stamp} · Không tải được RSS. Kiểm tra mạng rồi bấm Quét ngay. Danh sách cũ được giữ lại.")
            else:
                self.results = results
                self.render()
                details = " · Lỗi: " + ", ".join(failed) if failed else ""
                self.status.set(f"{stamp} · {country} · {len(results)} nhóm tin · {total-len(failed)}/{total} luồng RSS{details}")
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
