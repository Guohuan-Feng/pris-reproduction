"""Resource-bounded invented-array dry run of an Agent predictor program.

Every estimator and standardizer is replaced by arithmetic mocks in an isolated
child. This checks API use, fit counts, shape, finite output, train/evaluation
separation, and inference probes; it is not performance evaluation, and does not
prove that a program will work for every distribution or actual sklearn model.
"""
from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
import numpy as np
import predictor_runtime as runtime

ROOT = Path(__file__).resolve().parent


def invented_arrays(n_features):
    """Deterministic invented floats only; never reads a materials row or label."""
    row = np.arange(320, dtype=float)[:, None]
    column = np.arange(n_features, dtype=float)[None, :]
    train = np.sin((row + 1) * (column + 1) / 43) + (column + 1) / 100
    train[:160, 17] = 0.0
    train[160:, 17] = .2
    eval_rows = np.arange(19, dtype=float)[:, None]
    evaluate = np.cos((eval_rows + 2) * (column + 1) / 29) + (column + 1) / 100
    evaluate[:9, 17] = 0.0
    evaluate[9:, 17] = .3
    target = np.sin(np.arange(320, dtype=float) / 17) - .7
    return train, target, evaluate


def _worker():
    """Only this child imports/patches model factories; parent science is untouched."""
    import sklearn.ensemble as ensemble
    import sklearn.linear_model as linear
    import sklearn.kernel_ridge as kernel
    import sklearn.preprocessing as preprocessing
    payload = json.load(sys.stdin)
    X, y, E = invented_arrays(payload['n_features'])
    mock_calls = []

    class ArithmeticLearner:
        def __init__(self, **params):
            self.parameters = params
        def fit(self, values, target):
            # This is invented-array arithmetic, never an actual learner fit.
            values = np.asarray(values, float)
            target = np.asarray(target, float)
            self.feature_count = values.shape[1]
            self.offset = float(np.mean(target))
            mock_calls.append({'rows': len(target), 'features': values.shape[1], 'parameters': self.parameters})
            return self
        def predict(self, values):
            values = np.asarray(values, float)
            if values.ndim != 2 or values.shape[1] != self.feature_count:
                raise ValueError('Synthetic model feature width mismatch')
            return self.offset + .01 * np.sum(values, axis=1)

    class ArithmeticScaler:
        def fit(self, values):
            values = np.asarray(values, float)
            self.mean = np.mean(values, axis=0)
            self.scale = np.std(values, axis=0)
            self.scale[self.scale == 0] = 1
            return self
        def transform(self, values):
            return (np.asarray(values, float) - self.mean) / self.scale

    ensemble.ExtraTreesRegressor = ArithmeticLearner
    ensemble.HistGradientBoostingRegressor = ArithmeticLearner
    linear.Ridge = ArithmeticLearner
    kernel.KernelRidge = ArithmeticLearner
    preprocessing.StandardScaler = ArithmeticScaler
    worker_payload = {'code': payload['code'], 'X_train': X.tolist(), 'y_train': y.tolist(),
                      'X_eval': E.tolist(), 'max_fits': payload['max_fits_per_block'],
                      'event_path': payload['event_path'], 'block_id': 'synthetic_preflight'}
    original_stdin = sys.stdin
    captured = io.StringIO()
    started = time.perf_counter()
    try:
        sys.stdin = io.StringIO(json.dumps(worker_payload, allow_nan=False))
        with redirect_stdout(captured):
            runtime._worker()
        response = json.loads(captured.getvalue())
        result = {'accepted': True, 'mock_learner_fit_started': response['fit_started'],
                  'mock_learner_fit_completed': response['fit_completed'],
                  'mock_factory_fit_calls': len(mock_calls),
                  'inference_independence_probes': response['inference_independence_checks'],
                  'prediction_shape': [len(response['prediction'])],
                  'prediction_finite': bool(np.isfinite(response['prediction']).all()),
                  'mock_calls': mock_calls, 'worker_seconds': time.perf_counter() - started}
        if response['fit_started'] != response['fit_completed'] or response['fit_completed'] != len(mock_calls):
            raise RuntimeError('Synthetic learner count mismatch')
    except Exception as exc:
        events = []
        path = Path(payload['event_path'])
        if path.exists():
            events = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        result = {'accepted': False, 'error': f'{type(exc).__name__}: {exc}'[:2000],
                  'mock_learner_fit_started': sum(e.get('phase') == 'started' for e in events),
                  'mock_learner_fit_completed': sum(e.get('phase') == 'completed' for e in events),
                  'mock_factory_fit_calls': len(mock_calls),
                  'worker_seconds': time.perf_counter() - started}
    finally:
        sys.stdin = original_stdin
    result.update(scientific_fits=0, actual_LLM_calls=0, input_kind='Invented deterministic arrays and targets only')
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


