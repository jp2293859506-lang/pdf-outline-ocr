"""Select and validate an OCR execution device; never trust the GPU name alone."""
import logging
from pathlib import Path

LOG = logging.getLogger(__name__)
CUDA = 'CUDAExecutionProvider'
CPU = 'CPUExecutionProvider'
_dll_handles = []
_preloaded_libraries = {}


def preload_cudnn_extensions(root):
    """ORT 1.26's preload list predates these newer cuDNN 9 sublibraries."""
    import ctypes
    for name in ('cudnn_engines_tensor_ir64_9.dll', 'cudnn_ext64_9.dll'):
        library = root / 'cudnn' / 'bin' / name
        key = str(library)
        if library.is_file() and key not in _preloaded_libraries:
            try:
                _preloaded_libraries[key] = ctypes.WinDLL(key)
            except OSError as error:
                raise RuntimeError(f'无法加载 cuDNN 组件 {name}：{error}') from error


def providers():
    import onnxruntime as ort
    return ort.get_available_providers()


def make_engine(device):
    import onnxruntime as ort
    if device == 'cuda' and hasattr(ort, 'preload_dlls'):
        # Support both pip --target runtimes and the system CUDA installation.
        import os
        root = Path(__file__).resolve().parent / '.gpu-libs' / 'nvidia'
        if os.name == 'nt' and root.exists():
            for directory in root.glob('*/bin'):
                _dll_handles.append(os.add_dll_directory(str(directory)))
        ort.preload_dlls()
        if os.name == 'nt':
            preload_cudnn_extensions(root)
    from rapidocr import RapidOCR
    return RapidOCR(params={
        'EngineConfig.onnxruntime.use_cuda': device == 'cuda',
        'EngineConfig.onnxruntime.use_dml': False,
        'EngineConfig.onnxruntime.use_cann': False,
        'EngineConfig.onnxruntime.use_coreml': False,
        'EngineConfig.onnxruntime.cuda_ep_cfg.device_id': 0,
        'EngineConfig.onnxruntime.cuda_ep_cfg.gpu_mem_limit': 2 * 1024 ** 3,
    })


def sessions(engine):
    # Verified against pinned RapidOCR 3.9.2. Check every model, not only detection.
    return [getattr(engine, name).session.session
            for name in ('text_det', 'text_cls', 'text_rec')]


def verify_engine(engine, device):
    import numpy as np
    expected = CUDA if device == 'cuda' else CPU
    defaults = [(1, 3, 64, 64), (1, 3, 48, 192), (1, 3, 48, 320)]
    for session, default in zip(sessions(engine), defaults):
        actual = session.get_providers()
        if not actual or actual[0] != expected:
            raise RuntimeError(f'模型实际执行后端为 {actual}，未启用 {expected}；'
                               '请检查显卡驱动及 CUDA 12 / cuDNN 9 运行库')
        # Let the app handle retries so it can report the actual device accurately.
        session.disable_fallback()
        inputs = session.get_inputs()
        if len(inputs) != 1:
            raise RuntimeError('OCR 模型输入结构不兼容')
        tensor = inputs[0]
        shape = [dimension if isinstance(dimension, int) and dimension > 0 else default[i]
                 for i, dimension in enumerate(tensor.shape)]
        session.run(None, {tensor.name: np.zeros(shape, dtype=np.float32)})


class AdaptiveOCR:
    def __init__(self, mode='auto', report=None, factory=None, checker=None, available=None):
        if mode not in {'auto', 'cpu', 'cuda'}:
            raise ValueError('未知 OCR 设备模式')
        self.report = report or (lambda message: None)
        self.factory = factory or make_engine
        self.checker = checker or verify_engine
        self.engine = None
        self.device = None
        self.reason = ''
        if mode == 'cpu':
            self._cpu('已手动选择 CPU')
            return
        self.report('正在检测 CUDA 并试运行 OCR 模型…')
        candidate = None
        try:
            supported = (available or providers)()
            if CUDA in supported:
                candidate = self.factory('cuda')
                self.checker(candidate, 'cuda')
                self.engine = candidate
                self.device = 'cuda'
                self.report('实际设备：CUDA（GPU 0，三个 OCR 模型试运行通过）')
                return
            reason = '当前推理组件不提供 CUDA；可运行“安装CUDA支持.cmd”'
        except Exception as error:
            LOG.warning('CUDA initialization/probe failed', exc_info=True)
            reason = 'CUDA 初始化或试运行失败：' + self._short(error)
        candidate = None
        self._cpu(reason)

    @staticmethod
    def _short(error):
        if isinstance(error, UnicodeDecodeError):
            return 'GPU 底层错误信息编码异常，请检查 cuDNN 组件及 startup-error.log'
        return ' '.join(str(error).split())[:220] or type(error).__name__

    def _cpu(self, reason):
        self.engine = None
        self.device = 'cpu'
        self.reason = reason
        self.report('正在加载 CPU：' + reason)
        self.engine = self.factory('cpu')
        self.checker(self.engine, 'cpu')
        self.report('实际设备：CPU；' + reason)

    def __call__(self, image):
        try:
            result = self.engine(image)
            if self.device == 'cuda' and any(s.get_providers()[0] != CUDA for s in sessions(self.engine)):
                raise RuntimeError('运行期间 CUDA 已失效')
            return result
        except Exception as error:
            if self.device != 'cuda':
                raise
            LOG.warning('CUDA inference failed; retrying this page on CPU', exc_info=True)
            self._cpu('CUDA 识别失败，已重试本页：' + self._short(error))
            return self.engine(image)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', choices=['auto', 'cpu', 'cuda'], default='auto')
    arguments = parser.parse_args()
    AdaptiveOCR(arguments.device, print)
