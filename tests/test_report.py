"""Verify that embedded report data cannot terminate its JSON script element."""
import json
import re
import unittest

from runsignal.report import render


class ReportTests(unittest.TestCase):
    def test_untrusted_names_are_encoded_and_roundtrip_as_data(self):
        payload = {"name": '</script><script>alert("unsafe")</script>',
                   "path": "<img src=x onerror=alert(1)>", "label": "A&B > C\u2028test"}
        output = render(payload)
        match = re.search(r'<script type="application/json" id="data">(.*?)</script>', output, re.S)
        self.assertIsNotNone(match)
        self.assertEqual(json.loads(match[1]), payload)
        self.assertNotIn("<", match[1])
        self.assertNotIn(payload["path"], output)
        self.assertEqual(output.count("<script"), 2)


if __name__ == "__main__":
    unittest.main()