def validate_program_synthetic(code, max_fits_per_block, n_features, *, timeout_s=20, memory_mb=2048):
    """Return a bounded preflight receipt. Rejection never consumes science fits."""
    if not isinstance(n_features, int) or isinstance(n_features, bool) or not 42 <= n_features <= 160:
        raise ValueError('Synthetic feature width must be an integer between 42 and 160')
    if not isinstance(timeout_s, (int, float)) or isinstance(timeout_s, bool) or not math.isfinite(timeout_s) or not 1 <= timeout_s <= 30:
        raise ValueError('Synthetic worker timeout must be between 1 and 30 seconds')
    if not isinstance(memory_mb, int) or isinstance(memory_mb, bool) or not 128 <= memory_mb <= 2048:
        raise ValueError('Synthetic worker memory must be between 128 and 2048 MiB')
    receipt = {'schema_version': 1, 'scientific_fits': 0, 'actual_LLM_calls': 0,
               'n_features': n_features, 'max_fits_per_block': max_fits_per_block,
               'scope': 'Invented-array dry run with arithmetic model mocks; no scientific performance result',
               'limitations': 'Synthetic input routes may differ from real data. Inference checks are probes, not a universal proof.',
               'timeout_seconds': timeout_s, 'memory_mb': memory_mb}
    try:
        receipt['AST_validation'] = runtime.validate_predictor(code, max_fits_per_block)
        receipt['code_sha256'] = runtime.code_sha(code)
    except Exception as exc:
        return {**receipt, 'accepted': False, 'stage': 'AST', 'error': f'{type(exc).__name__}: {exc}'[:2000],
                'mock_learner_fit_started': 0, 'mock_learner_fit_completed': 0}
    environment = {k: os.environ[k] for k in ('SystemRoot', 'WINDIR', 'TEMP', 'TMP', 'PATH') if k in os.environ}
    environment.update(PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', OMP_NUM_THREADS='1',
                       OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')
    scientific_site = str(Path(np.__file__).resolve().parent.parent)
    script = str(Path(__file__).resolve())
    bootstrap = ('import sys,runpy;sys.path.insert(0,' + repr(scientific_site) + ');sys.path.insert(0,'
                 + repr(str(ROOT)) + ');sys.argv=[' + repr(script) + ',"--worker"];runpy.run_path('
                 + repr(script) + ',run_name="__main__")')
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='materials_predictor_synthetic_') as temporary:
        event_path = Path(temporary) / 'mock_fit_events.jsonl'
        payload = json.dumps({'code': code, 'max_fits_per_block': max_fits_per_block,
                              'n_features': n_features, 'event_path': str(event_path)}, allow_nan=False).encode('utf-8')
        kwargs = {'stdin': subprocess.PIPE, 'stdout': subprocess.PIPE, 'stderr': subprocess.PIPE,
                  'env': environment, 'cwd': str(ROOT)}
        if os.name == 'nt':
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        else:
            kwargs['preexec_fn'] = runtime.guard._posix_preexec(memory_mb, timeout_s)
        process = subprocess.Popen([getattr(sys, '_base_executable', None) or sys.executable,
                                    '-I', '-B', '-X', 'utf8', '-c', bootstrap], **kwargs)
        job = None
        try:
            if os.name == 'nt':
                job = runtime.guard._WindowsJob(process, memory_mb, timeout_s)
            try:
                output, error = process.communicate(payload, timeout=timeout_s)
            except subprocess.TimeoutExpired:
                if job:
                    job.close()
                process.kill()
                process.communicate(timeout=10)
                return {**receipt, 'accepted': False, 'stage': 'resource',
                        'error': 'Synthetic program timed out; zero scientific fits',
                        'wall_seconds': time.perf_counter() - started}
            if process.returncode != 0 or len(output) > 2 * 1024 ** 2 or len(error) > 128 * 1024:
                return {**receipt, 'accepted': False, 'stage': 'worker',
                        'error': f'Synthetic worker exited {process.returncode}: ' + error.decode('utf-8', errors='replace')[-2000:],
                        'wall_seconds': time.perf_counter() - started}
            response = json.loads(output.decode('utf-8'))
            events = [json.loads(line) for line in event_path.read_text(encoding='utf-8').splitlines()] if event_path.exists() else []
            if response.get('scientific_fits') != 0 or response.get('actual_LLM_calls') != 0:
                raise RuntimeError('Synthetic worker receipt mismatch')
            return {**receipt, **response, 'mock_fit_events': events, 'stage': 'synthetic_execution',
                    'wall_seconds': time.perf_counter() - started}
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
            if job:
                job.close()


if __name__ == '__main__' and '--worker' in sys.argv:
    _worker()
