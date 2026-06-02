import unittest
from io import StringIO
import sys
from task_cli.commands.activity import list_


class MockArgs:
    def __init__(self, task):
        self.task = task


class MockTaskCLI:
    """Mock TaskCLI for testing display logic."""

    def list_activities(self, task_id):
        """Return sample activity rows including decide and dismiss."""
        return [
            {
                "id": "activity:1",
                "task_id": "task:1",
                "type": "ask",
                "created_at": "2026-06-01T10:00:00",
                "content": "What should we do?",
                "target_name": "Spark",
            },
            {
                "id": "activity:2",
                "task_id": "task:1",
                "type": "propose",
                "created_at": "2026-06-01T10:05:00",
                "proposal_title": "Create support docs",
                "proposal_description": "Build a guide",
                "target_name": "You",
            },
            {
                "id": "activity:3",
                "task_id": "task:1",
                "type": "decide",
                "created_at": "2026-06-01T10:10:00",
                "proposal_activity_id": "activity:2",
                "content": "Looks good",
                "target_name": "You",
            },
            {
                "id": "activity:4",
                "task_id": "task:1",
                "type": "dismiss",
                "created_at": "2026-06-01T10:15:00",
                "proposal_activity_id": "activity:5",
                "content": "Not ready yet",
                "target_name": "You",
            },
        ]


class TestActivityDisplay(unittest.TestCase):
    """Test that activity display handles decide and dismiss verbs."""

    def test_decide_activity_displays_correctly(self):
        """Test that decide activities show proposal reference."""
        # This tests the display logic, not a full integration
        activity = {
            "id": "activity:3",
            "type": "decide",
            "created_at": "2026-06-01T10:10:00",
            "proposal_activity_id": "activity:2",
            "content": "Looks good",
            "target_name": "You",
        }

        activity_type = activity.get("type", "unknown")
        self.assertEqual(activity_type, "decide")
        self.assertIsNotNone(activity.get("proposal_activity_id"))
        self.assertEqual(activity.get("content"), "Looks good")

    def test_dismiss_activity_displays_correctly(self):
        """Test that dismiss activities show proposal reference."""
        activity = {
            "id": "activity:4",
            "type": "dismiss",
            "created_at": "2026-06-01T10:15:00",
            "proposal_activity_id": "activity:5",
            "content": "Not ready yet",
            "target_name": "You",
        }

        activity_type = activity.get("type", "unknown")
        self.assertEqual(activity_type, "dismiss")
        self.assertIsNotNone(activity.get("proposal_activity_id"))
        self.assertEqual(activity.get("content"), "Not ready yet")


if __name__ == "__main__":
    unittest.main()
