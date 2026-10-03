"""Independent numerical and information-boundary checks for the V2 workbench."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
import pipeline as p
from prepare_data import save

class NumericalChecks(unittest.TestCase):
    def test_hand_calculated_weighted_metrics_and_empty_subgroup(self):
        result = p.metrics([0, 2], [1, 0], [3, 1], ['a', 'b'])
        self.assertAlmostEqual(result['MAE_K'], 1.25)
        self.assertAlmostEqual(result['RMSE_K'], np.sqrt(1.75))
        self.assertAlmostEqual(result['bias_K'], .25)
        self.assertAlmostEqual(result['MSLE_log1p'], (3 * np.log(2)**2 + np.log(3)**2) / 4)
        self.assertEqual(result['subgroups']['positive_tc']['MAE_K'], 2)
        self.assertEqual(result['subgroups']['reported_zero']['MAE_K'], 1)
        self.assertIsNone(result['subgroups']['high_tc_ge40K']['MAE_K'])
        with self.assertRaises(ValueError):
            p.metrics([1], [1], [0])

    def test_train_only_imputation_and_constant_filtering(self):
        train = np.array([[1, np.nan, 7, np.nan], [3, 5, 7, np.nan], [5, 9, 7, np.nan]], float)
        fitted, state = p.fit_preprocessing(train, ['x', 'y', 'constant', 'missing'])
        self.assertEqual(state['medians'], [3, 7, 7, 0])
        self.assertEqual(state['missing_indicator_indices'], [1])
        self.assertEqual(state['kept_indices'], [0, 1, 4])
        held = p.transform([[999, np.nan, 1000, 10]], state)
        np.testing.assert_array_equal(held, [[999, 7, 1]])
        self.assertEqual(state['medians'], [3, 7, 7, 0])

    def test_target_inverse_clipping(self):
        np.testing.assert_array_equal(p.inverse_target([-2, 0, 3], 'raw'), [0, 0, 3])
        np.testing.assert_allclose(p.inverse_target([-2, 0, np.log(5)], 'log1p'), [0, 0, 4])

    def test_chemistry_routing_is_label_free_with_priority(self):
        frame = pd.DataFrame({'comp_fraction_Z029': [1, 0, 0], 'comp_fraction_Z008': [1, 0, 1], 'comp_fraction_Z026': [1, 1, 0], 'comp_fraction_Z033': [1, 1, 0], 'tc': [0, 2, 100]})
        np.testing.assert_array_equal(p.chemistry_routes(frame), ['cu_o', 'fe_anion', 'other'])
        changed = frame.assign(tc=[200, 0, 0], **{'class': ['anything']*3})
        np.testing.assert_array_equal(p.chemistry_routes(changed), p.chemistry_routes(frame))

    def test_expert_threshold_and_config_validation(self):
        self.assertTrue(p.eligible_expert(80, 12))
        self.assertFalse(p.eligible_expert(79, 12))
        self.assertFalse(p.eligible_expert(80, 11))
        spec = p.global_spec('composition', 'extra_trees', 'raw')
        p.validate_spec(spec)
        bad = dict(spec, input='tc')
        with self.assertRaises(ValueError):
            p.validate_spec(bad)
        with self.assertRaises(ValueError):
            p.validate_spec(dict(spec, experts={'other': spec['global']}))
        with self.assertRaises(ValueError):
            p.validate_spec(dict(spec, routing='chemistry'))
        with self.assertRaises(ValueError):
            p.validate_spec(dict(spec, global_config={'model': 'x'}))

    def test_cluster_relabeling_and_fold_only_scaler(self):
        self.assertEqual(p.cluster_mapping([30, 10, 20]), {1: 'cluster0', 2: 'cluster1', 0: 'cluster2'})
        self.assertEqual(p.cluster_mapping([10, 10, 20]), {0: 'cluster0', 1: 'cluster1', 2: 'cluster2'})
        frame = pd.DataFrame({'comp_Z_mean': [1, 2, 3, 10, 11, 12, 30, 31, 32], 'x': [1, 3, 2, 4, 6, 5, 7, 9, 8]})
        router = p.fit_router(frame, list(frame), 'kmeans3')
        np.testing.assert_allclose(router['scaler'].mean_, frame.mean().to_numpy())
        before = router['scaler'].mean_.copy()
        held = pd.DataFrame({'comp_Z_mean': [10000], 'x': [-2000]})
        self.assertEqual(len(p.route_labels(router, held)), 1)
        np.testing.assert_array_equal(router['scaler'].mean_, before)
        ordered = sorted(router['centroid_comp_Z_mean'])
        for original, z in enumerate(router['centroid_comp_Z_mean']):
            self.assertEqual(router['mapping'][original], 'cluster%d' % ordered.index(z))

    def test_both_estimators_and_targets_produce_finite_positive_predictions(self):
        x = np.column_stack([np.arange(60), np.sin(np.arange(60))])
        y = np.maximum(np.arange(60) - 10, 0)
        for model in p.MODELS:
            for target in p.TARGETS:
                bundle = p.fit_estimator(x, y, np.ones(60), ['x', 's'], {'model': model, 'target': target})
                pred = p.predict_estimator(bundle, x[[0, 30, 59]])
                self.assertTrue(np.isfinite(pred).all())
                self.assertTrue((pred >= 0).all())
                if model == 'hist_gradient_boosting':
                    self.assertFalse(bundle['estimator'].early_stopping)

    def test_small_expert_falls_back_to_global(self):
        n = 60
        frame = pd.DataFrame({'x': np.arange(n), 'comp_Z_mean': np.arange(n)+1, 'comp_fraction_Z029': np.ones(n), 'comp_fraction_Z008': np.ones(n), 'tc': np.arange(n), 'weight': np.ones(n), 'group': ['g%d' % (i//2) for i in range(n)]})
        schema = {'composition': ['x', 'comp_Z_mean', 'comp_fraction_Z029', 'comp_fraction_Z008'], 'inputs': {'composition': ['x', 'comp_Z_mean', 'comp_fraction_Z029', 'comp_fraction_Z008']}}
        spec = p.global_spec('composition', 'extra_trees', 'raw')
        spec['routing'] = 'chemistry'
        spec['experts'] = {'cu_o': {'model': 'hist_gradient_boosting', 'target': 'log1p'}}
        bundle = p.fit_pipeline(frame, schema, spec)
        self.assertEqual(bundle['fit_count'], 1)
        self.assertEqual(bundle['experts'], {})
        pred, routes, used = p.predict_pipeline(bundle, frame)
        np.testing.assert_array_equal(pred, p.predict_estimator(bundle['global'], frame[bundle['input_columns']].to_numpy()))
        self.assertTrue((used == 'global_fallback').all())

    def test_active_expert_fits_only_its_route_and_predicts_without_targets(self):
        n = 252
        first = np.arange(n) < 84
        second = (np.arange(n) >= 84) & (np.arange(n) < 168)
        frame = pd.DataFrame({'x': np.arange(n), 'comp_Z_mean': np.arange(n)+1, 'comp_fraction_Z029': first.astype(float), 'comp_fraction_Z008': first.astype(float),
                              'comp_fraction_Z026': second.astype(float), 'comp_fraction_Z033': second.astype(float), 'tc': np.arange(n), 'weight': np.ones(n), 'group': ['g%d' % (i//4) for i in range(n)], 'class': ['excluded']*n})
        names = ['x', 'comp_Z_mean', 'comp_fraction_Z029', 'comp_fraction_Z008', 'comp_fraction_Z026', 'comp_fraction_Z033']
        schema = {'composition': names, 'inputs': {'composition': names}}
        spec = p.global_spec('composition', 'extra_trees', 'raw')
        spec['routing'] = 'chemistry'
        spec['experts'] = {'cu_o': {'model': 'hist_gradient_boosting', 'target': 'raw'}}
        bundle = p.fit_pipeline(frame, schema, spec)
        self.assertEqual(bundle['fit_count'], 2)
        self.assertEqual(bundle['experts']['cu_o']['training_rows'], 84)
        self.assertEqual(bundle['experts']['cu_o']['preprocessing']['medians'][0], 41.5)
        self.assertEqual(bundle['global']['preprocessing']['medians'][0], 125.5)
        pred, routes, used = p.predict_pipeline(bundle, frame.drop(columns=['tc', 'weight', 'group', 'class']))
        self.assertTrue(np.isfinite(pred).all())
        self.assertEqual(int((used == 'expert_cu_o').sum()), 84)
        self.assertEqual(int((used == 'global_fallback').sum()), 168)

    def test_selection_tie_uses_intrinsic_fit_count_before_candidate_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            bench = p.Workbench(tmp)
            results = {'A01': {'metrics': {'MAE_K': 4.}, 'actual_model_fits': 9}, 'C01': {'metrics': {'MAE_K': 4.}, 'actual_model_fits': 3}, 'C02': {'metrics': {'MAE_K': 4.}, 'actual_model_fits': 3}}
            with patch.object(bench, '_result', side_effect=lambda cid: results[cid]):
                self.assertEqual(bench._winner(['A01', 'C02', 'C01']), 'C01')

    def test_feedback_does_not_open_validation_and_group_oof_covers_every_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'data').mkdir()
            n = 120
            frame = pd.DataFrame({'material_id': ['m%d' % i for i in range(n)], 'group': ['g%d' % (i//4) for i in range(n)], 'tc': np.maximum(np.arange(n)-20, 0), 'weight': np.ones(n), 'formula': ['X']*n, 'chemical_system': ['X']*n, 'x': np.arange(n), 'class': ['prohibited']*n})
            frame.to_csv(root / 'data/train.csv.gz', index=False)
            folds = np.array([(i//4)%3 for i in range(n)])
            pd.DataFrame({'material_id': frame.material_id, 'group': frame.group, 'fold': folds}).to_csv(root / 'data/fold_assignments.csv', index=False)
            save(root / 'data/schema.json', {'composition': ['x'], 'inputs': {'composition': ['x']}, 'excluded_predictor_metadata': ['tc', 'class']})
            save(root / 'data/data_audit.json', {'prepared_sha256': {}})
            original_reader = pd.read_csv
            def guarded_reader(path, *args, **kwargs):
                if 'validation' in str(path) or 'retrospective' in str(path):
                    raise AssertionError('Validation/test access during feedback')
                return original_reader(path, *args, **kwargs)
            with patch('pipeline.pd.read_csv', side_effect=guarded_reader):
                bench = p.Workbench(root)
                result = bench.run_strategy('A01', p.global_spec('composition', 'extra_trees', 'raw'))
                self.assertEqual(result['actual_model_fits'], 3)
                self.assertEqual(result['metrics']['rows'], n)
                self.assertEqual(len(bench.counterexamples('A01', 3)['examples']['overall']), 3)
            oof = original_reader(root / 'candidates/A01/oof_predictions.csv.gz')
            self.assertEqual(len(oof), n)
            self.assertTrue(oof.material_id.is_unique)
            self.assertTrue(np.isfinite(oof.prediction).all())
            self.assertEqual(oof.groupby('group').fold.nunique().max(), 1)

    def test_paired_bootstrap_hand_constant_difference(self):
        # Every group contributes exactly +1 error difference, hence every resample is +1.
        result = p.paired_bootstrap([0, 0, 0], [2, 2, 2], [1, 1, 1], [1, 2, 3], ['a', 'a', 'b'], 100)
        self.assertEqual(result['MAE_difference_K'], 1)
        self.assertEqual(result['conditional_95_percent_interval_K'], [1, 1])

if __name__ == '__main__':
    unittest.main(verbosity=2)
