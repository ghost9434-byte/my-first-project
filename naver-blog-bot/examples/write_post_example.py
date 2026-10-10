"""(로컬 클로드용) 새 디자인 틀로 post.json 을 쓰는 예시. 소도 글(2026-10-11)을 그대로 옮긴 것.

새 글을 쓸 때 이 파일을 복사해 내용만 바꾼 뒤 실행한다:
    .venv/bin/python examples/write_post_example.py posts/2026-10-12-글이름
사진은 먼저 make_post.py 로 posts/<폴더>/images/ 에 넣어 둔다.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from blog_style import gap, hashtags, head, office_footer, p, quote, summary_box, table, em  # noqa: E402

folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("posts/예시")
H = lambda s: {"type": "html", "html": s}
I = lambda f: {"type": "image", "file": "images/" + f}

blocks = [
    I("sodo_title.png"),
    H(gap()
      + p("안녕하세요, 목포 비파로 SH공유오피스입니다.")
      + p("오늘은 목포에 오시면", "꼭 한 번 드셔 보시길 권하는", "덕자 이야기입니다.")
      + p("덕자는 병어를 닮은 생선 '덕대'를", "전라도에서 부르는 이름이에요.")
      + p("제가 아끼는 단골집,", "부흥로의 소도를 소개해 드릴게요.")
      + gap()
      + summary_box("소도 한눈에 보기", [("위치", "목포시 부흥로 1"), ("전화", "061-281-0086"),
                                        ("영업", "밤 10시까지"), ("메뉴", "덕자회+찜 세트 (소·중·대)")])),
    H(head(1, "찰진 덕자회", "얇게 저며 가지런히 깔려 나와요")),
    I("hoe1.jpg"),
    H(p("쌈 채소에 한 점 올려 싸 먹으면", "담백하면서도 " + em("찰진 맛") + "이 그대로 느껴져요.")),
    H(head(2, "메뉴와 가격")
      + table(["메뉴", "가격"], [["덕자회+찜 소", "120,000원"], ["덕자회+찜 중", "140,000원"]])
      + head(3, "총평")
      + quote("목포에서 덕자를 제대로 맛보고 싶다면", "소도, 자신 있게 추천드립니다.")
      + office_footer()
      + hashtags(["목포맛집", "목포덕자", "덕자회", "덕자찜", "SH공유오피스"])),
]

post = {
    "blog_id": "shsuccesshub",
    "title": "목포 맛집 | 덕자회·덕자찜 현지인 단골집 '소도' 솔직 후기",
    "category": "목포 맛집·생활정보",
    "tags": [],          # 글 끝 해시태그 줄이 태그로 자동 등록되므로 보통 비워 둔다
    "publish": True,     # False 면 임시저장만
    "blocks": blocks,
}
folder.mkdir(parents=True, exist_ok=True)
(folder / "post.json").write_text(json.dumps(post, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"저장: {folder / 'post.json'}")
