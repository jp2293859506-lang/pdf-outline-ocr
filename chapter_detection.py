"""Heuristic chapter detection with optional local OCR."""
import re
from collections import defaultdict
from dataclasses import dataclass

from pdf_outline import Entry, read_pdf


@dataclass
class Line:
    text: str
    size: float
    page: int
    margin: bool = False


CHAPTER = re.compile(r'^第\s*([零〇一二三四五六七八九十百千万两\d]+)\s*([部篇章节])')
ENGLISH_CHAPTER = re.compile(r'^(chapter|part|appendix)\s+(\d+|[ivxlcdm]+|[a-z])\b', re.I)
DECIMAL = re.compile(r'^(\d{1,3}(?:\.\d{1,3}){1,3})[.、]?\s*(?=[A-Za-z\u4e00-\u9fff])')
NAMED = {'前言', '序言', '绪论', '引言', '结论', '参考文献', '附录', '致谢',
         'abstract', 'introduction', 'background', 'methods', 'results',
         'discussion', 'conclusion', 'conclusions', 'references', 'acknowledgments'}


def _clean(text):
    text = re.sub(r'\s+', ' ', text).strip()
    return re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', '', text)


def _body_size(lines):
    # OCR formula boxes have highly variable heights. Use the median of longer
    # text lines, not the most frequent rounded height of every detected box.
    sizes = sorted(float(line.size) for line in lines if len(line.text.strip()) >= 16)
    if not sizes:
        sizes = sorted(float(line.size) for line in lines)
    return sizes[len(sizes) // 2] if sizes else 12


def infer_entries(lines):
    pages = defaultdict(list)
    for line in lines:
        pages[line.page].append(line)
    candidates = []
    chapter_scope = None
    global_body = _body_size(lines)
    for page, page_lines in pages.items():
        texts = [_clean(line.text) for line in page_lines]
        first = ''.join(texts[:3]).replace(' ', '').lower()
        chapter_count = sum(bool(CHAPTER.match(t) or ENGLISH_CHAPTER.match(t)) for t in texts)
        leaders = sum(bool(re.search(r'[.·…]{3,}', t)) for t in texts)
        if first.startswith(('目录', 'tableofcontents', 'contents')) or (chapter_count >= 3 and leaders >= 2):
            continue
        body = _body_size(page_lines) if sum(len(l.text) >= 16 for l in page_lines) >= 3 else global_body
        for index, line in enumerate(page_lines):
            title = texts[index]
            if line.margin and line.size < body * 1.25:
                continue
            if not 2 <= len(title) <= 55 or re.search(r'[。；;！？!?=<>∫∑√{}]|\.{2,}|…|·{3,}', title):
                continue
            chapter = CHAPTER.match(title)
            english = ENGLISH_CHAPTER.match(title)
            decimal = DECIMAL.match(title)
            level, key = None, None
            if chapter:
                level = 2 if chapter[2] == '节' else 1
                key = ('chapter', chapter[1], chapter[2])
                # Number and title are often distinct OCR boxes / separate lines.
                if not title[chapter.end():].strip() and index + 1 < len(page_lines):
                    following = page_lines[index + 1]
                    suffix = texts[index + 1]
                    if (2 <= len(suffix) <= 35 and following.size >= line.size * .8
                            and not re.search(r'[。；;！？!?=<>∫∑√{}]|^第|^\d', suffix)):
                        title += ' ' + suffix
                suffix = title[chapter.end():].strip()
                if suffix:
                    title = title[:chapter.end()].replace(' ', '') + ' ' + suffix
                # A small repeated running header is not a new chapter.
                if len(page_lines) > 3 and line.size < body * 1.12:
                    continue
                if level == 1:
                    chapter_scope = key
            elif english:
                level, key = 1, ('english', english[1].lower(), english[2].lower())
                if len(page_lines) > 3 and line.size < body * 1.12:
                    continue
                chapter_scope = key
            elif decimal:
                if (len(page_lines) > 1 and line.size < body * 1.15) or re.search(r'[,，:：]', title):
                    continue
                level = decimal[1].count('.') + 1
                key = ('decimal', chapter_scope, decimal[1], title)
            elif title.lower() in NAMED and line.size >= body * 1.25:
                level, key = (2 if title.lower() == 'background' else 1), ('named', title.lower())
            else:
                continue
            candidates.append((key, float(line.size), Entry(level, title, page)))
    # Prefer the prominent body heading over its smaller running-header copies.
    best = {}
    for key, size, entry in candidates:
        if key not in best or size > best[key][0]:
            best[key] = (size, entry)
    entries = [entry for _, entry in best.values()]
    entries.sort(key=lambda entry: entry.page)  # Stable within each page.
    previous = 0
    for entry in entries:
        entry.level = min(entry.level, previous + 1)
        previous = entry.level
    return entries


def detect_chapters(source, password='', progress=None, ocr_mode='auto', ocr_progress=None,
                    device='auto', device_status=None):
    if ocr_mode not in {'auto', 'all', 'off'}:
        raise ValueError('未知 OCR 模式')
    reader = read_pdf(source, password)
    from contextlib import ExitStack
    try:
        with ExitStack() as resources:
            return _scan(reader, source, password, progress, ocr_mode, ocr_progress, [], resources,
                         device, device_status)
    finally:
        reader.close()


def _scan(reader, source, password, progress, ocr_mode, ocr_progress, lines, resources,
          device, device_status):
    text_pages = 0
    total = len(reader.pages)
    ocr_document = None
    for number, page in enumerate(reader.pages, 1):
        rows = defaultdict(list)
        height = float(page.mediabox.height)

        def visit(text, cm, tm, font, font_size):
            if not text.strip():
                return
            # Convert text origin to page coordinates, including form transforms.
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            scale = (cm[2] ** 2 + cm[3] ** 2) ** 0.5 or 1
            size = abs(float(font_size) * scale)
            for index, part in enumerate(text.splitlines()):
                if part.strip():
                    baseline = y - index * size * 1.2
                    rows[round(baseline / 2) * 2].append((x, part.strip(), size))

        extracted = page.extract_text(visitor_text=visit) or ''
        needs_ocr = ocr_mode == 'all' or (ocr_mode == 'auto' and
                    sum(character.isalnum() for character in extracted) < 40)
        if needs_ocr:
            if ocr_progress:
                ocr_progress(number, total)
            if ocr_document is None:
                from local_ocr import OCRDocument
                ocr_document = OCRDocument(source, password, device=device, device_status=device_status)
                resources.callback(ocr_document.close)
            detected = ocr_document.lines(number - 1)
            if detected:
                lines.extend(detected)
                text_pages += 1
                if progress:
                    progress(number, total)
                continue
        if extracted.strip():
            text_pages += 1
        for y, fragments in sorted(rows.items(), reverse=True):
            fragments.sort(key=lambda fragment: fragment[0])
            title = ' '.join(fragment[1] for fragment in fragments)
            size = max(fragment[2] for fragment in fragments)
            lines.append(Line(title, size, number, y > height * .94 or y < height * .06))
        if progress:
            progress(number, total)
    if not text_pages:
        raise ValueError('未识别到文字。请启用 OCR；若已启用，请检查扫描清晰度或页面方向。')
    entries = infer_entries(lines)
    if not entries:
        raise ValueError('未识别到明显的章节标题，请手动输入目录。')
    return entries, total - text_pages

