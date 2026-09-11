import unittest

from bemyself.report import parse_report


FULL_REPORT = """\
### Phase 6: FINISH
**Status:** COMPLETE
**send_to payload:** `[DONE] [DEPLOY: yes] [COMMIT: 0123abc] [BRANCH: yesloop/demo] [MERGE: no] did the thing`
**Files in scope:** a.txt, b.txt
Tests run: python3 -m unittest test_ok -> exit 0
"""


class ParseReportTest(unittest.TestCase):
    def setUp(self):
        self.claims = parse_report(FULL_REPORT)

    def by_kind(self, kind):
        return [c for c in self.claims if c.kind == kind]

    def test_commit_claim(self):
        cs = self.by_kind("commit_exists")
        self.assertEqual(len(cs), 1)
        self.assertEqual(cs[0].fields["commit"], "0123abc")

    def test_branch_claim_pairs_with_commit(self):
        cs = self.by_kind("branch_pushed")
        self.assertEqual(len(cs), 1)
        self.assertEqual(cs[0].fields["branch"], "yesloop/demo")
        self.assertEqual(cs[0].fields["commit"], "0123abc")

    def test_tests_claim(self):
        cs = self.by_kind("tests_green")
        self.assertEqual(len(cs), 1)
        self.assertEqual(cs[0].fields["command"], "python3 -m unittest test_ok")
        self.assertEqual(cs[0].fields["claimed_exit"], 0)
        self.assertEqual(cs[0].fields["commit"], "0123abc")

    def test_diff_scope_claim(self):
        cs = self.by_kind("diff_scope")
        self.assertEqual(len(cs), 1)
        self.assertEqual(cs[0].fields["head"], "0123abc")
        self.assertEqual(list(cs[0].fields["planned"]), ["a.txt", "b.txt"])

    def test_merge_and_deploy_claims(self):
        self.assertEqual(len(self.by_kind("merge")), 1)
        self.assertEqual(len(self.by_kind("deploy")), 1)

    def test_line_numbers(self):
        self.assertEqual(self.by_kind("commit_exists")[0].line, 3)
        self.assertEqual(self.by_kind("diff_scope")[0].line, 4)
        self.assertEqual(self.by_kind("tests_green")[0].line, 5)

    def test_raw_line_is_preserved(self):
        c = self.by_kind("commit_exists")[0]
        self.assertIn("[COMMIT: 0123abc]", c.raw)

    def test_no_markers_yields_no_claims(self):
        self.assertEqual(parse_report("nothing to see here\n"), [])

    def test_unicode_arrow(self):
        claims = parse_report("Tests run: go test ./... \u2192 exit 1\n")
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].kind, "tests_green")
        self.assertEqual(claims[0].fields["command"], "go test ./...")
        self.assertEqual(claims[0].fields["claimed_exit"], 1)
        self.assertIsNone(claims[0].fields["commit"])

    def test_branch_without_commit(self):
        claims = parse_report("[BRANCH: yesloop/x]\n")
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].fields["branch"], "yesloop/x")
        self.assertIsNone(claims[0].fields["commit"])

    def test_network_exit_code_preserved(self):
        claims = parse_report("Tests run: bash run.sh -> exit 137\n")
        self.assertEqual(claims[0].fields["claimed_exit"], 137)


if __name__ == "__main__":
    unittest.main()
