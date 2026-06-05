from django.test import TestCase
from apps.requirement_analysis.knowledge_utils import extract_text, split_into_chunks


class ExtractTextTest(TestCase):
    def test_extract_txt(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix='.txt', mode='w',
                                         encoding='utf-8', delete=False) as f:
            f.write("Hello world\n\nSecond paragraph")
            path = f.name
        try:
            result = extract_text(path)
            self.assertIn("Hello world", result)
            self.assertIn("Second paragraph", result)
        finally:
            os.unlink(path)

    def test_extract_md(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix='.md', mode='w',
                                         encoding='utf-8', delete=False) as f:
            f.write("# Title\n\nContent here")
            path = f.name
        try:
            result = extract_text(path)
            self.assertIn("Content here", result)
        finally:
            os.unlink(path)

    def test_unsupported_format_raises(self):
        from apps.requirement_analysis.knowledge_utils import UnsupportedFormatError
        with self.assertRaises(UnsupportedFormatError):
            extract_text("document.xlsx")


class SplitIntoChunksTest(TestCase):
    def test_short_text_single_chunk(self):
        result = split_into_chunks("Short text", max_chunk_size=500)
        self.assertEqual(result, ["Short text"])

    def test_blank_paragraphs_skipped(self):
        result = split_into_chunks("Para1\n\n\n\nPara2", max_chunk_size=500)
        self.assertEqual(result, ["Para1", "Para2"])

    def test_long_paragraph_is_hard_split(self):
        long_text = "A" * 1200
        result = split_into_chunks(long_text, max_chunk_size=500)
        self.assertEqual(len(result), 3)
        self.assertEqual(len(result[0]), 500)
        self.assertEqual(len(result[1]), 500)
        self.assertEqual(len(result[2]), 200)

    def test_empty_text_returns_empty_list(self):
        result = split_into_chunks("", max_chunk_size=500)
        self.assertEqual(result, [])
