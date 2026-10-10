"""read_page.py / read_blog.py 시험 (가짜 RSS·글 화면)."""
import json, os, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_tests as t

HERE = Path(__file__).resolve().parent
BOT = HERE.parent

def main():
    srv, port = t.serve()
    tmp = tempfile.mkdtemp()
    env = dict(os.environ, NAVER_BOT_CHROME=t.CHROME, NAVER_BOT_HEADLESS="1", NAVER_BOT_PROFILE=tmp + "/p",
               NAVER_BOT_RSS_URL=f"http://127.0.0.1:{port}/rss.xml",
               NAVER_BOT_POST_URL=f"http://127.0.0.1:{port}/mpost/{{log}}.html")
    ok = True
    p = subprocess.run([sys.executable, str(BOT / "read_blog.py")], env=env, capture_output=True, text=True, timeout=200)
    print(p.stdout[-800:], p.stderr[-500:])
    data = json.loads((BOT / "blog_snapshot" / "posts.json").read_text())
    checks = [len(data) == 2, data[0]["images"] == 2, "덕대" in data[0]["text"], data[0]["likes"] == "11",
              data[1]["comments"] == "2", "#덕자회" in data[0]["tags"], data[0]["category"] == "목포 맛집·생활정보",
              (BOT / "blog_snapshot" / "224410000001.png").exists()]
    print("read_blog:", checks); ok &= all(checks)
    p = subprocess.run([sys.executable, str(BOT / "read_page.py"), f"http://127.0.0.1:{port}/index.html?newdom=1"],
                       env=env, capture_output=True, text=True, timeout=120)
    print(p.stdout[-400:], p.stderr[-300:])
    out = Path(p.stdout.strip().splitlines()[-1].split(": ", 1)[1])
    txt = (out / "page1.md").read_text()
    checks = ["사진" in txt and "발행" in txt, (out / "page1.png").exists()]  # mainFrame 안 글자까지 읽혔는지
    print("read_page:", checks); ok &= all(checks)
    srv.shutdown()
    print("✅ 읽기 시험 통과" if ok else "❌ 읽기 시험 실패")
    sys.exit(0 if ok else 1)

main()
