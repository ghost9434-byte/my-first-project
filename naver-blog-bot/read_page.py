"""네이버 페이지 읽어 오기 (블로그 글, 네이버 지도·플레이스 등).

클로드는 네이버에 직접 들어갈 수 없으므로, 회장님 맥의 자동화용 크롬이 페이지를 열어
글자와 화면 사진을 파일로 저장한다. 그러면 클로드가 그 파일을 읽는다.

    .venv/bin/python read_page.py <주소> [<주소> ...]
→ reads/<날짜-시간>/ 에 page1.md (글자), page1.png (화면 전체) 를 저장한다.
"""
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from blog_bot import BASE, Bot, BotError

READS = BASE / "reads"


def page_text(page):
    """창과 안쪽 틀(iframe) 모두의 글자를 모은다. 네이버 블로그는 본문이 mainFrame 안에 있다."""
    parts = []
    for i, f in enumerate(page.frames):
        try:
            t = f.evaluate("() => document.body ? document.body.innerText : ''").strip()
        except Exception:
            continue
        if t and t not in parts:
            parts.append(f"<!-- frame {i}: {f.url[:100]} -->\n{t}")
    return "\n\n".join(parts)


def scroll_all(page, bot):
    """늦게 뜨는 내용까지 보이도록 끝까지 천천히 내린다."""
    for _ in range(30):
        try:
            at_end = page.evaluate(
                "() => { window.scrollBy(0, window.innerHeight * 0.9);"
                " return window.innerHeight + window.scrollY >= document.body.scrollHeight - 5; }")
        except Exception:
            break
        bot.wait(0.4)
        if at_end:
            break
    page.evaluate("() => window.scrollTo(0, 0)")
    bot.wait(0.5)


def read(urls, out_dir=None):
    out = Path(out_dir) if out_dir else READS / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    bot = Bot()
    results = []
    with sync_playwright() as pw:
        ctx, page = bot.open_browser(pw)
        try:
            for n, url in enumerate(urls, 1):
                page.goto(url, wait_until="domcontentloaded")
                bot.wait(3)
                scroll_all(page, bot)
                text = page_text(page)
                title = page.title()
                (out / f"page{n}.md").write_text(f"# {title}\n주소: {url}\n\n{text}\n", encoding="utf-8")
                try:
                    page.screenshot(path=str(out / f"page{n}.png"), full_page=True)
                except Exception:
                    page.screenshot(path=str(out / f"page{n}.png"))
                results.append((url, title, len(text)))
                print(f"✅ {n}. {title} (글자 {len(text)}자) → {out / f'page{n}.md'}", flush=True)
        finally:
            ctx.close()
    return out, results


def main():
    urls = [u for u in sys.argv[1:] if re.match(r"^https?://", u)]
    if not urls:
        print(__doc__)
        sys.exit(1)
    try:
        out, _ = read(urls)
    except BotError as e:
        print(f"❌ {e}")
        sys.exit(1)
    print(f"저장 폴더: {out}")


if __name__ == "__main__":
    main()
