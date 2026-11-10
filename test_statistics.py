import math
import unittest

from statistics_engine import calculate, parse_text, validate_dataset


def raw(values):
    return {'kind': 'raw', 'columns': ['Value'], 'rows': [[v] for v in values]}


class StatisticalTests(unittest.TestCase):
    def values(self, values, settings=None):
        return calculate(raw(values), settings)['results']

    def test_reference_experiment(self):
        results = self.values([10, 20, 30, 40, 50])
        for key, expected in {'count':5, 'sum':150, 'minimum':10, 'maximum':50, 'range':40,
                              'mean':30, 'median':30, 'midrange':30, 'population_variance':200,
                              'sample_variance':250, 'population_std':math.sqrt(200), 'sample_std':math.sqrt(250),
                              'q1':20, 'q2':30, 'q3':40, 'iqr':20, 'mean_absolute_deviation':12,
                              'median_absolute_deviation':10, 'standard_error':math.sqrt(50)}.items():
            with self.subTest(key=key):
                self.assertAlmostEqual(results[key], expected, places=10)

    def test_even_median(self):
        self.assertEqual(self.values([1, 2, 3, 4])['median'], 2.5)

    def test_multimodal(self):
        self.assertEqual(self.values([1, 1, 2, 2, 3])['mode'], [1, 2])

    def test_unique_values_have_no_mode(self):
        result = calculate(raw([1, 2, 3]))
        self.assertIsNone(result['results']['mode'])
        self.assertIn('mode', result['issues'])

    def test_quantile_type_seven(self):
        results = self.values([1, 2, 3, 4], {'percentiles':[0,10,25,50,75,100]})
        self.assertEqual(results['q1'], 1.75)
        self.assertEqual(results['q3'], 3.25)
        self.assertEqual(results['iqr'], 1.5)
        self.assertAlmostEqual(results['percentiles']['10.0'], 1.3)
        self.assertEqual(results['percentiles']['0.0'], 1)
        self.assertEqual(results['percentiles']['100.0'], 4)

    def test_bias_corrected_skewness(self):
        self.assertAlmostEqual(self.values([1, 1, 2])['skewness'], math.sqrt(3))
        self.assertAlmostEqual(self.values([1, 2, 3, 4])['skewness'], 0)

    def test_bias_corrected_kurtosis(self):
        self.assertAlmostEqual(self.values([1, 2, 3, 4])['excess_kurtosis'], -1.2)

    def test_population_zscores(self):
        results = self.values([10, 20, 30, 40, 50])
        self.assertAlmostEqual(results['zscores'][0], -math.sqrt(2))
        self.assertEqual(results['zscores'][2], 0)

    def test_single_value(self):
        results = self.values([8])
        for key in ('sample_variance', 'sample_std', 'skewness', 'excess_kurtosis', 'standard_error'):
            self.assertIsNone(results[key])
        self.assertEqual(results['population_variance'], 0)
        self.assertEqual(results['median'], 8)

    def test_identical_values(self):
        results = self.values([3, 3, 3, 3])
        self.assertEqual(results['population_std'], 0)
        self.assertEqual(results['sample_std'], 0)
        self.assertEqual(results['mode'], [3])
        for key in ('zscores', 'z_outliers', 'skewness', 'excess_kurtosis'):
            self.assertIsNone(results[key])

    def test_zero_mean_and_nonpositive_means(self):
        results = self.values([-1, 0, 1])
        for key in ('coefficient_of_variation', 'geometric_mean', 'harmonic_mean'):
            self.assertIsNone(results[key])
        self.assertEqual(results['mean'], 0)

    def test_negative_values(self):
        self.assertEqual(self.values([-5, -3, -1])['mean'], -3)

    def test_decimal_values(self):
        self.assertAlmostEqual(self.values([0.1, 0.2, 0.3])['mean'], 0.2)
        self.assertAlmostEqual(self.values([0.1, 0.2, 0.3])['population_variance'], 1/150)

    def test_geometric_and_harmonic(self):
        results = self.values([1, 2, 4])
        self.assertAlmostEqual(results['geometric_mean'], 2)
        self.assertAlmostEqual(results['harmonic_mean'], 12/7)

    def test_weighted_mean(self):
        self.assertAlmostEqual(self.values([1, 2, 4], {'weights':[1,1,2]})['weighted_mean'], 2.75)

    def test_invalid_weights(self):
        for weights in ([1], [0,0], [-1,2], [math.inf,1], 'bad'):
            with self.subTest(weights=weights), self.assertRaises(ValueError):
                self.values([1,2], {'weights':weights})

    def test_empty_and_invalid(self):
        for values in ([], ['bad'], [math.nan], [math.inf], [True], [1e101]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.values(values)

    def test_missing_reject_and_drop(self):
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.values([1, None, 3])
        result = calculate(raw([1, None, 3]), {'missing':'drop', 'weights':[1,999,3]})
        self.assertEqual(result['results']['mean'], 2)
        self.assertEqual(result['results']['weighted_mean'], 2.5)
        self.assertEqual(result['summary']['excluded_rows'], 1)
        with self.assertRaises(ValueError):
            self.values([None, None], {'missing':'drop'})

    def test_manual_separators(self):
        self.assertEqual(parse_text('1, 2\n3\t4 5'), [1,2,3,4,5])
        for text in ('', '1,,2', '1,', ',1', 'a', 'nan', '1, \n, 2'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_text(text)

    def test_iqr_outlier(self):
        self.assertEqual(self.values([1,2,3,4,100])['iqr_outliers'], [100])

    def test_zscore_outlier(self):
        self.assertEqual(self.values([0]*20+[100])['z_outliers'], [100])

    def test_frequency(self):
        result = self.values([2,1,2])['frequency']
        self.assertEqual(result[0], {'value':1,'frequency':1,'relative':1/3,'cumulative':1})
        self.assertEqual(result[1]['cumulative'], 3)

    def test_pearson_regression(self):
        dataset = {'columns':['X','Y'], 'rows':[[1,3],[2,5],[3,7]]}
        result = calculate(dataset, {'y_column':1})['results']
        self.assertAlmostEqual(result['pearson'], 1)
        self.assertAlmostEqual(result['spearman'], 1)
        self.assertAlmostEqual(result['regression']['slope'], 2)
        self.assertAlmostEqual(result['regression']['intercept'], 1)
        self.assertAlmostEqual(result['regression']['r_squared'], 1)

    def test_spearman_average_ties(self):
        dataset = {'columns':['X','Y'], 'rows':[[1,1],[1,2],[2,3]]}
        self.assertAlmostEqual(calculate(dataset, {'y_column':1})['results']['spearman'], math.sqrt(0.75))

    def test_paired_missing_and_constant(self):
        dataset = {'columns':['X','Y'], 'rows':[[1,2],[2,None],[3,6]]}
        result = calculate(dataset, {'y_column':1, 'missing':'drop'})
        self.assertEqual(result['summary']['count'], 2)
        self.assertAlmostEqual(result['results']['pearson'], 1)
        result = calculate({'columns':['X','Y'], 'rows':[[1,2],[1,3]]}, {'y_column':1})
        self.assertIsNone(result['results']['pearson'])
        self.assertIsNone(result['results']['regression'])

    def test_constant_y_regression(self):
        result = calculate({'columns':['X','Y'], 'rows':[[1,2],[2,2]]}, {'y_column':1})['results']
        self.assertEqual(result['regression']['slope'], 0)
        self.assertIsNone(result['regression']['r_squared'])

    def test_grouped_exact_frequency(self):
        dataset = {'kind':'frequency', 'columns':['Value','Frequency'], 'rows':[[10,2],[20,5],[30,3]]}
        result = calculate(dataset)
        self.assertEqual(result['results']['mean'], 21)
        self.assertEqual(result['results']['count'], 10)
        self.assertFalse(result['summary']['estimated'])

    def test_class_interval_estimates(self):
        result = calculate({'kind':'interval','columns':['Lower','Upper','Frequency'],'rows':[[10,20,2],[20,30,3]]})
        self.assertEqual(result['results']['mean'], 21)
        self.assertTrue(result['summary']['estimated'])

    def test_invalid_grouped_data(self):
        for rows in ([[10,-1]], [[10,1.5]], [[10,0]], [[10,10001]], [[10,None]]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                calculate({'kind':'frequency','columns':['V','F'],'rows':rows})
        with self.assertRaises(ValueError):
            calculate({'kind':'interval','columns':['L','U','F'],'rows':[[10,20,2],[15,25,3]]})

    def test_settings_and_limits(self):
        for settings in ({'column':5}, {'column':False}, {'missing':'ignore'}, {'statistics':[]}, {'statistics':['made_up']}, {'percentiles':[-1]}, {'percentiles':[101]}, {'y_column':0}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                self.values([1,2], settings)
        with self.assertRaises(ValueError):
            validate_dataset({'columns':['a','a'],'rows':[[1,2]]})
        with self.assertRaises(ValueError):
            validate_dataset(raw([1]*10001))

    def test_selected_statistics_and_finite_large_values(self):
        result = self.values([-1e100,0,1e100], {'statistics':['mean','population_variance']})
        self.assertEqual(set(result), {'mean','population_variance'})
        self.assertTrue(math.isfinite(result['population_variance']))


if __name__ == '__main__':
    unittest.main()
