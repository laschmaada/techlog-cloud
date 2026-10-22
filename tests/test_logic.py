"""Unit tests for TechLog domain logic. Run: python3 -m unittest discover tests -v
No AWS, no network - logic.py is pure by design."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import logic  # noqa: E402


def valid_body(**overrides):
    body = {
        "tail": "ZS-SXA",
        "fleetType": "B737-800",
        "ataChapter": "32",
        "station": "FAOR",
        "description": "Nose gear steering judder during taxi-in at low speed",
        "category": "AOG",
    }
    body.update(overrides)
    return body


def make_defect(**overrides):
    return logic.build_defect(logic.validate_new_defect(valid_body(**overrides)),
                              raised_by="mech@demo.local")


class ValidationTests(unittest.TestCase):
    def test_valid_body_passes_and_normalises(self):
        clean = logic.validate_new_defect(valid_body(tail="zs-sxa", station="faor"))
        self.assertEqual(clean["tail"], "ZS-SXA")
        self.assertEqual(clean["station"], "FAOR")

    def test_bad_tail_rejected(self):
        with self.assertRaises(logic.ValidationError):
            logic.validate_new_defect(valid_body(tail="SAA123"))

    def test_bad_ata_rejected(self):
        with self.assertRaises(logic.ValidationError):
            logic.validate_new_defect(valid_body(ataChapter="ABC"))

    def test_short_description_rejected(self):
        with self.assertRaises(logic.ValidationError):
            logic.validate_new_defect(valid_body(description="broken"))

    def test_bad_category_rejected(self):
        with self.assertRaises(logic.ValidationError):
            logic.validate_new_defect(valid_body(category="URGENT"))

    def test_bad_fleet_rejected(self):
        with self.assertRaises(logic.ValidationError):
            logic.validate_new_defect(valid_body(fleetType="B777"))


class WorkflowTests(unittest.TestCase):
    def test_new_defect_starts_open(self):
        d = make_defect()
        self.assertEqual(d["status"], "OPEN")
        self.assertEqual(d["raisedBy"], "mech@demo.local")

    def test_defer_requires_mel_ref(self):
        d = make_defect()
        with self.assertRaises(logic.ValidationError):
            logic.apply_transition(d, "defer", {}, actor="cert@demo.local")

    def test_defer_sets_status_and_history(self):
        d = make_defect()
        updated, entry = logic.apply_transition(
            d, "defer", {"melRef": "MEL 32-10 CAT B"}, actor="cert@demo.local")
        self.assertEqual(updated["status"], "DEFERRED")
        self.assertEqual(updated["melRef"], "MEL 32-10 CAT B")
        self.assertEqual(entry["event"], "DEFERRED")
        self.assertEqual(d["status"], "OPEN")  # original not mutated

    def test_deferred_cannot_close_directly(self):
        d = make_defect()
        d, _ = logic.apply_transition(d, "defer", {"melRef": "MEL 32-10"}, actor="c@d")
        with self.assertRaises(logic.TransitionError):
            logic.apply_transition(d, "close", {}, actor="c@d")

    def test_full_lifecycle(self):
        d = make_defect()
        d, _ = logic.apply_transition(d, "rectify",
                                      {"rectificationNote": "Actuator changed, ops check sat"},
                                      actor="cert@demo.local")
        self.assertEqual(d["status"], "RECTIFIED")
        d, _ = logic.apply_transition(d, "close", {}, actor="cert@demo.local")
        self.assertEqual(d["status"], "CLOSED")
        self.assertEqual(d["closedBy"], "cert@demo.local")

    def test_reopen_clears_mel_and_requires_reason(self):
        d = make_defect()
        d, _ = logic.apply_transition(d, "defer", {"melRef": "MEL 1"}, actor="c@d")
        d, _ = logic.apply_transition(d, "rectify", {"rectificationNote": "fixed"}, actor="c@d")
        d, _ = logic.apply_transition(d, "close", {}, actor="c@d")
        with self.assertRaises(logic.ValidationError):
            logic.apply_transition(d, "reopen", {}, actor="c@d")
        d, entry = logic.apply_transition(d, "reopen", {"reason": "Fault recurred on next sector"},
                                          actor="c@d")
        self.assertEqual(d["status"], "OPEN")
        self.assertIsNone(d["melRef"])
        self.assertEqual(entry["event"], "REOPENED")

    def test_unknown_action_rejected(self):
        with self.assertRaises(logic.ValidationError):
            logic.apply_transition(make_defect(), "delete", {}, actor="c@d")


class DynamoShapeTests(unittest.TestCase):
    def test_meta_item_keys(self):
        item = logic.to_dynamo_meta(make_defect())
        self.assertTrue(item["PK"].startswith("DEFECT#"))
        self.assertEqual(item["SK"], "META")
        self.assertEqual(item["GSI1PK"], "STATUS#OPEN")
        self.assertNotIn("melRef", item)  # None values stripped for boto3

    def test_history_item_keys(self):
        d = make_defect()
        item = logic.to_dynamo_history(d["defectId"], logic.created_history(d))
        self.assertEqual(item["PK"], f"DEFECT#{d['defectId']}")
        self.assertTrue(item["SK"].startswith("HISTORY#"))
        self.assertEqual(item["event"], "CREATED")


if __name__ == "__main__":
    unittest.main()
