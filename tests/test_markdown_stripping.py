import unittest
from task_program.spark_service import _strip_markdown


class TestMarkdownStripping(unittest.TestCase):
    """Test that markdown is properly stripped from text."""

    def test_strip_bold(self):
        self.assertEqual(_strip_markdown("**bold**"), "bold")
        self.assertEqual(_strip_markdown("text with **bold** in it"), "text with bold in it")

    def test_strip_italic(self):
        self.assertEqual(_strip_markdown("*italic*"), "italic")
        self.assertEqual(_strip_markdown("_italic_"), "italic")
        self.assertEqual(_strip_markdown("text *italic* and more"), "text italic and more")

    def test_strip_headers(self):
        self.assertEqual(_strip_markdown("# Header"), "Header")
        self.assertEqual(_strip_markdown("## Subheader"), "Subheader")
        self.assertEqual(_strip_markdown("### Level 3"), "Level 3")

    def test_strip_links(self):
        self.assertEqual(_strip_markdown("[click here](https://example.com)"), "click here")
        self.assertEqual(_strip_markdown("Check [this](url) out"), "Check this out")

    def test_strip_inline_code(self):
        self.assertEqual(_strip_markdown("`code`"), "code")
        self.assertEqual(_strip_markdown("Run `npm install` first"), "Run npm install first")

    def test_strip_code_blocks(self):
        self.assertIn("python code here", _strip_markdown("```python\npython code here\n```"))

    def test_preserve_plain_text(self):
        plain = "Just plain text with no formatting"
        self.assertEqual(_strip_markdown(plain), plain)

    def test_empty_string(self):
        self.assertEqual(_strip_markdown(""), "")

    def test_none_handling(self):
        self.assertIsNone(_strip_markdown(None))

    def test_mixed_formatting(self):
        text = "This is **bold** and *italic* with a [link](url) and `code`"
        result = _strip_markdown(text)
        self.assertNotIn("**", result)
        self.assertNotIn("*", result)
        self.assertNotIn("[", result)
        self.assertNotIn("](", result)
        self.assertNotIn("`", result)
        self.assertIn("bold", result)
        self.assertIn("italic", result)
        self.assertIn("link", result)
        self.assertIn("code", result)


if __name__ == "__main__":
    unittest.main()
