"""Tuned fork, fixes 5 and 6: BM25 ranking and mail-attachment links, on a small catalog (no model)."""
import sqlite3, tempfile, unittest
from pathlib import Path
from metadata.database import SCHEMA
from agent_api.metadata_retrieval import MetadataRetrieval


def catalog(path, files, terms, entities=(), links=()):
    con = sqlite3.connect(path); con.executescript(SCHEMA)
    for fid, name, summary in files:
        con.execute("INSERT INTO files(file_id,source_id,relative_path,file_name,file_type,summary) VALUES(?,?,?,?,?,?)",
                    (fid, "s", name, name, "txt", summary))
    for fid, term, freq in terms:
        con.execute("INSERT INTO file_terms VALUES(?,?,?,?,?)", (fid, term, "t", float(freq), freq))
    for fid, ent in entities:
        con.execute("INSERT INTO file_entities VALUES(?,?,?,?)", (fid, ent, "x", 1.0))
    for a, b in links:
        con.execute("INSERT INTO concept_relationships(source_concept,target_concept,relationship_type,source) "
                    "VALUES(?,?,'has_attachment','tuned-attachments')", ("file:" + a, "file:" + b))
    con.commit(); con.close()


class Fix5And6(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.db = Path(self.tmp.name) / "m.db"
    def tearDown(self):
        self.tmp.cleanup()

    def test_a_long_document_no_longer_wins_by_mentioning_everything(self):
        filler = [("deck", f"w{i}", 5) for i in range(200)]          # a long deck
        others = [(f"o{i}", "other", 1) for i in range(10)]           # documents without the words
        catalog(self.db, [("deck", "deck.pptx", ""), ("mail", "mail.txt", "")] + [(f"o{i}", f"o{i}.txt", "") for i in range(10)],
                filler + [("deck", "gold", 12), ("deck", "accumulator", 3),
                          ("mail", "gold", 2), ("mail", "accumulator", 2), ("mail", "launch", 1)] + others)
        ranked = [f["file_id"] for f in MetadataRetrieval(self.db).search_documents("gold accumulator launch")["files"]]
        self.assertEqual(ranked[0], "mail")

    def test_a_mail_is_found_through_its_attachment_and_lists_it(self):
        catalog(self.db, [("mail", "m.txt", "Subject: New launch"), ("att", "m__termsheet.pdf", ""), ("x", "x.txt", "")],
                [("att", "audusd", 3), ("att", "digital", 2), ("mail", "launch", 1), ("x", "other", 1)],
                links=[("mail", "att")])
        files = {f["file_id"]: f for f in MetadataRetrieval(self.db).search_documents("audusd digital")["files"]}
        self.assertIn("mail", files)
        self.assertAlmostEqual(files["mail"]["score"], round(0.9 * files["att"]["score"], 3), places=2)
        self.assertEqual([l["file_id"] for l in files["mail"]["linked_files"]], ["att"])
        self.assertEqual([l["file_id"] for l in files["att"]["linked_files"]], ["mail"])


if __name__ == "__main__":
    unittest.main()
