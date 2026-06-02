import unittest
from task_program.models import ActivityVerb


class TestDecideVerb(unittest.TestCase):
    """Test that the decide and dismiss verbs are defined."""

    def test_decide_verb_exists(self):
        """Test that DECIDE is in the ActivityVerb enum."""
        self.assertTrue(hasattr(ActivityVerb, "DECIDE"))
        self.assertEqual(ActivityVerb.DECIDE.value, "decide")

    def test_dismiss_verb_exists(self):
        """Test that DISMISS is in the ActivityVerb enum."""
        self.assertTrue(hasattr(ActivityVerb, "DISMISS"))
        self.assertEqual(ActivityVerb.DISMISS.value, "dismiss")

    def test_all_required_verbs_exist(self):
        """Test that all expected verbs are present."""
        required = ["UPDATE", "ASK", "INSTRUCT", "PROPOSE", "DECIDE", "DISMISS"]
        for verb in required:
            with self.subTest(verb=verb):
                self.assertTrue(hasattr(ActivityVerb, verb), f"{verb} not found in ActivityVerb")

    def test_delegate_not_yet_implemented(self):
        """Test that DELEGATE is not yet in the enum."""
        self.assertFalse(hasattr(ActivityVerb, "DELEGATE"))


if __name__ == "__main__":
    unittest.main()
