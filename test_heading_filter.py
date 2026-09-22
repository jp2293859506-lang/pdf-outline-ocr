import unittest
from chapter_detection import Line, infer_entries


class HeadingFilterTests(unittest.TestCase):
    def test_math_exercises_and_cover_are_not_chapters(self):
        lines = [Line('普通正文的长度应当足够用于估算正文的基准字号。', 14, 9)] * 5
        lines += [Line('880题', 130, 1), Line('精讲精练', 70, 1),
                  Line('1. 求下列极限', 25, 9), Line('一、选择题', 26, 9),
                  Line('A. f(x)在区间内连续', 28, 9), Line('lim x → 0', 35, 9),
                  Line('基础题', 24, 9), Line('第一章', 32, 9),
                  Line('函数、极限、连续', 29, 9)]
        result = infer_entries(lines)
        self.assertEqual([(e.title, e.page) for e in result], [('第一章 函数、极限、连续', 9)])

    def test_split_contents_page_and_running_headers(self):
        lines = [Line('目', 30, 7), Line('录', 30, 7),
                 Line('第一章函数、极限、连续', 20, 7), Line('1', 14, 7),
                 Line('这是超过十六个字的正文内容以估算正常文字大小。', 14, 9),
                 Line('第一章 函数、极限、连续', 32, 9),
                 Line('第一章 函数、极限、连续', 14, 11)]
        result = infer_entries(lines)
        self.assertEqual([(e.title, e.page) for e in result], [('第一章 函数、极限、连续', 9)])

    def test_large_ordinary_text_never_becomes_heading(self):
        result = infer_entries([Line('正文内容超过十六个字用于计算正常文字的大小。', 12, 1),
                                Line('促销信息', 100, 1), Line('这是一段正文', 30, 1)])
        self.assertEqual(result, [])
