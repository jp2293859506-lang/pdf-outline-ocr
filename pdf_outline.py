"""Local PDF bookmark editor. Page numbers are one-based."""
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader, PdfWriter


@dataclass
class Entry:
    level: int
    title: str
    page: int


def parse_outline(text, offset=0):
    entries = []
    previous = 0
    for number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        match = re.fullmatch(r'(#+)\s+(.+?)\s+(\d+)', raw.strip())
        if not match:
            raise ValueError(f'第 {number} 行格式错误，请使用：# 标题 页码')
        marks, title, page = match.groups()
        level = len(marks)
        if level > previous + 1:
            raise ValueError(f'第 {number} 行层级跳跃：首条必须为 #，子目录每次只能增加一个 #')
        actual = int(page) + offset
        if actual < 1:
            raise ValueError(f'第 {number} 行偏移后的页码必须大于 0')
        entries.append(Entry(level, title, actual))
        previous = level
    if not entries:
        raise ValueError('请先输入目录')
    return entries


def read_pdf(path, password=''):
    reader = PdfReader(path)
    if reader.is_encrypted and not reader.decrypt(password):
        raise ValueError('PDF 密码错误或未提供密码')
    return reader


def export_pdf(source, destination, text, offset=0, keep=True, password=''):
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve() or (
        destination.exists() and os.path.samefile(source, destination)
    ):
        raise ValueError('请另存为新文件，不能覆盖源 PDF')
    entries = parse_outline(text, offset)
    reader = read_pdf(source, password)
    for entry in entries:
        if entry.page > len(reader.pages):
            raise ValueError(f'“{entry.title}”指向第 {entry.page} 页，PDF 只有 {len(reader.pages)} 页')
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    if not keep:
        writer.root_object.pop('/Outlines', None)
    parents = []
    for entry in entries:
        parents = parents[:entry.level - 1]
        item = writer.add_outline_item(entry.title, entry.page - 1,
                                       parent=parents[-1] if parents else None)
        parents.append(item)
    writer.page_mode = '/UseOutlines'
    if reader.is_encrypted:
        writer.encrypt(password, algorithm='AES-256')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.pdf', delete=False) as stream:
            temporary = stream.name
            writer.write(stream)
        check = read_pdf(temporary, password)
        if len(check.pages) != len(reader.pages):
            raise ValueError('导出校验失败：页数不一致')
        os.replace(temporary, destination)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return len(entries)


