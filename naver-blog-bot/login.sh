#!/bin/bash
# 전용 크롬 창에서 네이버 로그인 (처음 한 번, 로그인이 풀렸을 때)
cd "$(dirname "$0")"
.venv/bin/python blog_bot.py login
