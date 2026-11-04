#!/usr/bin/env python3
"""청주/김해 ↔ 다낭 실시간 항공편 조회 봇 (표준 라이브러리만 사용).

두 가지 조회 소스를 지원합니다.
  serpapi  : Google Flights 결과를 SerpApi로 조회 (저비용항공사 포함, 권장)
             환경변수 SERPAPI_KEY 필요  -> https://serpapi.com (무료 월 100회)
  amadeus  : Amadeus Self-Service API (일부 저비용항공사는 누락될 수 있음)
             환경변수 AMADEUS_ID, AMADEUS_SECRET 필요 -> https://developers.amadeus.com

사용 예:
  export SERPAPI_KEY=...
  python3 flight_search.py --out 2026-12-26 2026-12-27 --back 2026-12-30
  python3 flight_search.py --out 2026-12-26 --back 2026-12-30 --origins CJJ --provider amadeus
  python3 flight_search.py --demo        # API 키 없이 출력 형식만 확인

모든 시각은 각 공항의 '현지 시각'입니다 (한국 UTC+9, 다낭 UTC+7, 차이 2시간).
"""
import argparse
import base64
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime

AIRPORTS = {"CJJ": "청주", "PUS": "김해(부산)", "DAD": "다낭"}
TZ_OFFSET = {"CJJ": 9, "PUS": 9, "DAD": 7}  # UTC 오프셋(시간)
FMT = "%Y-%m-%d %H:%M"


class Flight:
    def __init__(self, airline, number, origin, dest, dep, arr, price=None, stops=0):
        self.airline, self.number = airline, number
        self.origin, self.dest = origin, dest
        self.dep, self.arr = dep, arr  # 현지 시각 naive datetime
        self.price, self.stops = price, stops

    @property
    def duration_min(self):
        # 현지 시각 두 개를 UTC로 환산해서 비행시간 계산
        d = (self.arr - self.dep).total_seconds() / 60
        d -= (TZ_OFFSET[self.dest] - TZ_OFFSET[self.origin]) * 60
        return int(d)


