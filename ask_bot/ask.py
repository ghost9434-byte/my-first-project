#!/usr/bin/env python3
"""Mac mini 용 인터넷 검색 비서: 질문 -> Claude(웹검색 도구) -> 출처 포함 답변. 표준 라이브러리만 사용.

  export ANTHROPIC_API_KEY=sk-ant-...
  python3 ask.py "내일 다낭 날씨 알려줘"
  python3 ask.py                      # 대화형 모드
  ASK_TOKEN=비밀번호 python3 ask.py --serve --host 0.0.0.0 --port 8080   # 폰/다른 PC에서 접속

날씨, 뉴스, 항공 시간표, 환율 등 웹에서 찾을 수 있는 건 무엇이든 질문 가능합니다.
"""
import argparse
import hmac
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

API = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("ASK_MODEL", "claude-sonnet-5-5")
MAX_SEARCHES = int(os.environ.get("ASK_MAX_SEARCHES", "6"))


def system_prompt():
    return ("당신은 웹 검색 도구를 가진 비서입니다. 현재 시각: "
            + datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z") + ". "
            "날씨·시간표·가격·뉴스처럼 변하는 정보는 반드시 검색해서 확인하고, 한국어로 간결히 답하세요. "
            "찾지 못했거나 출처가 오래됐으면 추측하지 말고 그렇다고 말하세요. 시각은 현지 시각인지 명시하세요.")


def call_api(messages):
    body = json.dumps({
        "model": MODEL, "max_tokens": 2048, "system": system_prompt(), "messages": messages,
        "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": MAX_SEARCHES}],
    }).encode()
    req = urllib.request.Request(API, body, {
        "x-api-key": os.environ.get("ANTHROPIC_API_KEY", ""),
        "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"API 오류 {e.code}: {e.read().decode(errors='replace')[:500]}")


def extract(content):
    """응답 블록에서 본문 텍스트와 출처 URL 목록을 뽑는다."""
    text, sources = [], {}
    for b in content:
        if b.get("type") == "text":
            text.append(b.get("text", ""))
            for c in b.get("citations") or []:
                if c.get("url"):
                    sources[c["url"]] = c.get("title") or c["url"]
    return "".join(text).strip(), sources


def ask(question, history=None):
    """질문 하나에 답한다. history 를 넘기면 대화 맥락이 이어진다."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY 환경변수가 필요합니다.")
    messages = list(history or []) + [{"role": "user", "content": question}]
    texts, sources = [], {}
    for _ in range(5):  # 서버측 검색이 길어지면 pause_turn 으로 끊겨 이어서 호출
        resp = call_api(messages)
        t, s = extract(resp.get("content", []))
        texts.append(t)
        sources.update(s)
        if resp.get("stop_reason") != "pause_turn":
            break
        messages.append({"role": "assistant", "content": resp["content"]})
    answer = "\n".join(x for x in texts if x)
    if history is not None:
        history += [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]
    return answer, sources


def render(answer, sources):
    out = answer or "(답변 없음)"
    if sources:
        out += "\n\n출처:\n" + "\n".join(f"- {t}: {u}" for u, t in sources.items())
    return out


HTML = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>검색 비서</title><style>body{font:16px system-ui;max-width:640px;margin:16px auto;padding:0 16px}
input,button{font:inherit;padding:8px}input[name=q]{width:100%%;box-sizing:border-box}pre{white-space:pre-wrap}</style>
<form><input name=q placeholder="무엇이든 물어보세요 (예: 내일 다낭 날씨)" value="%s" autofocus>
<input type=hidden name=t value="%s"><button>검색</button></form><pre>%s</pre>"""


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")


class Handler(BaseHTTPRequestHandler):
    token = ""

    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        tok = (qs.get("t") or [""])[0]
        if self.token and not hmac.compare_digest(tok, self.token):
            return self.reply(403, "text/plain; charset=utf-8", "접근 토큰이 필요합니다: /?t=<ASK_TOKEN>")
        q = (qs.get("q") or [""])[0].strip()
        result = ""
        if q:
            try:
                result = render(*ask(q))
            except Exception as e:  # noqa
                result = f"오류: {e}"
        if u.path == "/api":
            return self.reply(200, "application/json; charset=utf-8",
                              json.dumps({"answer": result}, ensure_ascii=False))
        self.reply(200, "text/html; charset=utf-8", HTML % (esc(q), esc(tok), esc(result)))

    def reply(self, code, ctype, body):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("question", nargs="*")
    p.add_argument("--serve", action="store_true", help="웹 서버 모드")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8080)
    a = p.parse_args()

    if a.serve:
        Handler.token = os.environ.get("ASK_TOKEN", "")
        if a.host != "127.0.0.1" and not Handler.token:
            sys.exit("외부 접속(--host 0.0.0.0)에는 ASK_TOKEN 환경변수(접근 비밀번호)가 필요합니다.")
        print(f"http://{a.host}:{a.port}/  (토큰: ?t=...)")
        ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()
    elif a.question:
        print(render(*ask(" ".join(a.question))))
    else:
        hist = []
        print("질문을 입력하세요 (종료: Ctrl-D)")
        for line in sys.stdin:
            if line.strip():
                print(render(*ask(line.strip(), hist)), "\n")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        sys.exit(str(e))
