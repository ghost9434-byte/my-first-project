"""네이버 블로그 임시저장 도우미.

posts/<글폴더>/post.json 에 적힌 제목·본문·사진을 네이버 블로그 글쓰기 창에
차례로 넣고 '저장'(임시저장)까지 누른다. 발행은 사람이 직접 한다.

사용법:
    python3 blog_bot.py login                    # 처음 한 번: 전용 크롬 창에서 네이버 로그인
    python3 blog_bot.py post                     # 아직 안 올린 글 중 가장 오래된 것을 임시저장
    python3 blog_bot.py post 2026-10-10-sodo --step   # 특정 글, 단계마다 멈춰서 확인
    python3 blog_bot.py check 2026-10-10-sodo         # 글 파일만 점검 (브라우저 안 띄움)
"""

import argparse
import html as html_lib
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Error as PWError
from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

BASE = Path(__file__).resolve().parent
PROFILE_DIR = Path(os.environ.get("NAVER_BOT_PROFILE", Path.home() / ".naver-blog-bot" / "chrome-profile"))
LOG_DIR = BASE / "logs"
POSTED_FILE = BASE / ".posted"  # 이 맥에서 이미 임시저장한 글 목록
MOD = "Meta" if sys.platform == "darwin" else "Control"
DOC_END = "Meta+ArrowDown" if sys.platform == "darwin" else "Control+End"
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".bmp"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".avi", ".wmv", ".mkv", ".mpg", ".mpeg", ".3gp", ".webm"}
# 동영상은 네이버 서버로 올라가는 데 시간이 걸린다 (큰 파일은 몇 분)
VIDEO_TIMEOUT = int(os.environ.get("NAVER_BOT_VIDEO_TIMEOUT", "900"))

# 시험용 설정 (평소에는 쓰지 않음)
WRITE_URL_OVERRIDE = os.environ.get("NAVER_BOT_WRITE_URL")
CHROME_PATH = os.environ.get("NAVER_BOT_CHROME")
HEADLESS = os.environ.get("NAVER_BOT_HEADLESS") == "1"
NONINTERACTIVE = os.environ.get("NAVER_BOT_NONINTERACTIVE") == "1"

TITLE_MARKS = [".se-documentTitle", ".se-section-documentTitle", ".se-title-text"]
SEL_TITLE = ", ".join(f"{m} .se-text-paragraph" for m in TITLE_MARKS)
# 편집기 본문을 감싸는 영역 (네이버 화면에 따라 이름이 다를 수 있어 차례로 찾는다)
BODY_CANDIDATES = [".se-components-wrap", ".se-main-container", ".se-content", ".se-canvas"]
NOT_TITLE = ":not(.se-documentTitle):not(.se-section-documentTitle)"
SEL_IMAGE_BTNS = [
    "button.se-image-toolbar-button",
    "button[data-name='image']",
    "button[data-log='dot.img']",
    "button:has-text('사진')",
]
SEL_VIDEO_BTNS = [
    "button.se-video-toolbar-button",
    "button[data-name='video']",
    "button[data-log='dot.video']",
    "button:has-text('동영상')",
]
# 동영상 올리기 창 안의 버튼·칸 (네이버 화면이 바뀔 수 있어 여러 이름으로 찾는다)
SEL_VIDEO_ADD = ["[class*='nvu_btn_append']", "button:has-text('동영상 추가')", "label:has-text('동영상 추가')",
                 "button:has-text('파일 선택')", "button:has-text('내 PC')", "button:has-text('추가')"]
SEL_VIDEO_TITLE = ["[class*='nvu_inp_title'] input", "input[class*='nvu_inp_title']", "input[placeholder*='제목']"]
SEL_VIDEO_DESC = ["[class*='nvu_inp_desc'] textarea", "textarea[placeholder*='정보']", "textarea[placeholder*='설명']",
                  "textarea[placeholder*='소개']"]
SEL_VIDEO_DONE = ["[class*='nvu_btn_submit']", "button:has-text('완료')", "button:has-text('등록')",
                  "button:has-text('올리기')", "button:has-text('확인')"]
SEL_VIDEO_COMP = ".se-video, .se-oglink-video, [class*='se-component-video']"


class BotError(RuntimeError):
    pass


def posted_set():
    if POSTED_FILE.exists():
        return {l.strip() for l in POSTED_FILE.read_text(encoding="utf-8").splitlines() if l.strip()}
    return set()


def mark_posted(folder):
    with POSTED_FILE.open("a", encoding="utf-8") as f:
        f.write(folder + "\n")


def shared_post_folders():
    """GitHub로 받은 글 폴더만 (맥에서 로컬 클로드가 쓰는 중인 글은 빼기 위해).
    git 저장소가 아니면 모든 글 폴더."""
    import subprocess
    try:
        out = subprocess.run(["git", "-C", str(BASE), "ls-files", "posts"], capture_output=True, text=True, timeout=10)
        if out.returncode == 0:
            return {Path(f).parts[1] for f in out.stdout.splitlines() if f.endswith("/post.json") and len(Path(f).parts) >= 3}
    except Exception:
        pass
    return None


def next_unposted():
    """아직 올리지 않은 글 가운데 가장 오래된 것을 고른다. (폴더 이름 없이 실행할 때)
    로컬 클로드가 쓰는 중인 글은 집지 않도록, GitHub로 받은 글만 고른다."""
    done = posted_set()
    shared = shared_post_folders()
    folders = sorted(p.name for p in (BASE / "posts").iterdir()
                     if (p / "post.json").exists() and (shared is None or p.name in shared))
    todo = [f for f in folders if f not in done]
    return todo[0] if todo else None


