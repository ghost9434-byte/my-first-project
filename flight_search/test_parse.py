import unittest
from flight_search import parse_serpapi, parse_amadeus


class ParseTest(unittest.TestCase):
    def test_serpapi(self):
        js = {"best_flights": [{"price": 450000, "flights": [{
            "airline": "Aero K", "flight_number": "RF 531",
            "departure_airport": {"id": "CJJ", "time": "2026-12-26 21:00"},
            "arrival_airport": {"id": "DAD", "time": "2026-12-26 23:55"}}]}]}
        f = parse_serpapi(js, "CJJ", "DAD")[0]
        self.assertEqual(f.duration_min, 295)  # 4h55m (시차 2시간 보정)
        self.assertEqual(f.stops, 0)

    def test_amadeus(self):
        js = {"data": [{"price": {"total": "430000"}, "itineraries": [{"segments": [{
            "carrierCode": "RF", "number": "532",
            "departure": {"iataCode": "DAD", "at": "2026-12-31T00:55:00"},
            "arrival": {"iataCode": "CJJ", "at": "2026-12-31T07:10:00"}}]}]}]}
        f = parse_amadeus(js, "DAD", "CJJ")[0]
        self.assertEqual(f.number, "RF532")
        self.assertEqual(f.duration_min, 255)  # 4h15m


if __name__ == "__main__":
    unittest.main()
