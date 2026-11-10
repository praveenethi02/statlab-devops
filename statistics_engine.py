"""Deterministic descriptive statistics, without optional numerical dependencies."""
import math
import re
import statistics as st
from collections import Counter

ALGORITHM_VERSION = '1.0.0'
MAX_ROWS = 10_000
MAX_COLUMNS = 32
MAX_CELLS = 100_000
CONVENTIONS = {
    'quantiles': 'Hyndman-Fan type 7: linear interpolation at (n-1)*p; endpoints included.',
    'skewness': 'Adjusted Fisher-Pearson sample skewness (n >= 3).',
    'kurtosis': 'Bias-corrected Fisher excess kurtosis (n >= 4); normal distribution = 0.',
    'cv': 'Sample standard deviation / absolute mean * 100; undefined for zero mean.',
    'zscores': 'Population standard deviation; Z outliers use |z| > 3.',
    'missing': 'Reject missing selected values by default; drop policy removes rows explicitly.',
    'grouped': 'Value frequencies are exact; class intervals use midpoints and are estimates.',
}

# name, section, formula, interpretation
METRICS = {
    'count': ('Count', 'Descriptive Statistics', 'N', 'Number of included observations.'),
    'sum': ('Sum', 'Descriptive Statistics', 'Σx', 'Total of all included values.'),
    'minimum': ('Minimum', 'Descriptive Statistics', 'min(x)', 'Smallest observation.'),
    'maximum': ('Maximum', 'Descriptive Statistics', 'max(x)', 'Largest observation.'),
    'range': ('Range', 'Descriptive Statistics', 'max(x) − min(x)', 'Distance between the extremes.'),
    'mean': ('Arithmetic mean', 'Measures of Central Tendency', 'Σx / N', 'Average observation.'),
    'median': ('Median', 'Measures of Central Tendency', 'P50', 'Middle value; interpolated for even counts.'),
    'mode': ('Mode', 'Measures of Central Tendency', 'argmax frequency(x)', 'All most frequent values; undefined when all values occur once.'),
    'midrange': ('Midrange', 'Measures of Central Tendency', '(min + max) / 2', 'Midpoint of the extremes.'),
    'population_variance': ('Population variance', 'Measures of Dispersion', 'Σ(x − μ)² / N', 'Variance treating observations as the population.'),
    'sample_variance': ('Sample variance', 'Measures of Dispersion', 'Σ(x − x̄)² / (n − 1)', 'Unbiased sample variance; requires two observations.'),
    'population_std': ('Population standard deviation', 'Measures of Dispersion', '√population variance', 'Population spread in the original units.'),
    'sample_std': ('Sample standard deviation', 'Measures of Dispersion', '√sample variance', 'Sample spread; requires two observations.'),
    'mean_absolute_deviation': ('Mean absolute deviation', 'Measures of Dispersion', 'mean(|x − mean(x)|)', 'Average absolute distance from the mean.'),
    'median_absolute_deviation': ('Median absolute deviation', 'Measures of Dispersion', 'median(|x − median(x)|)', 'Unscaled robust spread about the median.'),
    'iqr': ('Interquartile range', 'Measures of Dispersion', 'Q3 − Q1', 'Spread of the middle half of the data.'),
    'coefficient_of_variation': ('Coefficient of variation (%)', 'Measures of Dispersion', '100 × s / |x̄|', 'Relative sample spread; undefined at mean zero.'),
    'q1': ('First quartile', 'Measures of Position', 'P25 (type 7)', '25th percentile.'),
    'q2': ('Second quartile', 'Measures of Position', 'P50 (type 7)', '50th percentile.'),
    'q3': ('Third quartile', 'Measures of Position', 'P75 (type 7)', '75th percentile.'),
    'percentiles': ('Percentiles', 'Measures of Position', 'x[j] + (h−j)(x[j+1]−x[j]); h=(n−1)p', 'Requested percentile positions, using linear interpolation.'),
    'deciles': ('Deciles', 'Measures of Position', 'P10, P20, …, P90', 'Nine equally spaced percentile positions.'),
    'zscores': ('Z-scores', 'Measures of Position', '(x − μ) / σ', 'Population-standardized observations, in input order.'),
    'five_number_summary': ('Five-number summary', 'Measures of Position', 'min, Q1, median, Q3, max', 'Extremes and quartiles.'),
    'skewness': ('Sample skewness', 'Distribution Characteristics', '√(n(n−1))/(n−2) × m3/m2^(3/2)', 'Bias-corrected asymmetry; undefined for constant data or n < 3.'),
    'excess_kurtosis': ('Sample excess kurtosis', 'Distribution Characteristics', '(n−1)/((n−2)(n−3)) × ((n+1)g2 + 6)', 'Bias-corrected excess; g2=m4/m2²−3. Requires n >= 4 and spread.'),
    'standard_error': ('Standard error of the mean', 'Distribution Characteristics', 's / √n', 'Estimated sampling error using sample standard deviation.'),
    'iqr_outliers': ('IQR outliers', 'Distribution Characteristics', 'x < Q1−1.5 IQR or x > Q3+1.5 IQR', 'Observations beyond the Tukey fences.'),
    'z_outliers': ('Z-score outliers', 'Distribution Characteristics', '|z| > 3', 'Observations over three population standard deviations away.'),
    'frequency': ('Frequency distribution', 'Additional Analysis', 'f, f/N, cumulative f', 'Exact values with absolute, relative, and cumulative frequencies.'),
    'geometric_mean': ('Geometric mean', 'Additional Analysis', 'exp(mean(log(x)))', 'Multiplicative average; requires strictly positive values.'),
    'harmonic_mean': ('Harmonic mean', 'Additional Analysis', 'N / Σ(1/x)', 'Reciprocal average; requires strictly positive values.'),
    'weighted_mean': ('Weighted mean', 'Additional Analysis', 'Σ(w x) / Σw', 'Requires one nonnegative weight per included observation and positive total weight.'),
    'pearson': ('Pearson correlation', 'Additional Analysis', 'cov(x,y) / (sx sy)', 'Linear association for paired observations; both columns must vary.'),
    'spearman': ('Spearman correlation', 'Additional Analysis', 'Pearson(rank(x), rank(y))', 'Rank correlation with average ranks for ties.'),
    'regression': ('Simple linear regression', 'Additional Analysis', 'y = intercept + slope × x', 'Ordinary least squares; includes R². Requires varying x.'),
}


