# -*- coding: utf-8 -*-
"""LICENSE section 6 source offer. Run: python -m unittest test_source_offer -v"""
import os
import unittest

import source_offer


class SourceOfferTest(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("SHOPVPN_SOURCE_URL", None)

    def test_default_is_fork_repo(self):
        os.environ.pop("SHOPVPN_SOURCE_URL", None)
        self.assertEqual(source_offer.source_url(), source_offer.FORK_REPO)
        self.assertEqual(source_offer.FORK_REPO, "https://github.com/amir12120/shopvpn-amir")

    def test_custom_url_and_bad_values(self):
        os.environ["SHOPVPN_SOURCE_URL"] = "https://github.com/me/fork"
        self.assertEqual(source_offer.source_url(), "https://github.com/me/fork")
        self.assertTrue(source_offer.license_url().endswith("/LICENSE"))
        os.environ["SHOPVPN_SOURCE_URL"] = "javascript:alert(1)"
        self.assertEqual(source_offer.source_url(), source_offer.FORK_REPO)

    def test_text_is_only_the_url(self):
        os.environ.pop("SHOPVPN_SOURCE_URL", None)
        for lang in ("fa", "en"):
            self.assertEqual(source_offer.build_text(lang), source_offer.FORK_REPO)
        os.environ["SHOPVPN_SOURCE_URL"] = 'https://x.io/a"b<c'
        # HTML escaping only; the answer stays a single address and no other text.
        self.assertEqual(source_offer.build_text("fa"), 'https://x.io/a"b&lt;c')
        self.assertNotIn("\n", source_offer.build_text("en"))


if __name__ == "__main__":
    unittest.main()
