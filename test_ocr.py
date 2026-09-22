import unittest
from unittest.mock import patch

from chapter_detection import Line, detect_chapters
from pdf_outline import export_pdf, read_pdf
from test_outline import test_directory


class OCRTests(unittest.TestCase):
    def test_scanned_page_routing_and_cleanup(self):
        from pypdf import PdfWriter
        with test_directory() as folder:
            source = folder / 'scan.pdf'
            writer = PdfWriter()
            writer.add_blank_page(width=600, height=800)
            writer.write(source)
            with patch('local_ocr.OCRDocument') as backend:
                backend.return_value.lines.return_value = [Line('第一章 引言', 24, 1)]
                entries, empty = detect_chapters(source)
                self.assertEqual(entries[0].title, '第一章 引言')
                self.assertEqual(empty, 0)
                backend.return_value.close.assert_called_once()
            with patch('local_ocr.OCRDocument') as backend:
                backend.return_value.lines.side_effect = RuntimeError('OCR failed')
                with self.assertRaisesRegex(RuntimeError, 'OCR failed'):
                    detect_chapters(source)
                backend.return_value.close.assert_called_once()

    def test_real_chinese_scan(self):
        from PIL import Image, ImageDraw, ImageFont
        from reportlab.pdfgen import canvas
        from reportlab.lib.utils import ImageReader
        from pathlib import Path
        font = Path('C:/Windows/Fonts/msyh.ttc')
        if not font.exists():
            self.skipTest('Chinese font not installed')
        with test_directory() as folder:
            image = Image.new('RGB', (1200, 1600), 'white')
            draw = ImageDraw.Draw(image)
            draw.text((100, 130), '第一章 绪论', fill='black', font=ImageFont.truetype(str(font), 60))
            draw.text((100, 250), '1.1 研究背景', fill='black', font=ImageFont.truetype(str(font), 44))
            for i in range(12):
                draw.text((100, 370 + i * 65), '这是用于验证扫描识别功能的正文内容。',
                          fill='black', font=ImageFont.truetype(str(font), 28))
            source, output = folder / 'chinese-scan.pdf', folder / 'bookmarks.pdf'
            pdf = canvas.Canvas(str(source), pagesize=(600, 800))
            pdf.drawImage(ImageReader(image), 0, 0, width=600, height=800)
            pdf.save()
            self.assertFalse(read_pdf(source).pages[0].extract_text().strip())
            entries, empty = detect_chapters(source)
            self.assertEqual(empty, 0)
            self.assertTrue(any('第一章' in e.title for e in entries), entries)
            self.assertTrue(any('研究背景' in e.title for e in entries), entries)
            text = '\n'.join(f'{"#" * e.level} {e.title} {e.page}' for e in entries)
            export_pdf(source, output, text)
            self.assertEqual(read_pdf(output).get_destination_page_number(read_pdf(output).outline[0]), 0)
