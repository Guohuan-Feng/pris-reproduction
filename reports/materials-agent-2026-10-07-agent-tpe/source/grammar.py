"""One preregistered residual-program grammar shared by Agent and TPE."""
from __future__ import annotations
import hashlib
import json
import math

MECHANISMS = ['additive', 'oxygen_gated', 'all_interactions']
ALPHAS = [10, 30, 100, 300, 1000]
DEPTHS = [4, 5, 6, 7, 8]
ITERATIONS = [600, 900, 1200]
TRANSFORMS = ['identity', 'asinh']
LOSSES = ['RMSE', 'MAE']
KEYS = {'mechanism', 'trend_alpha', 'depth', 'iterations', 'learning_rate',
        'l2_leaf_reg', 'target_transform', 'input_width', 'loss_function'}
FIXED_C15 = {'mechanism': 'oxygen_gated', 'trend_alpha': 100, 'depth': 6,
             'iterations': 900, 'learning_rate': .04, 'l2_leaf_reg': 8.,
             'target_transform': 'identity', 'input_width': 66, 'loss_function': 'RMSE'}

def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)

def validate_config(config, allowed_widths):
    if not isinstance(config, dict) or set(config) != KEYS:
        raise ValueError('Supply exactly the nine registered grammar fields')
    c = dict(config)
    for key, values in [('mechanism', MECHANISMS), ('trend_alpha', ALPHAS), ('depth', DEPTHS),
                        ('iterations', ITERATIONS), ('target_transform', TRANSFORMS),
                        ('loss_function', LOSSES),
                        ('input_width', allowed_widths)]:
        if isinstance(c[key], bool) or c[key] not in values:
            raise ValueError('Field outside registered grammar: '+key)
    for key in ('trend_alpha', 'depth', 'iterations', 'input_width'):
        if not isinstance(c[key], int): raise ValueError('Integer categorical field required: '+key)
    for key, lo, hi in [('learning_rate', .025, .07), ('l2_leaf_reg', 3., 20.)]:
        value = c[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
            raise ValueError('Continuous grammar field outside bounds: '+key)
        c[key] = float(value)
    return c

def identity(config):
    return hashlib.sha256(canonical(config).encode('utf-8')).hexdigest()

def programme(config, allowed_widths=(66, 90)):
    c = validate_config(config, allowed_widths)
    products = '' if c['mechanism'] == 'additive' else (
        '    products = (composition[:, :, np.newaxis] * environment[:, np.newaxis, :]'+
        (' * (X[:, 17] > 0)[:, np.newaxis, np.newaxis]' if c['mechanism'] == 'oxygen_gated' else '')+
        ').reshape((X.shape[0], 104))\n')
    params = {'iterations': c['iterations'], 'depth': c['depth'], 'learning_rate': c['learning_rate'],
              'l2_leaf_reg': c['l2_leaf_reg'], 'loss_function': c['loss_function'], 'subsample': .85}
    return ('import numpy as np\n\ndef trend_basis(X, center, scale):\n'
            '    composition = X[:, 13:26]\n'
            '    environment = np.tanh((X[:, [42,43,48,49,54,55,60,61]] - center) / scale)\n'+products+
            '    return np.concatenate((composition, environment'+(', products' if products else '')+'), axis=1)\n\n'
            'def fit(X_train,y_train):\n'
            '    environment = X_train[:, [42,43,48,49,54,55,60,61]]\n'
            '    center = np.mean(environment, axis=0)\n'
            '    scale = np.maximum(np.std(environment, axis=0), 1e-8)\n'
            '    basis = trend_basis(X_train, center, scale)\n'
            '    target = '+('np.sign(y_train) * np.log1p(np.abs(y_train) + y_train*y_train / (1.0 + np.sqrt(1.0 + y_train*y_train)))' if c['target_transform'] == 'asinh' else 'y_train')+'\n'
            '    trend = train_model("ridge", basis, target, {"alpha": '+repr(float(c['trend_alpha']))+'})\n'
            '    residual = target - trend.predict(basis)\n'
            '    nonlinear = train_model("catboost", X_train, residual, '+repr(params)+')\n'
            '    return (trend, nonlinear, center, scale)\n\n'
            'def predict(state,X_eval):\n'
            '    trend, nonlinear, center, scale = state\n'
            '    basis = trend_basis(X_eval, center, scale)\n'
            '    branch = trend.predict(basis) + nonlinear.predict(X_eval)\n'
            '    return '+('0.5 * (np.expm1(branch) - np.expm1(-branch))' if c['target_transform'] == 'asinh' else 'branch')+'\n')

def suggest(trial, allowed_widths):
    return validate_config({'mechanism': trial.suggest_categorical('mechanism', MECHANISMS),
        'trend_alpha': trial.suggest_categorical('trend_alpha', ALPHAS),
        'depth': trial.suggest_categorical('depth', DEPTHS),
        'iterations': trial.suggest_categorical('iterations', ITERATIONS),
        'learning_rate': trial.suggest_float('learning_rate', .025, .07, log=True),
        'l2_leaf_reg': trial.suggest_float('l2_leaf_reg', 3., 20., log=True),
        'target_transform': trial.suggest_categorical('target_transform', TRANSFORMS),
        'loss_function': trial.suggest_categorical('loss_function', LOSSES),
        'input_width': trial.suggest_categorical('input_width', list(allowed_widths))}, allowed_widths)
