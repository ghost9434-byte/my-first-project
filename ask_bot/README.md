# 검색 비서 (Mac mini)
날씨·뉴스·항공 시간표·환율 등 무엇이든 웹 검색 후 출처와 함께 한국어로 답합니다.
- 터미널: `ANTHROPIC_API_KEY=... python3 ask.py "내일 다낭 날씨"`
- 상시 서버: `./install_mac.sh` (처음엔 .env 생성 후 종료 -> 키 입력 -> 다시 실행)
- 접속: `http://맥미니이름.local:8080/?t=ASK_TOKEN` (HOST=0.0.0.0 설정 시). 인터넷에 직접 노출하지 마세요.
- API 호출: `/api?q=질문&t=토큰` 은 JSON 반환
- 비용: 검색 1회당 API 요금이 붙습니다. ASK_MAX_SEARCHES 로 질문당 검색 횟수 제한(기본 6).