def http_json(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


# ---------------------------------------------------------------- SerpApi
def parse_serpapi(js, origin, dest):
    out = []
    for grp in js.get("best_flights", []) + js.get("other_flights", []):
        legs = grp.get("flights", [])
        if not legs:
            continue
        first, last = legs[0], legs[-1]
        out.append(Flight(
            first.get("airline", "?"), first.get("flight_number", "?"),
            first["departure_airport"]["id"], last["arrival_airport"]["id"],
            datetime.strptime(first["departure_airport"]["time"], FMT),
            datetime.strptime(last["arrival_airport"]["time"], FMT),
            grp.get("price"), len(legs) - 1))
    return [f for f in out if f.origin == origin and f.dest == dest]


def search_serpapi(origin, dest, date):
    key = os.environ.get("SERPAPI_KEY")
    if not key:
        sys.exit("SERPAPI_KEY 환경변수가 필요합니다.")
    q = urllib.parse.urlencode({
        "engine": "google_flights", "departure_id": origin, "arrival_id": dest,
        "outbound_date": date, "type": 2, "currency": "KRW", "hl": "ko", "api_key": key})
    return parse_serpapi(http_json("https://serpapi.com/search.json?" + q), origin, dest)


# ---------------------------------------------------------------- Amadeus
def parse_amadeus(js, origin, dest):
    out = []
    for offer in js.get("data", []):
        segs = offer["itineraries"][0]["segments"]
        f, l = segs[0], segs[-1]
        out.append(Flight(
            f["carrierCode"], f["carrierCode"] + f["number"],
            f["departure"]["iataCode"], l["arrival"]["iataCode"],
            datetime.fromisoformat(f["departure"]["at"]),
            datetime.fromisoformat(l["arrival"]["at"]),
            float(offer["price"]["total"]), len(segs) - 1))
    return [x for x in out if x.origin == origin and x.dest == dest]


_amadeus_token = {}


def search_amadeus(origin, dest, date):
    cid, sec = os.environ.get("AMADEUS_ID"), os.environ.get("AMADEUS_SECRET")
    if not (cid and sec):
        sys.exit("AMADEUS_ID / AMADEUS_SECRET 환경변수가 필요합니다.")
    if "t" not in _amadeus_token:
        body = urllib.parse.urlencode({"grant_type": "client_credentials",
                                       "client_id": cid, "client_secret": sec}).encode()
        _amadeus_token["t"] = http_json(
            "https://api.amadeus.com/v1/security/oauth2/token", body,
            {"Content-Type": "application/x-www-form-urlencoded"})["access_token"]
    q = urllib.parse.urlencode({
        "originLocationCode": origin, "destinationLocationCode": dest,
        "departureDate": date, "adults": 1, "currencyCode": "KRW", "max": 30})
    js = http_json("https://api.amadeus.com/v2/shopping/flight-offers?" + q,
                   headers={"Authorization": "Bearer " + _amadeus_token["t"]})
    return parse_amadeus(js, origin, dest)


# ---------------------------------------------------------------- 출력
def fmt_dur(m):
    return f"{m // 60}시간 {m % 60:02d}분"


def show(flights, title):
    print(f"\n■ {title}")
    if not flights:
        print("  조회된 항공편 없음 (해당 날짜 미오픈이거나 결항일 수 있음)")
        return
    print(f"  {'항공사':<10}{'편명':<9}{'출발(현지)':<18}{'도착(현지)':<18}{'비행시간':<11}{'경유':<4}가격")
    for f in sorted(flights, key=lambda x: x.dep):
        price = f"{int(f.price):,}원" if f.price else "-"
        print(f"  {f.airline:<10}{f.number:<9}{f.dep.strftime('%m/%d %H:%M'):<18}"
              f"{f.arr.strftime('%m/%d %H:%M'):<18}{fmt_dur(f.duration_min):<11}{f.stops:<4}{price}")


def show_stay(outs, backs, out_date, back_date):
    """다낭 도착(현지) → 귀국편 출발(현지)까지 체류 시간 계산."""
    print(f"\n■ 다낭 체류 시간 ({out_date} 가는 편 도착 → {back_date} 오는 편 출발, 모두 다낭 현지 시각)")
    for o in sorted(outs, key=lambda x: x.arr):
        for b in sorted(backs, key=lambda x: x.dep):
            h = (b.dep - o.arr).total_seconds() / 3600
            print(f"  {o.number} {o.arr.strftime('%m/%d %H:%M')} 도착  →  "
                  f"{b.number} {b.dep.strftime('%m/%d %H:%M')} 출발   체류 {h:.1f}시간 ({h / 24:.1f}일)")


def demo_data():
    d = lambda s: datetime.strptime(s, FMT)
    outs = [Flight("에어로케이", "RF531", "CJJ", "DAD", d("2026-12-26 21:00"), d("2026-12-26 23:55"), 450000)]
    backs = [Flight("에어로케이", "RF532", "DAD", "CJJ", d("2026-12-31 00:55"), d("2026-12-31 07:10"), 430000)]
    return outs, backs


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", nargs="+", help="가는 날짜들 YYYY-MM-DD")
    p.add_argument("--back", nargs="+", help="오는 날짜들 YYYY-MM-DD")
    p.add_argument("--origins", nargs="+", default=["CJJ", "PUS"], choices=["CJJ", "PUS"])
    p.add_argument("--provider", default="serpapi", choices=["serpapi", "amadeus"])
    p.add_argument("--demo", action="store_true", help="API 없이 샘플 출력")
    a = p.parse_args()

    if a.demo:
        outs, backs = demo_data()
        show(outs, "[데모] 청주 → 다낭 12/26")
        show(backs, "[데모] 다낭 → 청주 12/31")
        show_stay(outs, backs, "12/26", "12/31")
        return
    if not (a.out and a.back):
        p.error("--out 과 --back 을 지정하세요 (또는 --demo)")

    search = search_serpapi if a.provider == "serpapi" else search_amadeus
    for org in a.origins:
        name = AIRPORTS[org]
        outs_by, backs_by = {}, {}
        for date in a.out:
            outs_by[date] = search(org, "DAD", date)
            show(outs_by[date], f"{name} → 다낭  {date}")
        for date in a.back:
            backs_by[date] = search("DAD", org, date)
            show(backs_by[date], f"다낭 → {name}  {date}")
        for od in a.out:
            for bd in a.back:
                show_stay(outs_by[od], backs_by[bd], od, bd)


if __name__ == "__main__":
    main()
