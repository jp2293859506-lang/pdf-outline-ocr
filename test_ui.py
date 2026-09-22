import time
import tkinter as tk
import unittest
from unittest.mock import patch

import pdf_outline


class InterfaceTests(unittest.TestCase):
    def test_device_controls_and_background_check(self):
        def inspect(root):
            try:
                root.update()
                def walk(widget):
                    yield widget
                    for child in widget.winfo_children():
                        yield from walk(child)
                widgets = list(walk(root))
                selectors = [w for w in widgets if w.winfo_class() == 'TCombobox']
                self.assertEqual(selectors[1].get(), '自动（优先 CUDA）')
                self.assertEqual(len(selectors[1]['values']), 3)
                selectors[1].set('CPU')
                button = next(w for w in widgets if w.winfo_class() == 'TButton'
                              and w.cget('text') == '检测设备')
                button.invoke()
                deadline = time.monotonic() + 30
                while str(button.cget('state')) == 'disabled' and time.monotonic() < deadline:
                    root.update()
                    time.sleep(.02)
                self.assertEqual(str(button.cget('state')), 'normal')
                messages = [w.cget('text') for w in widgets if w.winfo_class() == 'TLabel']
                self.assertTrue(any('实际设备：CPU' in message for message in messages), messages)
            finally:
                root.destroy()
        with patch.object(tk.Tk, 'mainloop', inspect):
            pdf_outline.main()
