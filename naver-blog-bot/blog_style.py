"""(클로드용) 블로그 글 디자인 틀.

네이버 편집기에 붙여 넣을 때 확인된 점 (2026-10-10 소도 글):
- 가운데 정렬, 구분선(<hr>), 표, 인용구(<blockquote>)는 그대로 살아남는다.
- 글 끝의 #해시태그 줄은 네이버가 태그로 자동 등록한다.
- 색·크기·글꼴을 적지 않은 문단은 바로 앞 문단의 서식(파란색, 작은 회색 글씨 등)을
  그대로 이어받는다. → 모든 글자에 색·크기·글꼴을 빠짐없이 적는다.
"""

BLUE = "#2f5dd4"
TEXT = "#333333"
GRAY = "#8a8a8a"
FONT = "'나눔고딕', NanumGothic, sans-serif"


def span(text, size=16, color=TEXT, bold=False):
    inner = f"<b>{text}</b>" if bold else text
    return f'<span style="font-family:{FONT};font-size:{size}px;color:{color};">{inner}</span>'


def p(*lines, size=16, color=TEXT, bold=False):
    """가운데 정렬 문단. 줄마다 서식을 따로 붙여 앞 문단 서식이 새지 않게 한다."""
    body = "<br>".join(span(line, size, color, bold) for line in lines)
    return f'<p style="text-align:center;">{body}</p>'


def em(text):
    """문장 안에서 강조할 말 (굵게 + 파랑). p() 안에 넣어 쓴다."""
    return f'</span><span style="font-family:{FONT};font-size:16px;color:{BLUE};"><b>{text}</b></span><span style="font-family:{FONT};font-size:16px;color:{TEXT};">'


def gap():
    return f'<p style="text-align:center;">{span("&nbsp;")}</p>'


def head(n, title, sub=None):
    out = gap() + "<hr>" + p(f"{n:02d}", size=13, color=GRAY) + p(title, size=24, color=BLUE, bold=True)
    if sub:
        out += p(sub, size=15, color=GRAY)
    return out + gap()


def summary_box(title, rows):
    """맨 위 '한눈에 보기' 상자. rows = [(항목, 내용), ...]"""
    lines = "<br>".join(span(f"{k} : {v}") for k, v in rows)
    return (f'<blockquote><p style="text-align:center;">{span(title, bold=True)}</p>'
            f'<p style="text-align:center;">{lines}</p></blockquote>')


def quote(*lines):
    return f'<blockquote><p style="text-align:center;">{"<br>".join(span(l) for l in lines)}</p></blockquote>'


def table(header, rows):
    cell = lambda t, tag: f'<{tag} style="text-align:center;">{span(t, 15)}</{tag}>'
    html = '<table border="1"><tr>' + "".join(cell(h, "th") for h in header) + "</tr>"
    for r in rows:
        html += "<tr>" + "".join(cell(c, "td") for c in r) + "</tr>"
    return html + "</table>"


def office_footer():
    return (gap() + "<hr>"
            + p("목포로 출장이나 미팅차 오셨다면,", "식사 후 잠깐 일하실 공간도 필요하시죠?")
            + p("SH 공유오피스 SUCCESS HUB", bold=True)
            + p("전남광주통합특별시 목포시 비파로 123, 2층", "24시간 연중무휴 · 010-6399-1056"))


def hashtags(tags):
    """글 끝 해시태그 줄. 네이버가 이 줄을 태그로 자동 등록한다."""
    return gap() + p(" ".join("#" + t.lstrip("#") for t in tags), size=13, color=GRAY)


# 맥북 클로드가 바꾼 디자인은 blog_style_local.py (맥북에만 있고 GitHub로 오가지 않음)에 둔다.
# 같은 이름의 함수가 있으면 그쪽이 이 파일의 것을 대신한다. 그래서 이 파일은 클라우드 쪽만 고친다.
try:
    from blog_style_local import *  # noqa: E402,F401,F403
except ImportError:
    pass
