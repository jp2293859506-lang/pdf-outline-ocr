import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from ocr_device import AdaptiveOCR, verify_engine, CUDA, CPU


def fake_engine(provider):
    engine = Mock(return_value='recognized')
    for name in ('text_det', 'text_cls', 'text_rec'):
        session = Mock()
        session.get_providers.return_value = [provider]
        session.get_inputs.return_value = [SimpleNamespace(name='image', shape=[1, 3, None, None])]
        setattr(engine, name, SimpleNamespace(session=SimpleNamespace(session=session)))
    return engine


class DeviceTests(unittest.TestCase):
    def test_cpu_does_not_probe_cuda(self):
        cpu = fake_engine(CPU)
        available = Mock(side_effect=AssertionError('CPU mode must not probe CUDA'))
        selected = AdaptiveOCR('cpu', factory=Mock(return_value=cpu), available=available)
        self.assertEqual(selected.device, 'cpu')
        available.assert_not_called()
        for name in ('text_det', 'text_cls', 'text_rec'):
            getattr(cpu, name).session.session.run.assert_called_once()

    def test_missing_cuda_falls_back_in_both_modes(self):
        for mode in ('auto', 'cuda'):
            reports = []
            selected = AdaptiveOCR(mode, reports.append, factory=lambda _: fake_engine(CPU),
                                   available=lambda: [CPU])
            self.assertEqual(selected.device, 'cpu')
            self.assertIn('不提供 CUDA', reports[-1])

    def test_cuda_is_verified(self):
        gpu = fake_engine(CUDA)
        selected = AdaptiveOCR(factory=lambda _: gpu, available=lambda: [CUDA, CPU])
        self.assertEqual(selected.device, 'cuda')
        self.assertEqual(selected('image'), 'recognized')
        for name in ('text_det', 'text_cls', 'text_rec'):
            getattr(gpu, name).session.session.disable_fallback.assert_called_once()

    def test_silent_cpu_provider_is_not_reported_as_cuda(self):
        factory = Mock(side_effect=[fake_engine(CPU), fake_engine(CPU)])
        with self.assertLogs('ocr_device', 'WARNING'):
            selected = AdaptiveOCR(factory=factory, available=lambda: [CUDA, CPU])
        self.assertEqual(selected.device, 'cpu')
        self.assertIn('未启用', selected.reason)

    def test_initialization_failure(self):
        factory = Mock(side_effect=[RuntimeError('missing cudnn DLL'), fake_engine(CPU)])
        with self.assertLogs('ocr_device', 'WARNING'):
            selected = AdaptiveOCR(factory=factory, available=lambda: [CUDA])
        self.assertEqual(selected.device, 'cpu')
        self.assertIn('missing cudnn', selected.reason)

    def test_failed_warmup_falls_back(self):
        gpu = fake_engine(CUDA)
        gpu.text_rec.session.session.run.side_effect = RuntimeError('out of memory')
        with self.assertLogs('ocr_device', 'WARNING'):
            selected = AdaptiveOCR(factory=Mock(side_effect=[gpu, fake_engine(CPU)]),
                                   available=lambda: [CUDA])
        self.assertEqual(selected.device, 'cpu')

    def test_runtime_failure_retries_page_once_and_stays_cpu(self):
        gpu = fake_engine(CUDA)
        gpu.side_effect = RuntimeError('CUDA out of memory')
        cpu = fake_engine(CPU)
        selected = AdaptiveOCR(factory=Mock(side_effect=[gpu, cpu]), available=lambda: [CUDA])
        with self.assertLogs('ocr_device', 'WARNING'):
            self.assertEqual(selected('page 1'), 'recognized')
        self.assertEqual(selected('page 2'), 'recognized')
        self.assertEqual(selected.device, 'cpu')
        self.assertEqual(gpu.call_count, 1)
        self.assertEqual(cpu.call_count, 2)

    def test_cpu_error_is_not_hidden(self):
        cpu = fake_engine(CPU)
        cpu.side_effect = ValueError('bad input')
        selected = AdaptiveOCR('cpu', factory=lambda _: cpu)
        with self.assertRaisesRegex(ValueError, 'bad input'):
            selected('bad image')

    def test_all_three_models_must_use_cuda(self):
        gpu = fake_engine(CUDA)
        gpu.text_cls.session.session.get_providers.return_value = [CPU]
        with self.assertRaises(RuntimeError):
            verify_engine(gpu, 'cuda')

    def test_invalid_mode(self):
        with self.assertRaises(ValueError):
            AdaptiveOCR('invalid')