def number(value):
    if isinstance(value, bool) or value is None or isinstance(value, (dict, list)):
        raise ValueError('Enter a finite numerical value.')
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f'Invalid numerical value: {str(value)[:60]}') from exc
    if not math.isfinite(result) or abs(result) > 1e100 or (result != 0 and abs(result) < 1e-100):
        raise ValueError('Values must be finite; nonzero magnitudes must be between 1e-100 and 1e100.')
    return result


def parse_text(text):
    if not isinstance(text, str) or len(text) > 1_000_000:
        raise ValueError('Numerical text must be at most 1 MB.')
    if not text.strip():
        raise ValueError('Enter at least one observation.')
    if any(not part.strip() for part in text.split(',')):
        raise ValueError('A comma-delimited value is missing. Fill or remove the empty cell.')
    parts = re.split(r'[,\s]+', text.strip())
    if len(parts) > MAX_ROWS:
        raise ValueError(f'At most {MAX_ROWS:,} observations are allowed.')
    return [number(part) for part in parts]


def quantile(sorted_values, percentile):
    p = number(percentile)
    if not 0 <= p <= 100:
        raise ValueError('Percentiles must be between 0 and 100.')
    h = (len(sorted_values) - 1) * p / 100
    j = math.floor(h)
    return sorted_values[j] + (h - j) * (sorted_values[min(j + 1, len(sorted_values) - 1)] - sorted_values[j])


