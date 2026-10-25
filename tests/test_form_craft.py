# SPDX-License-Identifier: GPL-3.0-or-later
"""form_craft - the primitive-choice layer that stops sphere defaulting.

The regression this guards: a model asked for a robotic arm or a horse returns a
pile of scaled UV spheres. Every assertion below is written against that failure,
not against the module's shape.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "runtime"))
import form_craft as fc  # noqa: E402


class FormVocabulary(unittest.TestCase):
    def test_every_form_is_fully_described(self):
        for fid, (label, why, build) in fc.FORMS.items():
            with self.subTest(form=fid):
                self.assertTrue(label, f"{fid} needs a label")
                self.assertTrue(why, f"{fid} needs a 'when it is right'")
                self.assertTrue(build, f"{fid} needs concrete build advice")

    def test_sphere_exists_but_is_documented_as_the_exception(self):
        self.assertIn("sphere", fc.FORMS)
        why = fc.FORMS["sphere"][1]
        self.assertIn("ONLY", why, "the sphere's 'when' must read as a narrow exception")
        self.assertIn("genuinely spherical", why)

    def test_the_curve_form_exists_because_it_is_the_missed_tool(self):
        self.assertIn("curve_to_mesh", fc.FORMS)
        self.assertIn("curve", fc.FORMS["curve_to_mesh"][2].lower())

    def test_every_mapped_feature_points_at_a_real_form(self):
        for kw, form in fc.FEATURE_FORMS.items():
            with self.subTest(feature=kw):
                self.assertIn(form, fc.FORMS, f"{kw} maps to unknown form {form}")


class TheReportedBug(unittest.TestCase):
    """The user's exact complaint: 'the AI won't use spheres for some parts'."""

    def test_a_limb_is_not_a_sphere(self):
        for name in ("upper arm", "forearm", "left leg", "robot thigh", "index finger"):
            with self.subTest(feature=name):
                self.assertNotEqual(fc.classify(name)["form"], "sphere")
                self.assertEqual(fc.classify(name)["form"], "cylinder")

    def test_a_mechanical_plate_is_not_a_sphere(self):
        for name in ("armour plate", "machine housing", "chest panel", "shoulder pad"):
            with self.subTest(feature=name):
                self.assertNotEqual(fc.classify(name)["form"], "sphere")

    def test_a_cable_is_a_swept_curve_not_a_sphere(self):
        self.assertEqual(fc.classify("hydraulic hose")["form"], "curve_to_mesh")
        self.assertEqual(fc.classify("power cable")["form"], "curve_to_mesh")

    def test_a_genuine_sphere_still_classifies_as_one(self):
        for name in ("left eyeball", "ball joint", "planet", "berry"):
            with self.subTest(feature=name):
                self.assertEqual(fc.classify(name)["form"], "sphere",
                                 f"{name} really IS round - the fix must not ban spheres")

    def test_longest_keyword_wins_so_ball_joint_beats_ball(self):
        self.assertEqual(fc.classify("ball joint")["form"], "sphere")
        # 'ball' alone is a sphere, but a 'ball peen hammer head' is not the point -
        # the ordering test is that the compound phrase is not shadowed by the short one.
        self.assertEqual(fc.classify("ball joint")["keyword"], "ball joint")

    def test_unmatched_input_falls_back_to_box_never_sphere(self):
        c = fc.classify("zonking flibbertigibbet")
        self.assertFalse(c["matched"])
        self.assertEqual(c["form"], "box")
        self.assertIn("rather than adding a sphere", c["note"])

    def test_empty_input_falls_back_to_box_never_sphere(self):
        for bad in (None, "", "   "):
            with self.subTest(value=repr(bad)):
                c = fc.classify(bad)
                self.assertEqual(c["form"], "box")
                self.assertFalse(c["matched"])


class AuditBeforeBuilding(unittest.TestCase):
    def test_a_sphere_proposed_for_a_limb_is_caught(self):
        r = fc.audit([{"name": "upper arm", "form": "sphere"},
                      {"name": "forearm", "form": "cylinder"}])
        self.assertEqual(r["verdict"], "sphere-heavy")
        self.assertEqual(r["mismatchCount"], 1)
        mismatch = [p for p in r["parts"] if p.get("mismatch")][0]
        self.assertEqual(mismatch["name"], "upper arm")
        # The summary line comes first, the per-part reason must be present too.
        self.assertTrue(any("upper arm" in a for a in r["advice"]),
                        f"the offending part must be named in the advice: {r['advice']}")
        self.assertIn("limb", r["advice"][0].lower() + " " + " ".join(r["advice"]).lower())

    def test_a_correct_sphere_is_not_flagged(self):
        r = fc.audit([{"name": "eyeball", "form": "sphere"},
                      {"name": "neck", "form": "cylinder"}])
        self.assertEqual(r["mismatchCount"], 0)
        self.assertNotEqual(r["verdict"], "sphere-heavy")

    def test_mostly_spheres_is_flagged_for_review(self):
        r = fc.audit(["eyeball", "ball joint", "berry", "knob", "arm", "leg"])
        self.assertEqual(r["verdict"], "review",
                         "a part list that is mostly spheres is the placeholder look")

    def test_a_healthy_part_list_is_ok(self):
        r = fc.audit(["armour plate", "upper arm", "hydraulic hose", "eyeball",
                      "gear", "leaf"])
        self.assertEqual(r["verdict"], "ok")
        self.assertEqual(r["mismatchCount"], 0)

    def test_audit_accepts_bare_strings_and_dicts(self):
        r = fc.audit(["upper arm", {"part": "forearm"}])
        self.assertEqual(r["total"], 2)
        self.assertEqual([p["name"] for p in r["parts"]], ["upper arm", "forearm"])

    def test_an_empty_part_list_is_not_an_error(self):
        r = fc.audit([])
        self.assertEqual(r["verdict"], "ok")
        self.assertEqual(r["total"], 0)

    def test_audit_never_tells_you_to_delete_a_correct_sphere(self):
        r = fc.audit([{"name": "eyeball", "form": "sphere"}])
        self.assertEqual(r["advice"], [])


class PromptGuidance(unittest.TestCase):
    def test_guidance_leads_with_the_rule_not_the_table(self):
        g = fc.guidance()
        self.assertTrue(g.startswith("FORM SELECTION"))
        self.assertIn(fc.CORE_RULE, g)

    def test_guidance_names_the_cylindrical_and_box_families(self):
        g = fc.guidance()
        self.assertIn("CYLINDER", g)
        self.assertIn("BOX", g)
        self.assertIn("SWEPT CURVE", g)

    def test_guidance_includes_the_tell_for_a_wrong_sphere(self):
        self.assertIn("scaling a sphere", fc.guidance())

    def test_describe_is_a_single_line(self):
        d = fc.describe()
        self.assertNotIn("\n", d)
        self.assertIn("forms", d)

    def test_only_a_small_minority_of_features_are_spheres(self):
        """The whole point: spheres must be rare in the mapping."""
        total = len(fc.FEATURE_FORMS)
        spheres = sum(1 for f in fc.FEATURE_FORMS.values() if f == "sphere")
        self.assertLess(spheres / total, 0.25,
                        "if a quarter of features map to spheres, the default is still balls")


if __name__ == "__main__":
    unittest.main(verbosity=2)
