import tempfile
import uuid
from contextlib import contextmanager

@contextmanager
def test_directory():
    folder = Path(__file__).parent / ('test_' + uuid.uuid4().hex)
    folder.mkdir(mode=0o777)
    try:
        yield folder
    finally:
        for item in folder.iterdir():
            item.unlink()
        folder.rmdir()

import unittest
from pathlib import Path
from pypdf import PdfWriter
from pdf_outline import export_pdf, parse_outline, read_pdf


class OutlineTests(unittest.TestCase):
    def test_parse(self):
        entries = parse_outline('# 第一章 1\n## 子章节 2\n# 第二章 3', 2)
        self.assertEqual([e.page for e in entries], [3, 4, 5])
        for text in ('', '## 错误 1', '# 一级 1\n### 跳级 2', '# 标题 -1'):
            with self.assertRaises(ValueError):
                parse_outline(text)

    def test_export(self):
        with test_directory() as folder:
            source = Path(folder) / 'source.pdf'
            target = Path(folder) / 'result.pdf'
            writer = PdfWriter()
            for _ in range(4):
                writer.add_blank_page(width=300, height=400)
            writer.add_outline_item('原书签', 0)
            writer.add_metadata({'/Title': '测试文档'})
            writer.write(source)
            original = source.read_bytes()
            for keep in (True, False):
                export_pdf(source, target, '# 第一章 1\n## 小节 2', offset=1, keep=keep)
                result = read_pdf(target)
                self.assertEqual(len(result.pages), 4)
                self.assertEqual(result.metadata.title, '测试文档')
                outline = result.outline
                if keep:
                    self.assertEqual(outline.pop(0).title, '原书签')
                self.assertEqual(outline[0].title, '第一章')
                self.assertEqual(result.get_destination_page_number(outline[0]), 1)
                self.assertEqual(result.get_destination_page_number(outline[1][0]), 2)
            saved = target.read_bytes()
            with self.assertRaises(ValueError):
                export_pdf(source, target, '# 越界 5')
            self.assertEqual(target.read_bytes(), saved)
            with self.assertRaises(ValueError):
                export_pdf(source, source, '# 第一章 1')
            self.assertEqual(source.read_bytes(), original)

    def test_encrypted(self):
        with test_directory() as folder:
            source, target = Path(folder) / 'locked.pdf', Path(folder) / 'output.pdf'
            writer = PdfWriter()
            writer.add_blank_page(width=300, height=400)
            writer.encrypt('secret', algorithm='AES-256')
            writer.write(source)
            with self.assertRaises(ValueError):
                export_pdf(source, target, '# 开始 1', password='wrong')
            export_pdf(source, target, '# 开始 1', password='secret')
            reader = read_pdf(target, 'secret')
            self.assertTrue(reader.is_encrypted)
            self.assertEqual(reader.outline[0].title, '开始')


if __name__ == '__main__':
    unittest.main()