def validate_dataset(data):
    if not isinstance(data, dict):
        raise ValueError('A dataset object is required.')
    kind = data.get('kind', 'raw')
    if kind not in ('raw', 'frequency', 'interval'):
        raise ValueError('Dataset kind must be raw, frequency, or interval.')
    columns, rows = data.get('columns'), data.get('rows')
    if not isinstance(columns, list) or not 1 <= len(columns) <= MAX_COLUMNS:
        raise ValueError(f'Provide 1–{MAX_COLUMNS} column names.')
    if any(not isinstance(c, str) or not c.strip() or len(c) > 80 for c in columns):
        raise ValueError('Column names must contain 1–80 characters.')
    columns = [c.strip() for c in columns]
    if len(set(columns)) != len(columns):
        raise ValueError('Column names must be unique.')
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS or len(rows) * len(columns) > MAX_CELLS:
        raise ValueError('Provide 1–10,000 rows and at most 100,000 cells.')
    cleaned = []
    for i, row in enumerate(rows):
        if not isinstance(row, list) or len(row) != len(columns):
            raise ValueError(f'Row {i+1} does not match the column count.')
        cells = []
        for value in row:
            if value is None or value == '':
                cells.append(None)
            elif isinstance(value, str):
                if len(value) > 500:
                    raise ValueError('Cells must be at most 500 characters.')
                cells.append(value.strip() or None)
            else:
                cells.append(number(value))
        cleaned.append(cells)
    output = {'kind': kind, 'columns': columns, 'rows': cleaned}
    if kind != 'raw':
        grouped_values(output)
    return output


def grouped_values(dataset):
    kind = dataset['kind']
    expected = 2 if kind == 'frequency' else 3
    if len(dataset['columns']) != expected:
        raise ValueError('Frequency data needs value/frequency columns; intervals need lower/upper/frequency columns.')
    values, previous_upper = [], None
    for i, row in enumerate(dataset['rows']):
        parsed = [number(v) for v in row]
        frequency = parsed[-1]
        if frequency < 0 or not frequency.is_integer() or frequency > MAX_ROWS:
            raise ValueError(f'Row {i+1}: frequency must be a nonnegative integer at most {MAX_ROWS}.')
        if kind == 'interval':
            lower, upper = parsed[:2]
            if lower >= upper or (previous_upper is not None and lower < previous_upper):
                raise ValueError('Intervals must be ordered, nonoverlapping, and have lower < upper.')
            previous_upper = upper
            value = lower + (upper - lower) / 2
        else:
            value = parsed[0]
        if len(values) + int(frequency) > MAX_ROWS:
            raise ValueError('Total frequency may not exceed 10,000.')
        values.extend([value] * int(frequency))
    if not values:
        raise ValueError('At least one positive frequency is required.')
    return values


def ranks(values):
    ordered = sorted(enumerate(values), key=lambda pair: pair[1])
    output, i = [0.0] * len(values), 0
    while i < len(ordered):
        j = i + 1
        while j < len(ordered) and ordered[j][1] == ordered[i][1]:
            j += 1
        for position in range(i, j):
            output[ordered[position][0]] = (i + j + 1) / 2
        i = j
    return output


def paired_stats(x, y):
    mx, my = st.fmean(x), st.fmean(y)
    sx, sy = st.pstdev(x), st.pstdev(y)
    r = None
    if len(x) > 1 and sx > 0 and sy > 0:
        r = max(-1.0, min(1.0, st.fmean(((a-mx)/sx)*((b-my)/sy) for a, b in zip(x, y))))
    regression = None
    if len(x) > 1 and sx > 0:
        slope = st.fmean(((a-mx)/sx)*(b-my) for a, b in zip(x, y)) / sx
        regression = {'slope': slope, 'intercept': my-slope*mx, 'r_squared': r*r if r is not None else None}
    return r, regression


