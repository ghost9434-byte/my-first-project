"""시험용 가짜 네이버 글쓰기 화면으로 blog_bot.py 를 여러 경우에 돌려 본다.

실행: python3 tests/run_tests.py   (리눅스 시험 서버 / 맥 모두 가능)
"""
import functools
import http.server
import json
import os
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
BOT = HERE.parent / "blog_bot.py"
DEFAULT_CHROME = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" if sys.platform == "darwin"
                  else "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
CHROME = os.environ.get("NAVER_BOT_CHROME", DEFAULT_CHROME)


def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    handler = functools.partial(Quiet, directory=str(HERE / "mock"))
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def run(port, folder, query, timeout=180):
    tmp = Path(tempfile.mkdtemp())
    env = dict(os.environ,
               NAVER_BOT_WRITE_URL=f"http://127.0.0.1:{port}/index.html?{query}",
               NAVER_BOT_CHROME=CHROME, NAVER_BOT_HEADLESS="1", NAVER_BOT_NONINTERACTIVE="1",
               NAVER_BOT_PROFILE=str(tmp / "profile"), NAVER_BOT_DUMP=str(tmp / "state.json"))
    try:
        p = subprocess.run([sys.executable, str(BOT), "post", folder], env=env,
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        p = subprocess.CompletedProcess(e.cmd, 124, (e.stdout or b"").decode(errors="ignore") if isinstance(e.stdout, bytes) else (e.stdout or ""), "시간 초과")
    state = json.loads((tmp / "state.json").read_text()) if (tmp / "state.json").exists() else None
    if state is not None and (tmp / "state.json.publish.json").exists():
        state["publish"] = json.loads((tmp / "state.json.publish.json").read_text())
    shutil.rmtree(tmp, ignore_errors=True)
    return p, state


def kinds(state):
    out = []
    for c in state["comps"]:
        for k in ("se-image", "se-video", "se-horizontalLine", "se-table", "se-quotation", "se-text"):
            if k in c["cls"]:
                out.append(k.replace("se-", ""))
                break
    return out


def check_hongildong(state, formatted=True):
    errs = []
    full = "\n".join(c["text"] for c in state["comps"])
    if state["title"].strip() != "목포 덕자회 맛집, 홍길동선어회 (덕자회·덕자찜)":
        errs.append(f"제목 다름: {state['title']!r}")
    k = kinds(state)
    if k.count("image") != 2:
        errs.append(f"사진 수 {k.count('image')} (2여야 함)")
    if not k or k[0] != "image":
        errs.append("첫 내용이 대표 사진이 아님")
    for phrase in ["들어보셨나요", "왜 덕자는 목포에서", "추천하는 이유", "비파로43번길 42-1", "2인 이상", "010-6399-1056"]:
        if phrase not in full:
            errs.append(f"본문 누락: {phrase}")
    # 순서: 추천 이유 → 가게정보 사진 → 가게 정보 표
    texts = [c["text"] for c in state["comps"]]
    try:
        i_reason = next(i for i, t in enumerate(texts) if "덕자회와 칼칼한" in t or "덕자회" in t and "칼칼한" in t)
        i_img2 = [i for i, kk in enumerate(k) if kk == "image"][1]
        i_info = next(i for i, t in enumerate(texts) if "가게 정보" in t)
        if not (i_reason < i_img2 < i_info):
            errs.append(f"순서 이상: 추천이유 {i_reason}, 사진 {i_img2}, 가게정보 {i_info}")
    except (StopIteration, IndexError):
        errs.append("순서 확인 실패")
    if formatted:
        if "horizontalLine" not in k: errs.append("구분선 없음")
        if "table" not in k: errs.append("표 없음")
        if "quotation" not in k: errs.append("인용구 없음")
    if not state["saved"]:
        errs.append("저장 안 됨")
    return errs


def main():
    srv, port = serve()
    cases = [
        ("기본 (mainFrame 안)", "../tests/fixtures/basic", "", True),
        ("편집기가 바로 뜨는 경우", "../tests/fixtures/basic", "direct=1", True),
        ("작성중 글 팝업 + 도움말", "../tests/fixtures/basic", "popup=1&help=1", True),
        ("팝업이 늦게 뜨는 경우", "../tests/fixtures/basic", "popup=1&latepopup=1", True),
        ("가짜 붙여넣기 거부 → 대체 경로", "../tests/fixtures/basic", "trustedonly=1", False),
        ("사진 버튼이 파일창을 안 띄움", "../tests/fixtures/basic", "nochooser=1", True),
        ("사진 업로드가 느림", "../tests/fixtures/basic", "slowupload=1", True),
        ("저장 버튼 없음 → 단축키", "../tests/fixtures/basic", "nosavebtn=1", True),
        ("로그인 먼저 필요", "../tests/fixtures/basic", "login=1", True),
        ("로그인 화면이 안쪽 틀에 뜸", "../tests/fixtures/basic", "login=iframe", True),
        ("붙여넣기 뒤 빈 줄 생김", "../tests/fixtures/basic", "pastetrailtext=1", True),
        ("실제 편집기 구조(.se-components-wrap)", "../tests/fixtures/basic", "newdom=1", True),
        ("새 구조 + 팝업 + 로그인", "../tests/fixtures/basic", "newdom=1&popup=1&help=1&login=1", True),
        ("사진 뒤 선택 막 (Esc로 풀림)", "../tests/fixtures/basic", "newdom=1&overlay=1", True),
        ("사진 뒤 선택 막 (안 풀림 → 직접)", "../tests/fixtures/basic", "newdom=1&overlay=2", True),
        ("모든 경우 한꺼번에", "../tests/fixtures/basic", "newdom=1&overlay=1&popup=1&help=1&latepopup=1&nochooser=1&slowupload=1&pastetrailtext=1", True),
    ]
    results = []
    for name, folder, q, formatted in cases:
        p, state = run(port, folder, q)
        errs = []
        if p.returncode != 0:
            errs.append(f"종료코드 {p.returncode}: {(p.stdout + p.stderr)[-600:]}")
        elif state is None:
            errs.append("상태 기록 없음")
        else:
            errs = check_hongildong(state, formatted)
        results.append((name, errs))
        print(("✅ " if not errs else "❌ ") + name + ("" if not errs else "\n     - " + "\n     - ".join(errs)), flush=True)

    # 여러 장 사진
    p, state = run(port, "../tests/fixtures/multi", "")
    errs = []
    if p.returncode != 0 or not state:
        errs.append(f"실패: {(p.stdout + p.stderr)[-600:]}")
    else:
        k = kinds(state)
        texts = [c["text"] for c in state["comps"]]
        if k.count("image") != 2: errs.append(f"사진 수 {k.count('image')}")
        if "첫 문단" not in texts[0]: errs.append("첫 문단 위치")
        if "끝 문단" not in texts[-1] and "끝 문단" not in "".join(texts[-2:]): errs.append("끝 문단 위치")
    results.append(("사진 여러 장 한 번에", errs))
    print(("✅ " if not errs else "❌ ") + "사진 여러 장 한 번에" + ("" if not errs else " " + str(errs)), flush=True)

    # 실제로 올릴 글 전체 (사진 10장)
    for post in sorted((HERE.parent / "posts").iterdir()):
        if not (post / "post.json").exists():
            continue
        data = json.loads((post / "post.json").read_text(encoding="utf-8"))
        need = sum(len(b["files"]) if "files" in b else 1 for b in data["blocks"] if b["type"] == "image")
        p, state = run(port, post.name, "newdom=1&overlay=1&popup=1&help=1&slowupload=1", timeout=400)
        errs = []
        if p.returncode != 0 or not state:
            errs.append(f"실패: {(p.stdout + p.stderr)[-600:]}")
        else:
            k = kinds(state)
            if k.count("image") != need: errs.append(f"사진 {k.count('image')}/{need}")
            if state["title"].strip() != data["title"].strip(): errs.append("제목 다름")
            if not state["saved"]: errs.append("저장 안 됨")
            got_imgs = [i for i, kk in enumerate(k) if kk == "image"]
            if got_imgs != sorted(got_imgs): errs.append("사진 순서")
        name = f"실제 글: {post.name}"
        results.append((name, errs))
        print(("✅ " if not errs else "❌ ") + name + ("" if not errs else " " + str(errs)), flush=True)

    # 발행 (카테고리·태그)
    for name, q, expect_pub in [("발행: 카테고리·태그", "newdom=1&overlay=1", True),
                                ("발행: 카테고리 띄어쓰기 다름", "newdom=1&pubtext=1", True),
                                ("발행: 카테고리 없음 → 발행 안 하고 임시저장만", "newdom=1&nocat=1", False)]:
        p, state = run(port, "../tests/fixtures/pub", q)
        errs = []
        out = p.stdout
        if p.returncode != 0 or not state:
            errs.append(f"실패: {(out + p.stderr)[-500:]}")
        else:
            errs += check_hongildong(state)
            if expect_pub:
                pub = state.get("publish") or {}
                if "생활정보" not in pub.get("category", ""): errs.append(f"카테고리 {pub.get('category')!r}")
                if pub.get("tags") != ["#목포맛집", "#덕자회"]: errs.append(f"태그 {pub.get('tags')}")
                if "카테고리로 발행했습니다" not in out: errs.append("발행 완료 문구 없음: " + out[-300:])
            else:
                if "발행했습니다" in out: errs.append("발행하면 안 되는데 발행함")
                if "발행은 하지 못했습니다" not in out: errs.append("안내 문구 없음")
        results.append((name, errs))
        print(("✅ " if not errs else "❌ ") + name + ("" if not errs else " " + str(errs)), flush=True)

    # 동영상
    for name, q, ok_video in [("동영상: 올리기 창 → 제목 → 완료 → 발행", "newdom=1&overlay=1", True),
                              ("동영상: 버튼이 바로 파일 창", "newdom=1&videodirect=1", True),
                              ("동영상: 올리는 데 오래 걸림", "newdom=1&videoslow=1&popup=1", True),
                              ("동영상: 끝까지 안 올라감 → 글은 저장, 발행 안 함", "newdom=1&videostuck=1", False)]:
        os.environ["NAVER_BOT_VIDEO_TIMEOUT"] = "12"
        p, state = run(port, "../tests/fixtures/video", q)
        os.environ.pop("NAVER_BOT_VIDEO_TIMEOUT")
        errs = []
        out = p.stdout
        if p.returncode != 0 or not state:
            errs.append(f"실패: {(out + p.stderr)[-600:]}")
        else:
            k = kinds(state)
            texts = [c["text"] for c in state["comps"]]
            if not state["saved"]: errs.append("저장 안 됨")
            if k.count("image") != 1: errs.append(f"사진 수 {k.count('image')}")
            if ok_video:
                if k.count("video") != 1: errs.append(f"동영상 수 {k.count('video')}: {k}")
                else:
                    iv, ii = k.index("video"), k.index("image")
                    i_after = next((i for i, t in enumerate(texts) if "영상 뒤 문단" in t), -1)
                    if not (ii < iv < i_after): errs.append(f"순서 이상: 사진 {ii}, 동영상 {iv}, 뒤 문단 {i_after} / {k}")
                    if "videodirect" not in q and "소도 덕자찜 끓는 모습" not in texts[iv]:
                        errs.append(f"동영상 제목 다름: {texts[iv]!r}")
                if "카테고리로 발행했습니다" not in out: errs.append("발행 안 됨: " + out[-300:])
            else:
                if k.count("video") != 0: errs.append("동영상이 들어가면 안 됨")
                if "영상 뒤 문단" not in "".join(texts): errs.append("동영상 뒤 글이 빠짐")
                if "발행했습니다" in out: errs.append("발행하면 안 되는데 발행함")
                if "동영상을 넣지 못했습니다" not in out: errs.append("안내 문구 없음")
        results.append((name, errs))
        print(("✅ " if not errs else "❌ ") + name + ("" if not errs else " " + str(errs)), flush=True)

    # 깨진 글 파일은 브라우저 열기 전에 막혀야 함
    p = subprocess.run([sys.executable, str(BOT), "check", "../tests/fixtures/broken"], capture_output=True, text=True)
    ok = p.returncode == 1 and "사진 파일이 없습니다" in p.stdout
    results.append(("깨진 글 파일 미리 잡기", [] if ok else [p.stdout]))
    print(("✅ " if ok else "❌ ") + "깨진 글 파일 미리 잡기", flush=True)

    srv.shutdown()
    failed = [n for n, e in results if e]
    print(f"\n{len(results) - len(failed)}/{len(results)} 통과")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