# ---------- 글 파일 ----------
def load_post(folder):
    post_dir = (BASE / "posts" / folder).resolve()
    path = post_dir / "post.json"
    if not path.exists():
        raise BotError(f"글 파일이 없습니다: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise BotError(f"post.json 형식이 잘못되었습니다: {e}")
    problems = []
    if not data.get("blog_id"):
        problems.append("blog_id 가 없습니다")
    if not data.get("title", "").strip():
        problems.append("title(제목)이 비어 있습니다")
    blocks = data.get("blocks") or []
    if not blocks:
        problems.append("blocks(본문)가 비어 있습니다")
    for i, b in enumerate(blocks, 1):
        kind = b.get("type")
        if kind == "image":
            files = b["files"] if "files" in b else [b.get("file")]
            for f in files:
                if not f:
                    problems.append(f"{i}번째 사진 블록에 파일 이름이 없습니다")
                    continue
                p = post_dir / f
                if not p.exists():
                    problems.append(f"{i}번째 사진 파일이 없습니다: {f}")
                elif p.suffix.lower() not in IMAGE_EXT:
                    problems.append(f"{i}번째 사진 형식이 이상합니다: {f}")
        elif kind == "video":
            f = b.get("file")
            if not f:
                problems.append(f"{i}번째 동영상 블록에 파일 이름이 없습니다")
            elif not (post_dir / f).exists():
                problems.append(f"{i}번째 동영상 파일이 없습니다: {f}")
            elif (post_dir / f).suffix.lower() not in VIDEO_EXT:
                problems.append(f"{i}번째 동영상 형식이 이상합니다: {f}")
        elif kind == "html":
            if not b.get("html", "").strip():
                problems.append(f"{i}번째 글 블록이 비어 있습니다")
        else:
            problems.append(f"{i}번째 블록 종류를 모르겠습니다: {kind}")
    if problems:
        raise BotError("글 파일에 문제가 있습니다:\n  - " + "\n  - ".join(problems))
    return post_dir, data


def login_state(ctx):
    """네이버 로그인 쿠키(NID_AUT)로 상태를 본다.
    kept: 로그인 상태 유지 켜짐 / session: 로그인됐지만 창을 닫으면 풀림 / none: 로그인 안 됨"""
    try:
        cookies = ctx.cookies("https://nid.naver.com")
    except Exception:
        return "none"
    aut = [c for c in cookies if c.get("name") == "NID_AUT"]
    if not aut:
        return "none"
    return "kept" if any(c.get("expires", -1) not in (-1, None) and c["expires"] > 0 for c in aut) else "session"


def on_login_page(page):
    """로그인 화면이 창 전체나 안쪽 틀(iframe) 어디에든 떠 있는지."""
    try:
        return any("nid.naver.com" in (f.url or "") for f in page.frames)
    except Exception:
        return "nid.naver.com" in page.url


def norm(t):
    """카테고리 이름 비교용: 공백과 가운뎃점 모양 차이를 없앤다."""
    return re.sub(r"[\s·・･.ㆍ‧∙•]", "", t or "")


def html_to_plain(h):
    t = re.sub(r"<br\s*/?>", "\n", h)
    t = re.sub(r"<hr\s*/?>", "\n", t)
    t = re.sub(r"</(p|h\d|li|tr|div|blockquote)>", "\n", t)
    t = re.sub(r"</t[dh]>", "\t", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = html_lib.unescape(t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


class Bot:
    def __init__(self, step=False, no_publish=False):
        self.step = step
        self.no_publish = no_publish
        self.shot_no = 0
        self.run_dir = LOG_DIR / datetime.now().strftime("%Y%m%d-%H%M%S")
        self.page = None
        self.body_sel = ".se-components-wrap"

    # ---------- 공통 ----------
    def open_browser(self, pw):
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        opts = dict(
            headless=HEADLESS,
            no_viewport=True,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
            # '자동화된 소프트웨어가 제어 중' 표시를 끈다 (네이버 로그인 화면이 막히지 않도록)
            ignore_default_args=["--enable-automation"],
        )
        if CHROME_PATH:
            opts["executable_path"] = CHROME_PATH
        else:
            opts["channel"] = "chrome"  # 맥에 깔린 구글 크롬을 그대로 사용
        if HEADLESS:
            opts.pop("no_viewport")
            opts["viewport"] = {"width": 1400, "height": 1000}
        try:
            ctx = pw.chromium.launch_persistent_context(str(PROFILE_DIR), **opts)
        except PWError as e:
            msg = str(e)
            if "ProcessSingleton" in msg or "profile" in msg.lower() and "in use" in msg.lower():
                raise BotError("이전에 열린 자동화용 크롬 창이 아직 켜져 있습니다. 그 창을 닫고 다시 실행해 주세요.")
            if "chrome" in msg.lower() and ("not found" in msg.lower() or "executable" in msg.lower()):
                raise BotError("구글 크롬을 찾지 못했습니다. 크롬을 설치한 뒤 다시 실행해 주세요.")
            raise
        origins = ["https://blog.naver.com", "https://nid.naver.com"]
        if WRITE_URL_OVERRIDE:
            m = re.match(r"^(https?://[^/]+)", WRITE_URL_OVERRIDE)
            if m:
                origins.append(m.group(1))
        for origin in origins:
            try:
                ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=origin)
            except Exception:
                pass
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_default_timeout(15000)
        self.page = page
        return ctx, page

    def shot(self, name):
        """단계별 화면을 logs/ 에 남긴다. 막히면 이 사진을 보내 주시면 된다."""
        if not self.page:
            return None
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.shot_no += 1
        path = self.run_dir / f"{self.shot_no:02d}-{name}.png"
        try:
            self.page.screenshot(path=str(path))
        except Exception:
            return None
        return path

    def wait(self, sec):
        """기다리는 동안에도 브라우저 소식을 받도록 time.sleep 대신 이것을 쓴다."""
        if self.page:
            self.page.wait_for_timeout(int(sec * 1000))
        else:
            time.sleep(sec)

    def say(self, msg):
        print(f"▶ {msg}", flush=True)
        if self.step and not NONINTERACTIVE:
            input("  확인하셨으면 엔터를 누르세요... ")

    def wait_enter(self, msg):
        if not NONINTERACTIVE:
            input(msg)

    # ---------- 로그인 ----------
    def login(self):
        with sync_playwright() as pw:
            ctx, page = self.open_browser(pw)
            if login_state(ctx) == "kept":
                ctx.close()
                print("✅ 이미 로그인되어 있습니다. 바로 글을 올리시면 됩니다.")
                return
            page.goto("https://nid.naver.com/nidlogin.login")
            for attempt in range(2):
                if not self.wait_for_login(page):
                    break
                self.wait(2)
                state = login_state(ctx)
                if state == "kept":
                    ctx.close()
                    print("✅ 로그인이 저장되었습니다. 다음부터는 로그인 없이 바로 진행됩니다.")
                    return
                if state == "session" and attempt == 0:
                    print("⚠️ '로그인 상태 유지'가 꺼져 있습니다. 이대로면 창을 닫을 때 로그인이 풀립니다.")
                    print("   열린 창에서 '로그인 상태 유지'에 체크하고 한 번 더 로그인해 주세요.")
                    ctx.clear_cookies()
                    page.goto("https://nid.naver.com/nidlogin.login")
                    continue
                break
            state = login_state(ctx)
            ctx.close()
            if state == "session":
                print("⚠️ 로그인은 됐지만 '로그인 상태 유지'가 꺼져 있습니다. 글 올릴 때 다시 로그인하라고 나올 수 있습니다.")
            else:
                print("❌ 로그인을 확인하지 못했습니다. 'bash login.sh' 를 다시 실행해 주세요.")

    # ---------- 글쓰기 화면 ----------
    def editor_frame(self, page, timeout=60):
        """글쓰기 화면이 뜬 틀(frame)을 찾고, 본문 영역 이름도 정한다."""
        end = time.time() + timeout
        while time.time() < end:
            if on_login_page(page):
                return None
            candidates = []
            fr = page.frame(name="mainFrame")
            if fr:
                candidates.append(fr)
            candidates.append(page.main_frame)
            candidates.extend(f for f in page.frames if f not in candidates)
            for target in candidates:
                try:
                    if not any(target.locator(m).count() > 0 for m in TITLE_MARKS):
                        continue
                    for body in BODY_CANDIDATES:
                        if target.locator(f"{body} .se-component").count() > 0:
                            self.body_sel = body
                            return target
                except Exception:
                    pass
            self.wait(0.5)
        self.diagnose(page)
        raise BotError("글쓰기 화면을 찾지 못했습니다. (진단 기록을 남겼습니다)")

    def diagnose(self, page):
        """글쓰기 화면을 못 찾았을 때 클로드가 고칠 수 있도록 화면 구조를 기록한다."""
        self.run_dir.mkdir(parents=True, exist_ok=True)
        keys = ["se-documentTitle", "se-section-documentTitle", "se-title-text", "se-components-wrap",
                "se-main-container", "se-content", "se-canvas", "se-component", "se-text-paragraph",
                "se-image-toolbar-button", "se-popup", "se-help-panel"]
        lines = [f"top: {page.url}"]
        for i, f in enumerate(page.frames):
            try:
                counts = f.evaluate("ks => ks.map(k => k + '=' + document.getElementsByClassName(k).length).join(' ')", keys)
                title = f.evaluate("() => document.title")
                lines.append(f"frame{i} name={f.name!r} url={f.url[:120]} title={title!r}\n   {counts}")
                html = f.content()
                (self.run_dir / f"frame{i}.html").write_text(html[:400000], encoding="utf-8")
            except Exception as e:
                lines.append(f"frame{i} url={f.url[:120]} (읽기 실패: {e})")
        report = "\n".join(lines)
        (self.run_dir / "진단.txt").write_text(report, encoding="utf-8")
        self.shot("diagnose")
        print("\n----- 진단 기록 (이 부분을 캡처해서 클로드에게 보내 주세요) -----")
        print(report)
        print("-----------------------------------------------------------")

    def wait_for_login(self, page, minutes=10):
        """회장님이 크롬 창에서 로그인할 때까지 기다린다. 로그인 쿠키가 생기면 바로 넘어간다."""
        try:
            page.bring_to_front()
        except Exception:
            pass
        print(f"\n네이버 로그인이 필요합니다. 자동화용 크롬 창에서 로그인해 주세요. (최대 {minutes}분 기다립니다)")
        print("  · 크롬 창이 안 보이면 ⌘+Tab 으로 크롬을 찾아 주세요.")
        print("  · '로그인 상태 유지'에 체크하시면 다음부터는 이 단계가 없습니다.")
        print("  · '새로운 기기' 확인 화면이 나오면 '등록' 또는 '등록 안함'을 눌러 주세요.")
        end = time.time() + minutes * 60
        last_note = time.time()
        while time.time() < end:
            if login_state(page.context) != "none" or not on_login_page(page):
                self.wait(1.5)  # 로그인 뒤 넘어가는 화면이 끝나도록 잠깐 기다림
                return True
            if time.time() - last_note > 30:
                left = int((end - time.time()) // 60)
                print(f"  …기다리는 중 (약 {left}분 남음) 현재 화면: {page.url[:70]}", flush=True)
                self.shot("login-wait")
                last_note = time.time()
            self.wait(1)
        return False

    def open_editor(self, page, write_url):
        page.goto(write_url, wait_until="domcontentloaded")
        fr = self.editor_frame(page)
        if fr is None:
            if not self.wait_for_login(page):
                raise BotError("로그인이 끝나지 않았습니다. 'bash login.sh' 로 먼저 로그인해 주세요.")
            if login_state(page.context) == "session":
                print("⚠️ '로그인 상태 유지'가 꺼져 있어, 이번 작업이 끝나면 로그인이 풀립니다. 다음엔 체크해 주세요.")
            print("✅ 로그인 확인. 글쓰기 화면으로 갑니다.")
            page.goto(write_url, wait_until="domcontentloaded")
            fr = self.editor_frame(page)
            if fr is None:
                raise BotError("로그인 뒤에도 글쓰기 화면이 열리지 않았습니다.")
        return fr

    def dismiss_popups(self, fr):
        self.wait(1.5)  # 팝업이 늦게 뜨는 경우가 있다
        # '작성 중인 글이 있습니다' → 취소(새로 쓰기)
        for sel in [".se-popup-button-cancel", ".se-popup button:has-text('취소')"]:
            try:
                btn = fr.locator(sel).first
                if btn.count() and btn.is_visible():
                    btn.click()
                    self.wait(0.5)
                    break
            except Exception:
                pass
        # 도움말 패널 닫기
        for sel in [".se-help-panel-close-button"]:
            try:
                btn = fr.locator(sel).first
                if btn.count() and btn.is_visible():
                    btn.click()
            except Exception:
                pass

    # ---------- 본문 넣기 ----------
    def sel_comp(self, extra=""):
        return f"{self.body_sel} .se-component{NOT_TITLE}{extra}"

    def sel_text_para(self):
        return f"{self.body_sel} .se-component.se-text{NOT_TITLE} .se-text-paragraph"

    def body_length(self, fr):
        try:
            return fr.locator(self.body_sel).first.evaluate("e => e.innerText.replace(/\\s/g,'').length")
        except Exception:
            return -1

    def paste_html(self, fr, html, plain):
        """서식(소제목·굵게·표·구분선)을 살려 붙여 넣는다. 안 되면 글자만이라도 넣는다."""
        page = self.page
        before = self.body_length(fr)

        # 1) 편집기에 직접 '붙여넣기' 신호 보내기 (클립보드 권한 필요 없음)
        fr.evaluate(
            """([h, t]) => {
                const el = document.activeElement || document.body;
                const dt = new DataTransfer();
                dt.setData('text/html', h);
                dt.setData('text/plain', t);
                el.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true}));
            }""",
            [html, plain],
        )
        self.wait(0.8)
        if self.body_length(fr) > before:
            return "서식 붙여넣기"

        # 2) 실제 클립보드에 넣고 ⌘V
        ok = False
        try:
            ok = fr.evaluate(
                """async ([h, t]) => {
                    try {
                        await navigator.clipboard.write([new ClipboardItem({
                            'text/html': new Blob([h], {type: 'text/html'}),
                            'text/plain': new Blob([t], {type: 'text/plain'}),
                        })]);
                        return true;
                    } catch (e) { return false; }
                }""",
                [html, plain],
            )
        except Exception:
            ok = False
        if ok:
            page.keyboard.press(f"{MOD}+V")
            self.wait(1.0)
            if self.body_length(fr) > before:
                return "클립보드 붙여넣기"

        # 3) 서식 없이 글자 입력
        page.keyboard.insert_text(plain)
        self.wait(0.5)
        if self.body_length(fr) > before:
            return "글자만 입력(서식 없음)"
        raise BotError("본문 글이 들어가지 않았습니다.")

    def find_image_button(self, fr):
        for sel in SEL_IMAGE_BTNS:
            loc = fr.locator(sel).first
            try:
                if loc.count() > 0 and loc.is_visible():
                    return loc
            except Exception:
                pass
        return None

    def insert_images(self, fr, paths):
        page = self.page
        before = fr.locator(self.sel_comp(".se-image")).count()
        files = [str(p) for p in paths]
        btn = self.find_image_button(fr)
        done = False
        if btn is not None:
            try:
                with page.expect_file_chooser(timeout=8000) as fc:
                    btn.click()
                fc.value.set_files(files)
                done = True
            except PWTimeout:
                done = False
        if not done:
            # 버튼이 파일 창을 안 띄우면 숨은 파일 입력칸에 바로 넣는다
            # 사진용 칸을 먼저 고른다 (동영상용 칸에 사진을 넣지 않도록)
            for sel in ["input[type=file][accept*='image']", "input[type=file]:not([accept*='video'])"]:
                inputs = fr.locator(sel)
                if inputs.count():
                    break
            if inputs.count() == 0:
                raise BotError("사진 버튼을 찾지 못했습니다. (네이버 화면이 바뀌었을 수 있습니다)")
            inputs.last.set_input_files(files)

        # 여러 장이면 '개별사진/콜라주/슬라이드' 선택 창이 뜰 수 있다 → 개별사진
        if len(files) > 1:
            for sel in ["button:has-text('개별사진')", ".se-image-type-popup button >> nth=0"]:
                try:
                    b = fr.locator(sel).first
                    if b.count() and b.is_visible():
                        b.click()
                        break
                except Exception:
                    pass

        end = time.time() + 60
        while time.time() < end:
            if fr.locator(self.sel_comp(".se-image")).count() > before:
                break
            self.wait(0.5)
        else:
            raise BotError("사진이 올라가지 않았습니다. (1분 기다렸습니다)")
        # 업로드가 끝날 때까지 조금 더 기다린다
        end = time.time() + 30
        while time.time() < end:
            try:
                if fr.locator(f"{self.body_sel} .se-image-uploading, {self.body_sel} .se-is-uploading").count() == 0:
                    break
            except Exception:
                break
            self.wait(0.5)
        self.wait(1.0)

    # ---------- 동영상 ----------
    def all_frames(self, fr):
        return [fr] + [f for f in self.page.frames if f != fr]

    def find_visible(self, fr, sels, enabled=False):
        """편집기와 다른 모든 틀에서, 보이는 첫 번째 요소를 찾는다."""
        for sel in sels:
            for f in self.all_frames(fr):
                try:
                    loc = f.locator(sel)
                    for i in range(min(loc.count(), 5)):
                        el = loc.nth(i)
                        if not el.is_visible():
                            continue
                        if enabled and (not el.is_enabled() or "disable" in (el.get_attribute("class") or "")
                                        or el.get_attribute("aria-disabled") == "true"):
                            continue
                        return el
                except Exception:
                    pass
        return None

    def video_uploading(self, fr):
        """올리는 중 표시(숫자 %, '업로드 중')가 보이면 True."""
        js = r"""() => [...document.querySelectorAll('body *')].some(e => {
            if (e.children.length || !e.offsetParent) return false;
            const t = (e.innerText || '').trim();
            return /^(\d{1,2}(\.\d+)?\s*%|.*업로드\s*중.*|.*올리는\s*중.*)$/.test(t);
        })"""
        for f in self.all_frames(fr):
            try:
                if f.evaluate(js):
                    return True
            except Exception:
                pass
        return False

    def insert_video(self, fr, path, title="", desc=""):
        """동영상 버튼 → 파일 고르기 → 제목·설명 → 다 올라가면 '완료'."""
        page = self.page
        comp = self.sel_comp("") + ":is(" + SEL_VIDEO_COMP + ")"
        before = fr.locator(comp).count()
        btn = self.find_visible(fr, SEL_VIDEO_BTNS)
        if btn is None:
            raise BotError("동영상 버튼을 찾지 못했습니다. (네이버 화면이 바뀌었을 수 있습니다)")
        chosen = False
        try:  # 버튼이 바로 파일 창을 띄우는 경우
            with page.expect_file_chooser(timeout=5000) as fc:
                btn.click(timeout=5000)
            fc.value.set_files(str(path))
            chosen = True
        except PWTimeout:
            pass
        self.wait(1.0)
        if not chosen:  # '동영상 올리기' 창이 뜬 경우 → '동영상 추가'
            add = self.find_visible(fr, SEL_VIDEO_ADD)
            if add is not None:
                try:
                    with page.expect_file_chooser(timeout=5000) as fc:
                        add.click(timeout=5000)
                    fc.value.set_files(str(path))
                    chosen = True
                except PWTimeout:
                    pass
        if not chosen:  # 숨은 파일 칸에 바로 넣기 (동영상용 칸을 먼저)
            for sel in ["input[type=file][accept*='video']", "input[type=file]:not([accept*='image'])"]:
                for f in self.all_frames(fr):
                    try:
                        loc = f.locator(sel)
                        if loc.count():
                            loc.last.set_input_files(str(path))
                            chosen = True
                            break
                    except Exception:
                        pass
                if chosen:
                    break
        if not chosen:
            raise BotError("동영상 파일을 고르는 칸을 찾지 못했습니다.")
        self.shot("video-chosen")
        print(f"  동영상을 올리는 중입니다: {Path(path).name} (큰 파일은 몇 분 걸립니다)", flush=True)

        # 제목·설명 (제목은 네이버가 꼭 요구한다)
        self.wait(1.5)
        t = self.find_visible(fr, SEL_VIDEO_TITLE)
        if t is not None and title:
            try:
                t.fill(title[:60])
            except Exception:
                pass
        d = self.find_visible(fr, SEL_VIDEO_DESC)
        if d is not None and desc:
            try:
                d.fill(desc)
            except Exception:
                pass

        # 다 올라가서 '완료'가 눌릴 수 있을 때까지 기다린다
        start = time.time()
        end = start + VIDEO_TIMEOUT
        last_note = start
        clicked = False
        while time.time() < end:
            if fr.locator(comp).count() > before:  # 올리기 창 없이 바로 본문에 들어간 경우
                clicked = True
                break
            # 올리기가 시작되기도 전에 '완료'를 누르지 않도록 처음 3초는 기다린다
            if time.time() - start > 3 and not self.video_uploading(fr):
                done = self.find_visible(fr, SEL_VIDEO_DONE, enabled=True)
                if done is not None:
                    self.shot("video-ready")
                    self.safe_click(done, "동영상 완료 버튼")
                    clicked = True
                    break
            if time.time() - last_note > 30:
                print(f"  …동영상 올리는 중 ({int(end - time.time()) // 60}분 더 기다릴 수 있음)", flush=True)
                self.shot("video-uploading")
                last_note = time.time()
            self.wait(1.0)
        if not clicked:
            limit = f"{VIDEO_TIMEOUT // 60}분" if VIDEO_TIMEOUT >= 60 else f"{VIDEO_TIMEOUT}초"
            raise BotError(f"동영상이 {limit} 안에 다 올라가지 않았습니다.")

        end = time.time() + 120
        while time.time() < end:
            if fr.locator(comp).count() > before:
                break
            self.wait(1.0)
        else:
            raise BotError("완료를 눌렀지만 본문에 동영상이 보이지 않습니다.")
        self.wait(1.0)

    def close_video_layer(self, fr):
        """동영상 넣기에 실패했을 때 열린 창을 닫고 본문으로 돌아온다."""
        self.page.keyboard.press("Escape")
        self.wait(0.5)
        for sel in ["[class*='nvu_btn_cancel']", "[class*='nvu_btn_close']", "button:has-text('취소')",
                    "button:has-text('닫기')", "button[class*='close']"]:
            b = self.find_visible(fr, [sel])
            if b is not None:
                try:
                    b.click(timeout=2000)
                    self.wait(0.5)
                except Exception:
                    pass
        cancel = self.find_visible(fr, ["button:has-text('확인')"])  # '업로드를 취소할까요?' 같은 물음
        if cancel is not None:
            try:
                cancel.click(timeout=2000)
            except Exception:
                pass

    def safe_click(self, loc, what="편집기"):
        """사진을 넣은 직후 네이버가 투명한 선택 막(se-selection)을 덮어 클릭을 가로막는 경우가 있다.
        1) 그냥 클릭 → 2) Esc로 선택을 풀고 다시 클릭 → 3) 막을 무시하고 그 줄에 직접 커서를 놓는다."""
        page = self.page
        try:
            loc.click(timeout=3000)
            return "click"
        except PWTimeout:
            pass
        page.keyboard.press("Escape")
        self.wait(0.5)
        try:
            loc.click(timeout=3000)
            return "esc+click"
        except PWTimeout:
            pass
        try:
            loc.evaluate(
                """el => {
                    el.scrollIntoView({block: 'center'});
                    const r = el.getBoundingClientRect();
                    const opt = {bubbles: true, cancelable: true, view: window,
                                 clientX: r.right - 2, clientY: r.top + r.height / 2};
                    for (const t of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'])
                        el.dispatchEvent(new (t.startsWith('pointer') ? PointerEvent : MouseEvent)(t, opt));
                    const sel = el.ownerDocument.getSelection();
                    const range = el.ownerDocument.createRange();
                    range.selectNodeContents(el);
                    range.collapse(false);
                    sel.removeAllRanges();
                    sel.addRange(range);
                    if (el.focus) el.focus();
                }"""
            )
            self.wait(0.3)
            return "direct"
        except Exception as e:
            raise BotError(f"{what}을(를) 누르지 못했습니다: {e}")

    def cursor_to_end(self, fr):
        """커서를 본문 맨 끝 빈 줄로 옮긴다. 마지막이 글이 아니면 새 줄을 만든다."""
        page = self.page
        last = fr.locator(self.sel_comp()).last
        cls = last.get_attribute("class") or ""
        if "se-text" in cls:
            self.safe_click(last.locator(".se-text-paragraph").last, "마지막 줄")
            page.keyboard.press(DOC_END)
            page.keyboard.press("End")
            return
        self.safe_click(last, "마지막 사진")
        self.wait(0.3)
        page.keyboard.press("Enter")
        self.wait(0.5)
        last = fr.locator(self.sel_comp()).last
        if "se-text" in (last.get_attribute("class") or ""):
            self.safe_click(last.locator(".se-text-paragraph").last, "새 줄")
            page.keyboard.press("End")
            return
        raise BotError("사진 다음 줄로 커서를 옮기지 못했습니다.")

    # ---------- 저장 ----------
    def save_draft(self, fr):
        page = self.page
        tries = [
            fr.locator("button[class*='save_btn']"),
            fr.get_by_role("button", name=re.compile(r"^\s*저장")),
            page.locator("button[class*='save_btn']"),
            page.get_by_role("button", name=re.compile(r"^\s*저장")),
        ]
        for loc in tries:
            try:
                if loc.count() > 0 and loc.first.is_visible():
                    loc.first.click()
                    self.wait(2.5)
                    return True
            except Exception:
                pass
        # 단축키(⌘S)도 시도
        try:
            page.keyboard.press(f"{MOD}+S")
            self.wait(2.5)
            return None
        except Exception:
            return False

    # ---------- 발행 ----------
    def publish(self, fr, category, tags):
        """발행 창을 열어 카테고리를 고르고 태그를 넣은 뒤 발행한다.
        카테고리를 못 찾으면 발행하지 않고 창을 닫는다(임시저장은 이미 되어 있음)."""
        page = self.page
        opened = False
        for loc in [fr.locator("button[class*='publish_btn']"),
                    fr.get_by_role("button", name=re.compile(r"^\s*발행\s*$")),
                    page.locator("button[class*='publish_btn']")]:
            try:
                if loc.count() > 0 and loc.first.is_visible():
                    self.safe_click(loc.first, "발행 버튼")
                    opened = True
                    break
            except Exception:
                pass
        if not opened:
            return False, "발행 버튼을 찾지 못했습니다"
        self.wait(1.5)
        self.shot("publish-layer")

        # 카테고리
        if category:
            want = norm(category)
            sel_btn = None
            for loc in [fr.locator("button[class*='selectbox_button']"),
                        fr.locator("[class*='publish'] button[aria-haspopup]"),
                        fr.locator("button[class*='category']")]:
                try:
                    if loc.count() > 0 and loc.first.is_visible():
                        sel_btn = loc.first
                        break
                except Exception:
                    pass
            if sel_btn is None:
                self.diagnose_layer(fr)
                return False, "카테고리 선택 칸을 찾지 못했습니다"
            if norm(sel_btn.inner_text()) != want:
                self.safe_click(sel_btn, "카테고리 선택 칸")
                self.wait(0.8)
                picked = False
                gap_chars = r"[\s·・･.ㆍ‧∙•]*"
                pattern = re.compile("^" + gap_chars + gap_chars.join(re.escape(ch) for ch in want) + gap_chars + "$")
                options = fr.get_by_text(pattern)
                for i in range(min(options.count(), 10)):
                    o = options.nth(i)
                    try:
                        if o.is_visible():
                            self.safe_click(o, "카테고리")
                            picked = True
                            self.wait(0.4)
                            if norm(sel_btn.inner_text()) == want:
                                break
                    except Exception:
                        pass
                self.wait(0.6)
                if not picked or norm(sel_btn.inner_text()) != want:
                    self.diagnose_layer(fr)
                    page.keyboard.press("Escape")
                    return False, f"카테고리 '{category}'를 찾지 못했습니다"
            print(f"  카테고리: {sel_btn.inner_text().strip()}")

        # 태그
        if tags:
            inp = fr.locator("input[placeholder*='태그'], input[class*='tag_input']").first
            try:
                if inp.count() > 0 and inp.is_visible():
                    for t in tags:
                        self.safe_click(inp, "태그 칸")
                        page.keyboard.insert_text(t.lstrip("#"))
                        page.keyboard.press("Enter")
                        self.wait(0.25)
                    print(f"  태그: {', '.join(tags)}")
                else:
                    print("  ⚠️ 태그 칸을 찾지 못해 태그 없이 발행합니다.")
            except Exception:
                print("  ⚠️ 태그를 넣지 못해 태그 없이 발행합니다.")

        dump = os.environ.get("NAVER_BOT_DUMP")
        if dump:  # 시험용: 발행 직전 상태
            info = fr.evaluate("""() => ({
                category: (document.querySelector("button[class*='selectbox_button']") || {}).innerText || '',
                tags: [...document.querySelectorAll("[class*='tag_item']")].map(e => e.innerText.trim()),
            })""")
            Path(dump + ".publish.json").write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")

        self.shot("publish-ready")
        self.say("카테고리와 태그를 넣었습니다. 이제 발행합니다.")
        confirm = None
        for loc in [fr.locator("button[data-testid='seOnePublishBtn']"),
                    fr.locator("button[class*='confirm_btn']"),
                    fr.get_by_role("button", name=re.compile(r"^\s*발행\s*$")).last]:
            try:
                if loc.count() > 0 and loc.first.is_visible():
                    confirm = loc.first if loc.count() else loc
                    break
            except Exception:
                pass
        if confirm is None:
            self.diagnose_layer(fr)
            return False, "마지막 발행 버튼을 찾지 못했습니다"
        self.safe_click(confirm, "마지막 발행 버튼")

        # 글쓰기 화면이 사라지면 발행된 것
        end = time.time() + 30
        while time.time() < end:
            self.wait(1)
            try:
                still = any(f.locator(".se-documentTitle").count() > 0 for f in page.frames)
            except Exception:
                still = True
            if not still:
                self.shot("published")
                return True, page.url
        self.shot("publish-unknown")
        return False, "발행 버튼은 눌렀지만 발행 완료를 확인하지 못했습니다. 블로그에서 확인해 주세요"

    def diagnose_layer(self, fr, what="발행 창"):
        """발행 창·동영상 창에서 막혔을 때, 보이는 글자와 버튼을 기록한다."""
        try:
            texts = fr.evaluate("""() => [...document.querySelectorAll('button, label, li, input')]
                .filter(e => e.offsetParent !== null)
                .map(e => (e.tagName + '.' + (e.className || '').toString().slice(0, 40) + ' ' +
                           (e.innerText || e.placeholder || '').trim().slice(0, 30)))
                .slice(0, 80)""")
        except Exception as e:
            texts = [f"(읽기 실패: {e})"]
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / f"{what.replace(' ', '')}_진단.txt").write_text("\n".join(texts), encoding="utf-8")
        self.shot("layer-diagnose")
        print(f"\n----- {what} 진단 (이 부분을 캡처해서 클로드에게 보내 주세요) -----")
        print("\n".join(texts[:40]))
        print("------------------------------------------------------------")

    # ---------- 전체 흐름 ----------
    def post(self, folder):
        post_dir, data = load_post(folder)
        write_url = WRITE_URL_OVERRIDE or f"https://blog.naver.com/{data['blog_id']}?Redirect=Write&"
        report = []
        video_failed = []

        with sync_playwright() as pw:
            ctx, page = self.open_browser(pw)
            try:
                fr = self.open_editor(page, write_url)
                self.dismiss_popups(fr)
                self.shot("editor-open")
                self.say("글쓰기 화면이 열렸습니다.")

                # 제목
                self.safe_click(fr.locator(SEL_TITLE).first, "제목 칸")
                page.keyboard.insert_text(data["title"].strip())
                self.wait(0.3)
                got = fr.locator(SEL_TITLE).first.inner_text().strip()
                if data["title"].strip() not in got:
                    raise BotError(f"제목이 제대로 들어가지 않았습니다. (들어간 것: {got!r})")
                self.shot("title")
                self.say(f"제목을 넣었습니다: {got}")

                # 본문 첫 줄로
                self.safe_click(fr.locator(self.sel_text_para()).first, "본문 첫 줄")

                for i, block in enumerate(data["blocks"], 1):
                    kind = block["type"]
                    if kind == "image":
                        names = block["files"] if "files" in block else [block["file"]]
                        self.insert_images(fr, [post_dir / n for n in names])
                        self.cursor_to_end(fr)
                        how = f"사진 {len(names)}장"
                    elif kind == "video":
                        try:
                            self.insert_video(fr, post_dir / block["file"], block.get("title") or data["title"],
                                              block.get("desc", ""))
                            how = "동영상"
                        except BotError as e:
                            # 동영상 하나 때문에 글 전체를 버리지 않는다. 대신 발행은 하지 않는다.
                            self.shot("video-error")
                            self.diagnose_layer(fr, "동영상 창")
                            self.close_video_layer(fr)
                            video_failed.append(f"{block['file']}: {e}")
                            how = f"동영상 실패 ({e})"
                        self.cursor_to_end(fr)
                    else:
                        plain = block.get("plain") or html_to_plain(block["html"])
                        how = self.paste_html(fr, block["html"], plain)
                        self.cursor_to_end(fr)
                    report.append(f"{i}. {kind}: {how}")
                    self.shot(f"block{i:02d}-{kind}")
                    self.say(f"{i}번째 내용을 넣었습니다 ({how}).")

                img_need = sum(len(b["files"]) if "files" in b else 1 for b in data["blocks"] if b["type"] == "image")
                img_got = fr.locator(self.sel_comp(".se-image")).count()
                vid_need = sum(1 for b in data["blocks"] if b["type"] == "video")
                vid_got = fr.locator(self.sel_comp("") + ":is(" + SEL_VIDEO_COMP + ")").count()
                saved = self.save_draft(fr)
                self.shot("saved" if saved else "save-check")
                dump = os.environ.get("NAVER_BOT_DUMP")
                if dump:  # 시험용: 편집기 상태 기록
                    state = fr.evaluate("""sel => ({
                        title: document.querySelector('.se-documentTitle .se-text-paragraph').innerText,
                        comps: [...document.querySelectorAll(sel)].map(c => ({cls: c.className, text: c.innerText})),
                        saved: !!window.__saved,
                    })""", self.sel_comp())
                    Path(dump).write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
                published, pub_msg = None, ""
                if data.get("publish") and not self.no_publish:
                    if video_failed:
                        published, pub_msg = False, "동영상을 넣지 못해 발행하지 않았습니다"
                    else:
                        published, pub_msg = self.publish(fr, data.get("category"), data.get("tags") or [])
            except BotError:
                self.shot("error")
                self.close_after_error(ctx)
                raise
            except Exception as e:
                self.shot("error")
                self.close_after_error(ctx)
                raise BotError(f"예상하지 못한 문제가 생겼습니다: {e}")

            print("\n===== 결과 =====")
            print(f"제목: {data['title']}")
            for line in report:
                print("  " + line)
            print(f"사진: 넣을 것 {img_need}장 / 화면에서 확인된 것 {img_got}장")
            if vid_need:
                print(f"동영상: 넣을 것 {vid_need}개 / 화면에서 확인된 것 {vid_got}개")
            for v in video_failed:
                print(f"⚠️ 동영상을 넣지 못했습니다 → 블로그에서 직접 넣어 주세요: {v}")
            if published:
                print(f"✅ '{data.get('category')}' 카테고리로 발행했습니다: {pub_msg}")
            elif published is False:
                print(f"⚠️ 발행은 하지 못했습니다: {pub_msg}")
                print("   글은 임시저장되어 있으니, 블로그에서 카테고리를 고르고 직접 발행해 주세요.")
            elif saved:
                print("✅ 임시저장을 눌렀습니다. 화면을 확인하신 뒤 카테고리 고르고 발행은 직접 해 주세요.")
            elif saved is None:
                print("⚠️ 저장 버튼을 못 찾아 단축키로 저장을 시도했습니다. 화면에서 '저장'을 한 번 더 눌러 주세요.")
            else:
                print("⚠️ 저장 버튼을 찾지 못했습니다. 화면에서 직접 '저장'을 눌러 주세요.")
            if data.get("note"):
                print(f"메모: {data['note']}")
            print(f"단계별 화면: {self.run_dir}")
            self.wait_enter("\n창을 닫으려면 엔터를 누르세요... ")
            ctx.close()
            return {"saved": saved, "published": published, "report": report, "img_need": img_need, "img_got": img_got,
                    "video_failed": video_failed}

    def close_after_error(self, ctx):
        print(f"\n화면을 그대로 두었습니다. 문제를 확인하신 뒤 엔터를 누르면 창이 닫힙니다.")
        try:
            self.wait_enter("")
        finally:
            try:
                ctx.close()
            except Exception:
                pass


def main():
    ap = argparse.ArgumentParser(description="네이버 블로그 임시저장 도우미")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login", help="전용 크롬 창에서 네이버 로그인")
    p = sub.add_parser("post", help="posts/<폴더> 글을 임시저장")
    p.add_argument("folder", nargs="?", help="생략하면 아직 안 올린 글 중 가장 오래된 것")
    p.add_argument("--step", action="store_true", help="단계마다 멈춰서 확인")
    p.add_argument("--draft", action="store_true", help="발행하지 않고 임시저장만")
    c = sub.add_parser("check", help="글 파일만 점검")
    c.add_argument("folder")
    args = ap.parse_args()

    bot = Bot(step=getattr(args, "step", False), no_publish=getattr(args, "draft", False))
    try:
        if args.cmd == "login":
            bot.login()
        elif args.cmd == "check":
            post_dir, data = load_post(args.folder)
            n_img = sum(len(b["files"]) if "files" in b else 1 for b in data["blocks"] if b["type"] == "image")
            n_vid = sum(1 for b in data["blocks"] if b["type"] == "video")
            print(f"✅ 글 파일 정상: '{data['title']}' / 블록 {len(data['blocks'])}개 / 사진 {n_img}장"
                  + (f" / 동영상 {n_vid}개" if n_vid else ""))
        else:
            folder = args.folder or next_unposted()
            if not folder:
                print("올릴 새 글이 없습니다. 클로드에게 사진을 보내 새 글을 받아 주세요.")
                return
            print(f"올릴 글: {folder}")
            result = bot.post(folder)
            if result and result["saved"] is not False and not os.environ.get("NAVER_BOT_DUMP"):
                mark_posted(folder)
                left = next_unposted()
                print(f"남은 새 글: {left or '없음'}")
    except BotError as e:
        print(f"\n❌ 멈췄습니다: {e}")
        if bot.shot_no:
            print(f"logs 폴더의 마지막 사진을 클로드에게 보내 주세요: {bot.run_dir}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n중단했습니다.")
        sys.exit(130)


if __name__ == "__main__":
    main()
