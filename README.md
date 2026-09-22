# PDF Outline OCR

中文桌面 PDF 目录工具。手动编辑或自动识别章节，为 PDF 添加可点击的侧栏书签。
支持文本 PDF、扫描件中英文 OCR，以及 CUDA 自动检测和 CPU 回退。

## 功能

- 使用 `# 标题 页码` 输入多级目录，也可导入 UTF-8 文本。
- 自动识别明确的中文章/节、英文 Chapter、分级数字标题。
- 排除普通题号、公式、封面大字、明显的印刷目录页和重复页眉。
- 自动 OCR 扫描页、全部页面 OCR、仅提取文字三种模式。
- 自动 / CPU / CUDA 设备选择；检查三个 OCR 模型并实际试运行。
- CUDA 初始化或识别失败时回退 CPU，重试当前页并显示原因。
- 页码偏移、书签预览、保留或替换原书签、密码 PDF 支持。
- 在本地处理，不上传 PDF，不需要 API 密钥。

## 安装与启动

推荐 Windows 10/11、64 位 Python 3.12，安装 Python 时包含 Tkinter 并添加到 PATH。

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt -r requirements-ocr.txt
.venv\Scripts\python pdf_outline.py
```

安装好依赖后也可双击 `启动.cmd`。启动脚本优先使用项目 `.venv`，否则使用 PATH 中的 Python。
`安装OCR.cmd` 提供另一种安装方式：将普通 OCR 依赖安装到项目的 `.ocr-libs`。
首次安装需要联网，模型随依赖包安装。

### 可选 CUDA

已有兼容 NVIDIA 显卡驱动时，关闭程序后运行 `安装CUDA支持.cmd`。
GPU 推理组件及 CUDA/cuDNN 运行库将安装到本项目的 `.gpu-libs`，首次下载较大。
该目录优先于 CPU 依赖加载；无需将 CPU、GPU 两种 ONNX Runtime 装进同一虚拟环境。

重启程序，点击“检测设备”。仅检测到显卡或 CUDA provider 不等于 GPU 可用，程序会验证
检测、方向分类、识别三个模型并试运行；失败时明确显示 CPU 回退原因。
选择 CUDA 同样允许回退，不是强制 GPU。GPU 0 的 CUDA 内存池上限设为 2 GiB，
并非整个进程显存的硬上限。部分算子及 PDF 渲染仍可能使用 CPU。

固定使用 ONNX Runtime GPU 1.26.0、CUDA 12、cuDNN 9；新版 cuDNN 扩展 DLL 会显式预加载。
参考：[ONNX Runtime CUDA](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html)、
[RapidOCR](https://rapidai.github.io/RapidOCRDocs/main/install_usage/rapidocr/how_to_use_infer_engine/)。

## 使用

1. 选择 PDF，加密文件输入密码。
2. 输入目录或点击“自动检测章节”。
3. 检查标题、层级和实际页码，按需编辑。
4. 另存为带书签的新 PDF。

```text
# 第一章 引言 1
## 1.1 研究背景 2
# 第二章 方法 5
```

实际 PDF 页码 = 输入页码 + 偏移。例如正文第 1 页位于 PDF 第 6 页，偏移填 5。
自动检测使用 PDF 实际页码，并将偏移归零。程序拒绝覆盖输入 PDF。

## 限制

- 输出是侧栏书签，不插入可见目录页；OCR 不给正文添加可搜索文字层。
- 采用保守规则，未编号的自定义标题、正文同字号标题、复杂分栏或旋转文字可能漏检。
- 自动 OCR 仅处理少于 40 个可提取文字字符的页面；文字层损坏时可选全部页面 OCR。
- 加密输出以输入密码重新加密，不保留原权限设置；修改已签名 PDF 会使原签名失效。
- 大文件导出可能暂时阻塞界面，章节检测在后台执行。

## 测试

```powershell
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m unittest discover -v
```

测试包括 PDF 书签跳转、密码保护、章节筛选、设备回退、中文扫描件和 Tkinter 界面。
界面测试需要桌面环境，中文扫描测试在缺少 Windows 微软雅黑字体时跳过。
通过批处理安装到本地依赖目录的用户，可先在 cmd 中执行 `call runtime.cmd` 再运行测试。

本仓库只包含项目源码和测试，不包含用户 PDF、模型文件、运行库、日志或账户凭据。
