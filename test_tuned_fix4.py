"""Tuned fork, fix 4: a long document is read where it answers the question (no model)."""
import tempfile, unittest
from pathlib import Path
from agent_api.core import Config, Tools


class Fix4(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tools = Tools(Config(metadata_db=str(Path(self.tmp.name) / "none.db")))
    def tearDown(self):
        self.tmp.cleanup()

    def test_the_slide_that_answers_is_returned_in_document_order(self):
        every = [(i, f"Slide {i}: market colour and general commentary " * 20) for i in range(1, 6)]
        every.append((6, "24M USDJPY bullish digital structured deposit | Digital level | 183.50 (digital level)"))
        every += [(i, "Appendix and disclosures " * 30) for i in range(7, 10)]
        units, sel = self.tools._focused_units(every, "slide", "What is the digital level on the two-year USDJPY "
                                                           "bullish digital deposit?", 1500)
        self.assertIn({"slide": 6}, [u["locator"] for u in units])
        self.assertIn("183.50", "".join(u["text"] for u in units))
        self.assertEqual([u["locator"]["slide"] for u in units], sorted(u["locator"]["slide"] for u in units))
        self.assertEqual(sel["mode"], "focused")

    def test_nothing_matching_falls_back_to_the_title_unit_only(self):
        every = [(1, "Title page"), (2, "unrelated words " * 50)]
        units, _ = self.tools._focused_units(every, "page", "copper accumulator knock-out", 400)
        self.assertEqual([u["locator"] for u in units], [{"page": 1}])


if __name__ == "__main__":
    unittest.main()
