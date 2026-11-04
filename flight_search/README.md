# 다낭 항공편 조회 봇

## Mac mini 서버 설치
```bash
cd flight_search
./install_mac.sh          # 처음엔 .env 를 만들고 종료 -> 키 입력 후 다시 실행
./install_mac.sh 3600     # (선택) 1시간마다
```
- 결과: `results/latest.txt` (최근 30회 보관), 로그: `results/launchd.err`
- 수동 실행: `./run.sh`
- 해제: `launchctl unload ~/Library/LaunchAgents/com.flightsearch.bot.plist`
- 서버로 쓰면 시스템 설정 > 에너지에서 "정전 후 자동 시작", 잠자기 방지를 켜 두세요.
- `.env` 에 API 키가 있으니 git 에 올리지 마세요(.gitignore 처리됨).
