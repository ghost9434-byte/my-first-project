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


class BotError(RuntimeError):
    pass


def posted_set():
    if POSTED_FILE.exists():
        return {l.strip() for l in POSTED_FILE.read_text(encoding="utf-8").splitlines() if l.strip()}
    return set()


def mark_posted(folder):
    with POSTED_FILE.open("a", encoding="utf-8") as f:
        f.write(folder + "\n")


def next_unposted():
    """아직 올리지 않은 글 가운데 가장 오래된 것을 고른다."""
    done = posted_set()
    folders = sorted(p.name for p in (BASE / "posts").iterdir() if (p / "post.json").exists())
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


def html_to_plain(h):
    t = re.sub(r"<br\s*/?>", "\n", h)
    t = re.sub(r"<hr\s*/?>", "\n", t)
    t = re.sub(r"</(p|h\d|li|tr|div|blockquote)>", "\n", t)
    t = re.sub(r"</t[dh]>", "\t", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = html_lib.unescape(t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


class Bot:
    def __init__(self, step=False):
        self.step = step
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
            inputs = fr.locator("input[type=file]")
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

    # ---------- 전체 흐름 ----------
    def post(self, folder):
        post_dir, data = load_post(folder)
        write_url = WRITE_URL_OVERRIDE or f"https://blog.naver.com/{data['blog_id']}?Redirect=Write&"
        report = []

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
                    else:
                        plain = block.get("plain") or html_to_plain(block["html"])
                        how = self.paste_html(fr, block["html"], plain)
                        self.cursor_to_end(fr)
                    report.append(f"{i}. {kind}: {how}")
                    self.shot(f"block{i:02d}-{kind}")
                    self.say(f"{i}번째 내용을 넣었습니다 ({how}).")

                img_need = sum(len(b["files"]) if "files" in b else 1 for b in data["blocks"] if b["type"] == "image")
                img_got = fr.locator(self.sel_comp(".se-image")).count()
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
            if saved:
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
            return {"saved": saved, "report": report, "img_need": img_need, "img_got": img_got}

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
    c = sub.add_parser("check", help="글 파일만 점검")
    c.add_argument("folder")
    args = ap.parse_args()

    bot = Bot(step=getattr(args, "step", False))
    try:
        if args.cmd == "login":
            bot.login()
        elif args.cmd == "check":
            post_dir, data = load_post(args.folder)
            n_img = sum(len(b["files"]) if "files" in b else 1 for b in data["blocks"] if b["type"] == "image")
            print(f"✅ 글 파일 정상: '{data['title']}' / 블록 {len(data['blocks'])}개 / 사진 {n_img}장")
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