def calculate(dataset, settings=None):
    dataset = validate_dataset(dataset)
    settings = {} if settings is None else settings
    if not isinstance(settings, dict):
        raise ValueError('Calculation settings must be an object.')
    policy = settings.get('missing', 'reject')
    if policy not in ('reject', 'drop'):
        raise ValueError('Missing-value policy must be reject or drop.')
    column = settings.get('column', 0)
    ycolumn = settings.get('y_column')
    if type(column) is not int or not 0 <= column < len(dataset['columns']):
        raise ValueError('Select a valid numerical column.')
    if ycolumn is not None and (type(ycolumn) is not int or not 0 <= ycolumn < len(dataset['columns']) or ycolumn == column):
        raise ValueError('Select a different valid second column.')
    if dataset['kind'] != 'raw' and (ycolumn is not None or settings.get('weights') is not None):
        raise ValueError('Paired and weighted workflows require raw numerical data.')
    values, ys, included, excluded = [], [], [], 0
    if dataset['kind'] != 'raw':
        values = grouped_values(dataset)
    else:
        for i, row in enumerate(dataset['rows']):
            selected = [row[column]] + ([row[ycolumn]] if ycolumn is not None else [])
            if any(v is None for v in selected):
                if policy == 'reject':
                    raise ValueError(f'Row {i+1} has a missing selected value. Correct it or choose Drop missing rows.')
                excluded += 1
                continue
            try:
                values.append(number(selected[0]))
                if ycolumn is not None:
                    ys.append(number(selected[1]))
            except ValueError as exc:
                raise ValueError(f'Row {i+1}: {exc}') from exc
            included.append(i)
    if not values:
        raise ValueError('No numerical observations remain for calculation.')
    n, ordered, counts = len(values), sorted(values), Counter(values)
    mean, median = st.fmean(values), st.median(values)
    pv, ps = st.pvariance(values), st.pstdev(values)
    sv, ss = (st.variance(values), st.stdev(values)) if n > 1 else (None, None)
    q1, q3 = quantile(ordered, 25), quantile(ordered, 75)
    iqr = q3 - q1
    max_frequency = max(counts.values())
    zscores = [(v-mean)/ps for v in values] if ps > 0 else None
    percentiles = settings.get('percentiles', [5, 25, 50, 75, 95])
    if not isinstance(percentiles, list) or not 1 <= len(percentiles) <= 100:
        raise ValueError('Choose 1–100 percentile positions.')
    positive = min(values) > 0
    results = {
        'count': n, 'sum': math.fsum(values), 'minimum': ordered[0], 'maximum': ordered[-1],
        'range': ordered[-1]-ordered[0], 'mean': mean, 'median': median,
        'mode': sorted(v for v, f in counts.items() if f == max_frequency) if max_frequency > 1 else None,
        'midrange': (ordered[0]+ordered[-1])/2,
        'population_variance': pv, 'sample_variance': sv, 'population_std': ps, 'sample_std': ss,
        'mean_absolute_deviation': st.fmean(abs(v-mean) for v in values),
        'median_absolute_deviation': st.median(abs(v-median) for v in values),
        'iqr': iqr, 'coefficient_of_variation': ss/abs(mean)*100 if ss is not None and mean != 0 else None,
        'q1': q1, 'q2': median, 'q3': q3,
        'percentiles': {str(number(p)): quantile(ordered, p) for p in percentiles},
        'deciles': {str(p): quantile(ordered, p) for p in range(10, 100, 10)},
        'zscores': zscores, 'five_number_summary': [ordered[0], q1, median, q3, ordered[-1]],
        'skewness': math.sqrt(n*(n-1))/(n-2)*st.fmean(z**3 for z in zscores) if n >= 3 and zscores is not None else None,
        'excess_kurtosis': (n-1)/((n-2)*(n-3))*((n+1)*(st.fmean(z**4 for z in zscores)-3)+6) if n >= 4 and zscores is not None else None,
        'standard_error': ss/math.sqrt(n) if ss is not None else None,
        'iqr_outliers': [v for v in values if v < q1-1.5*iqr or v > q3+1.5*iqr],
        'z_outliers': [v for v, z in zip(values, zscores) if abs(z) > 3] if zscores is not None else None,
        'geometric_mean': math.exp(st.fmean(math.log(v) for v in values)) if positive else None,
        'harmonic_mean': st.harmonic_mean(values) if positive else None,
        'weighted_mean': None, 'pearson': None, 'spearman': None, 'regression': None,
    }
    cumulative, frequency = 0, []
    for value, count in sorted(counts.items()):
        cumulative += count
        frequency.append({'value': value, 'frequency': count, 'relative': count/n, 'cumulative': cumulative})
    results['frequency'] = frequency
    if settings.get('weights') is not None:
        weights = settings['weights']
        if not isinstance(weights, list) or len(weights) != len(dataset['rows']):
            raise ValueError('Provide one weight for every source row, including rows dropped for missing values.')
        weights = [number(v) for v in weights]
        if any(w < 0 for w in weights):
            raise ValueError('Weights must be nonnegative.')
        weights = [weights[i] for i in included]
        total = math.fsum(weights)
        if total <= 0:
            raise ValueError('The included weights must have a positive sum.')
        results['weighted_mean'] = math.fsum(v*(w/total) for v, w in zip(values, weights))
    if ycolumn is not None:
        results['pearson'], results['regression'] = paired_stats(values, ys)
        results['spearman'], _ = paired_stats(ranks(values), ranks(ys))
    selected = settings.get('statistics', list(METRICS))
    if not isinstance(selected, list) or not selected or any(not isinstance(k, str) or k not in METRICS for k in selected):
        raise ValueError('Select at least one supported statistic.')
    issues = {k: METRICS[k][3] for k in selected if results[k] is None}
    reasons = {
        'mode': 'No mode: every observed value occurs once.',
        'sample_variance': 'Sample variance requires at least two observations.',
        'sample_std': 'Sample standard deviation requires at least two observations.',
        'standard_error': 'Standard error requires at least two observations.',
        'coefficient_of_variation': 'Coefficient of variation requires at least two observations and a nonzero mean.',
        'zscores': 'Z-scores are undefined because the population standard deviation is zero.',
        'z_outliers': 'Z-score outliers are undefined because the population standard deviation is zero.',
        'skewness': 'Bias-corrected skewness requires at least three observations and nonzero variance.',
        'excess_kurtosis': 'Bias-corrected excess kurtosis requires at least four observations and nonzero variance.',
        'geometric_mean': 'Geometric mean requires every included value to be strictly positive.',
        'harmonic_mean': 'Harmonic mean requires every included value to be strictly positive.',
        'weighted_mean': 'Supply one nonnegative weight per source row to calculate a weighted mean.',
        'pearson': 'Select two numerical columns with at least two paired observations and variation in both columns.',
        'spearman': 'Select two numerical columns with at least two paired observations and variation in both columns.',
        'regression': 'Select two numerical columns with at least two paired observations and a varying X column.',
    }
    issues.update({k: reasons[k] for k in issues if k in reasons})
    # Avoid serializing IEEE infinity when relative spread exceeds floating-point range.
    for key in selected:
        if isinstance(results[key], float) and not math.isfinite(results[key]):
            results[key] = None
            issues[key] = 'Result exceeds finite floating-point range.'
    return {
        'results': {k: results[k] for k in selected}, 'issues': issues,
        'catalog': {k: dict(zip(('name', 'section', 'formula', 'description'), METRICS[k])) for k in selected},
        'algorithm_version': ALGORITHM_VERSION, 'conventions': CONVENTIONS, 'settings': settings,
        'summary': {'count': n, 'excluded_rows': excluded, 'column': dataset['columns'][column],
                    'y_column': dataset['columns'][ycolumn] if ycolumn is not None else None,
                    'estimated': dataset['kind'] == 'interval', 'kind': dataset['kind']},
        'chart_data': {'values': values, 'y': ys, 'frequency': frequency, 'five_number_summary': results['five_number_summary']},
    }
