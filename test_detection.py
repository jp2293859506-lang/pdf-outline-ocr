import unittest
from chapter_detection import Line, detect_chapters, infer_entries
from pdf_outline import export_pdf, parse_outline, read_pdf
from test_outline import test_directory


class DetectionTests(unittest.TestCase):
    def test_patterns_and_noise(self):
        lines = [Line('正文内容' * 100, 12, 1),
                 Line('第一章 绪论', 20, 1), Line('1.1 研究背景', 16, 1),
                 Line('1.1.1 国内研究', 14, 2), Line('第二章 方法', 20, 3),
                 Line('Chapter 3 Results', 20, 4),
                 Line('第二章 方法 ........ 12', 12, 1),
                 Line('1. 这是正文列表，并不是标题。', 12, 2),
                 Line('第八章 页眉', 12, 1, True), Line('第八章 页眉', 12, 2, True),
                 Line('目录', 24, 1), Line('23', 12, 3)]
        entries = infer_entries(lines)
        self.assertEqual([e.level for e in entries], [1, 2, 3, 1, 1])
        self.assertEqual([e.page for e in entries], [1, 1, 2, 3, 4])

    def test_font_titles_and_missing_parent(self):
        entries = infer_entries([Line('normal body ' * 100, 12, 1),
                                Line('Introduction', 22, 1),
                                Line('Background', 17, 2)])
        self.assertEqual([e.title for e in entries], ['Introduction', 'Background'])
        self.assertEqual([e.level for e in entries], [1, 2])
        self.assertEqual(infer_entries([Line('1.2.3 标题', 12, 1)])[0].level, 1)

    def test_pdf_roundtrip(self):
        from reportlab.pdfgen import canvas
        with test_directory() as folder:
            source, output = folder / 'chapters.pdf', folder / 'output.pdf'
            pdf = canvas.Canvas(str(source))
            for heading in ('Chapter 1 Introduction', 'Chapter 2 Methods'):
                pdf.setFont('Helvetica', 22)
                pdf.drawString(60, 760, heading)
                pdf.setFont('Helvetica', 16)
                pdf.drawString(60, 720, '1.1 Background')
                pdf.setFont('Helvetica', 12)
                for i in range(12):
                    pdf.drawString(60, 680 - i * 20, 'Ordinary body text to establish the main font size.')
                pdf.showPage()
            pdf.save()
            progress = []
            entries, empty = detect_chapters(source, progress=lambda a, b: progress.append((a, b)))
            self.assertEqual(empty, 0)
            self.assertEqual(len(entries), 4)
            self.assertEqual([e.page for e in entries], [1, 1, 2, 2])
            self.assertEqual([e.level for e in entries], [1, 2, 1, 2])
            self.assertEqual(progress[-1], (2, 2))
            text = '\n'.join(f'{"#" * e.level} {e.title} {e.page}' for e in entries)
            parse_outline(text)
            export_pdf(source, output, text)
            reader = read_pdf(output)
            self.assertEqual(reader.get_destination_page_number(reader.outline[2]), 1)

    def test_empty_pdf(self):
        from pypdf import PdfWriter
        with test_directory() as folder:
            source = folder / 'scan.pdf'
            writer = PdfWriter()
            writer.add_blank_page(width=300, height=400)
            writer.write(source)
            with self.assertRaisesRegex(ValueError, 'OCR'):
                detect_chapters(source, ocr_mode='off')
