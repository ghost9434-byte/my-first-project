import unittest
from ask import extract, render


class T(unittest.TestCase):
    def test_extract(self):
        c = [{"type": "server_tool_use"}, {"type": "web_search_tool_result"},
             {"type": "text", "text": "맑음 ", "citations": [{"url": "https://a.com", "title": "A"}]},
             {"type": "text", "text": "28도", "citations": [{"url": "https://a.com", "title": "A"}]}]
        t, s = extract(c)
        self.assertEqual(t, "맑음 28도")
        self.assertEqual(s, {"https://a.com": "A"})
        self.assertIn("- A: https://a.com", render(t, s))


if __name__ == "__main__":
    unittest.main()