def main():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from tkinter.scrolledtext import ScrolledText

    root = tk.Tk()
    root.title('PDF 目录工具 · CUDA 自适应版')
    root.geometry('960x810')
    root.minsize(850, 760)
    root.option_add('*Font', ('Microsoft YaHei UI', 10))
    frame = ttk.Frame(root, padding=22)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='为 PDF 添加目录', font=('Microsoft YaHei UI', 21, 'bold')).pack(anchor='w')
    ttk.Label(frame, text='创建可点击的侧栏书签，原文页数和排版保持不变。').pack(anchor='w', pady=(4, 16))
    path = tk.StringVar()
    status = tk.StringVar(value='请选择 PDF，然后输入目录。')
    row = ttk.Frame(frame)
    row.pack(fill='x')
    ttk.Entry(row, textvariable=path).pack(side='left', fill='x', expand=True)

    def choose():
        selected = filedialog.askopenfilename(filetypes=[('PDF 文件', '*.pdf')])
        if selected:
            path.set(selected)
            status.set('已选择：' + Path(selected).name)

    ttk.Button(row, text='选择 PDF', command=choose).pack(side='left', padx=(8, 0))
    options = ttk.Frame(frame)
    options.pack(fill='x', pady=12)
    ttk.Label(options, text='页码偏移').pack(side='left')
    offset = tk.StringVar(value='0')
    ttk.Spinbox(options, from_=-99999, to=99999, width=7, textvariable=offset).pack(side='left', padx=8)
    keep = tk.BooleanVar(value=True)
    ttk.Checkbutton(options, text='保留原有书签', variable=keep).pack(side='left', padx=10)
    ttk.Label(options, text='PDF 密码').pack(side='left', padx=(12, 4))
    password = tk.StringVar()
    ttk.Entry(options, textvariable=password, show='●', width=16).pack(side='left')
    ocr_options = ttk.Frame(frame)
    ocr_options.pack(fill='x', pady=(0, 8))
    ttk.Label(ocr_options, text='文字识别').pack(side='left')
    ocr_mode = tk.StringVar(value='自动 OCR（扫描页）')
    ocr_choices = {'自动 OCR（扫描页）': 'auto', '全部页面 OCR': 'all', '仅提取文字（快速）': 'off'}
    ttk.Combobox(ocr_options, textvariable=ocr_mode, values=list(ocr_choices),
                 state='readonly', width=23).pack(side='left', padx=8)
    ttk.Label(ocr_options, text='只保留明确章节标题，过滤题号、公式和普通大字。').pack(side='left')
    device_row = ttk.Frame(frame)
    device_row.pack(fill='x', pady=(0, 6))
    ttk.Label(device_row, text='OCR 设备').pack(side='left')
    device_mode = tk.StringVar(value='自动（优先 CUDA）')
    device_choices = {'自动（优先 CUDA）': 'auto', 'CPU': 'cpu', 'CUDA（失败回退 CPU）': 'cuda'}
    ttk.Combobox(device_row, textvariable=device_mode, values=list(device_choices),
                 state='readonly', width=25).pack(side='left', padx=8)
    device_status = tk.StringVar(value='实际设备：尚未运行 OCR')
    ttk.Label(frame, textvariable=device_status, wraplength=880).pack(anchor='w', pady=(0, 8))

    def check_device():
        import queue
        import threading
        from ocr_device import AdaptiveOCR
        events = queue.Queue()
        selected = device_choices[device_mode.get()]
        check_button.configure(state='disabled')
        auto_button.configure(state='disabled')
        device_status.set('正在检测设备并试运行模型…')

        def work():
            try:
                AdaptiveOCR(selected, lambda message: events.put(('status', message)))
            except Exception as error:
                events.put(('status', '设备检测失败：' + str(error)))
            finally:
                events.put(('done', None))

        def poll_device():
            try:
                while True:
                    kind, message = events.get_nowait()
                    if kind == 'done':
                        check_button.configure(state='normal')
                        auto_button.configure(state='normal')
                        return
                    device_status.set(message)
            except queue.Empty:
                root.after(100, poll_device)
        threading.Thread(target=work, daemon=True).start()
        root.after(100, poll_device)

    check_button = ttk.Button(device_row, text='检测设备', command=check_device)
    check_button.pack(side='left', padx=8)
    ttk.Label(frame, text='每行：# 标题 页码；用 ##、### 表示子目录。页码从 1 开始。').pack(anchor='w')
    ttk.Label(frame, text='例如正文第 1 页是 PDF 第 6 页，页码偏移填 5。').pack(anchor='w', pady=(2, 8))
    editor = ScrolledText(frame, height=10, undo=True, font=('Microsoft YaHei UI', 11))
    editor.pack(fill='both', expand=True)
    editor.insert('1.0', '# 第一章 引言 1\n## 研究背景 2\n# 第二章 方法 3\n')
    tree = ttk.Treeview(frame, columns=('page',), height=5)
    tree.heading('#0', text='目录预览')
    tree.heading('page', text='PDF 实际页码')
    tree.column('page', width=120, stretch=False)
    tree.pack(fill='both', expand=True, pady=12)

    def preview():
        entries = parse_outline(editor.get('1.0', 'end'), int(offset.get()))
        tree.delete(*tree.get_children())
        parents = []
        for entry in entries:
            parents = parents[:entry.level - 1]
            parents.append(tree.insert(parents[-1] if parents else '', 'end',
                                       text=entry.title, values=(entry.page,), open=True))
        status.set(f'目录格式有效，共 {len(entries)} 条；导出时检查 PDF 页数。')

    def guarded_preview():
        try:
            preview()
        except Exception as error:
            messagebox.showerror('目录格式错误', str(error))

    def import_text():
        selected = filedialog.askopenfilename(filetypes=[('UTF-8 文本', '*.txt'), ('所有文件', '*.*')])
        if selected:
            try:
                content = Path(selected).read_text(encoding='utf-8-sig')
                editor.delete('1.0', 'end')
                editor.insert('1.0', content)
            except Exception as error:
                messagebox.showerror('导入失败', str(error))

    def save():
        try:
            if not path.get() or not Path(path.get()).is_file():
                raise ValueError('请选择有效的 PDF 文件')
            preview()
            target = filedialog.asksaveasfilename(defaultextension='.pdf',
                initialfile=Path(path.get()).stem + '_带目录.pdf', filetypes=[('PDF 文件', '*.pdf')])
            if not target:
                return
            status.set('正在导出…')
            root.update_idletasks()
            count = export_pdf(path.get(), target, editor.get('1.0', 'end'),
                               int(offset.get()), keep.get(), password.get())
            status.set(f'完成：已添加 {count} 条目录，保存至 {target}')
            messagebox.showinfo('导出完成', f'已添加 {count} 条目录。\n{target}')
        except Exception as error:
            status.set('导出未完成，请检查输入。')
            messagebox.showerror('无法导出', str(error))

    def auto_detect():
        import queue
        import threading
        from chapter_detection import detect_chapters

        source = path.get()
        if not source or not Path(source).is_file():
            messagebox.showerror('无法检测', '请先选择有效的 PDF 文件')
            return
        before = editor.get('1.0', 'end')
        if before.strip() and not messagebox.askyesno('自动检测章节',
                '检测成功后将替换编辑区中的目录（可以撤销），是否继续？'):
            return
        original_password = password.get()
        original_offset = offset.get()
        selected_ocr = ocr_mode.get()
        selected_device = device_mode.get()
        updates = queue.Queue()
        auto_button.configure(state='disabled')
        check_button.configure(state='disabled')
        device_status.set('实际设备：等待 OCR；文字页无需 OCR 推理')
        status.set('正在检测章节…')

        def worker():
            try:
                result = detect_chapters(source, original_password,
                    lambda current, total: updates.put(('progress', (current, total))),
                    ocr_mode=ocr_choices[selected_ocr],
                    device=device_choices[selected_device],
                    device_status=lambda message: updates.put(('device', message)),
                    ocr_progress=lambda current, total: updates.put(('ocr', (current, total))))
                updates.put(('done', result))
            except Exception as error:
                updates.put(('error', str(error)))

        def poll():
            try:
                while True:
                    kind, value = updates.get_nowait()
                    if kind == 'device':
                        device_status.set(value)
                        continue
                    if kind in {'progress', 'ocr'}:
                        prefix = '正在 OCR 识别' if kind == 'ocr' else '正在检测章节'
                        status.set(f'{prefix}：{value[0]} / {value[1]} 页')
                        continue
                    auto_button.configure(state='normal')
                    check_button.configure(state='normal')
                    if kind == 'error':
                        status.set('检测未完成，原目录已保留。')
                        messagebox.showerror('无法检测章节', value)
                        return
                    if (path.get(), password.get(), editor.get('1.0', 'end'), offset.get(), ocr_mode.get(), device_mode.get()) != (
                            source, original_password, before, original_offset, selected_ocr, selected_device):
                        status.set('检测期间输入已更改，结果未应用。请重新检测。')
                        return
                    entries, empty_pages = value
                    editor.edit_separator()
                    editor.delete('1.0', 'end')
                    editor.insert('1.0', '\n'.join(
                        f'{"#" * entry.level} {entry.title} {entry.page}' for entry in entries))
                    editor.edit_separator()
                    offset.set('0')
                    preview()
                    note = f'；{empty_pages} 页无文字，未识别' if empty_pages else ''
                    status.set(f'已检测 {len(entries)} 条目录，使用 PDF 实际页码，偏移已归零{note}。请核对后导出。')
                    return
            except queue.Empty:
                root.after(100, poll)

        threading.Thread(target=worker, daemon=True).start()
        root.after(100, poll)

    buttons = ttk.Frame(frame)
    buttons.pack(fill='x')
    auto_button = ttk.Button(buttons, text='自动检测章节', command=auto_detect)
    auto_button.pack(side='left', padx=(0, 8))
    ttk.Button(buttons, text='导入目录文本', command=import_text).pack(side='left')
    ttk.Button(buttons, text='预览目录', command=guarded_preview).pack(side='left', padx=8)
    ttk.Button(buttons, text='另存为带目录的 PDF', command=save).pack(side='right')
    ttk.Label(frame, textvariable=status, wraplength=790).pack(anchor='w', pady=(12, 0))
    root.mainloop()


if __name__ == '__main__':
    main()
