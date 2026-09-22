"""Local OCR backend; rendered pages never leave the computer."""
from ocr_device import AdaptiveOCR


class OCRDocument:
    def __init__(self, source, password='', device='auto', device_status=None):
        try:
            import pypdfium2 as pdfium
            self.engine = AdaptiveOCR(device, device_status)
        except ImportError as error:
            raise ValueError('OCR 组件未安装，请运行安装OCR.cmd，然后重新启动程序。') from error
        self.document = pdfium.PdfDocument(str(source), password=password or None)

    def close(self):
        self.document.close()
        self.engine = None

    def lines(self, index):
        from chapter_detection import Line
        page = self.document[index]
        bitmap = None
        try:
            width, height = page.get_size()
            scale = min(2.5, 2400 / max(width, height))
            bitmap = page.render(scale=scale)
            result = self.engine(bitmap.to_pil().convert('RGB'))
            lines = []
            if result.txts is None or result.boxes is None:
                return lines
            for box, text, score in zip(result.boxes, result.txts, result.scores):
                if score < .55 or not text.strip():
                    continue
                top = min(point[1] for point in box) / scale
                bottom = max(point[1] for point in box) / scale
                size = (bottom - top) / .85
                lines.append((top, min(point[0] for point in box),
                              Line(text, size, index + 1, top < height * .06 or bottom > height * .94)))
            return [item[2] for item in sorted(lines, key=lambda item: (round(item[0] / 4), item[1]))]
        finally:
            if bitmap is not None:
                bitmap.close()
            page.close()
