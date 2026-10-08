from pathlib import Path
import json
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, cross_val_predict

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data' / 'analytical_panel.csv'
NUM = ['Sown area, th. ha','Apr-Sep temperature, °C','Apr-Sep precipitation, mm','Apr-Sep root-zone wetness','Apr-Sep solar radiation, MJ/m²/day']
CAT = ['District','Crop']
TARGET = 'Yield, centners/ha'


def make_model(min_leaf=2, max_depth=None, max_features=1.0, n_estimators=350):
    pre = ColumnTransformer([
        ('cat', OneHotEncoder(handle_unknown='ignore'), CAT),
        ('num', StandardScaler(), NUM),
    ])
    rf = RandomForestRegressor(
        n_estimators=n_estimators,
        random_state=42,
        min_samples_leaf=min_leaf,
        max_depth=max_depth,
        max_features=max_features,
        n_jobs=-1,
    )
    return Pipeline([('pre', pre), ('model', rf)])


def metrics(y, p):
    return {
        'MAE': float(mean_absolute_error(y, p)),
        'RMSE': float(mean_squared_error(y, p) ** 0.5),
        'R2': float(r2_score(y, p)),
    }


def load_core_data():
    df = pd.read_csv(DATA).dropna(subset=[TARGET]).copy()
    if 'Use in analytical core' in df.columns:
        df = df[df['Use in analytical core'].astype(str).str.startswith('Yes')].copy()
    if 'Use in 2.3 inference' in df.columns:
        df = df[df['Use in 2.3 inference'].astype(str).str.startswith('Yes')].copy()
    df['Year'] = pd.to_numeric(df['Year'], errors='coerce')
    return df.dropna(subset=['Year']).copy()


def fold_baseline(df):
    X = df[CAT + NUM]
    y = df[TARGET]
    groups = df['Year'].astype(str)
    cv = GroupKFold(n_splits=min(5, groups.nunique()))
    out = pd.Series(index=df.index, dtype=float)
    for tridx, teidx in cv.split(X, y, groups):
        tr = df.iloc[tridx]
        te = df.iloc[teidx]
        dc = tr.groupby(['District','Crop'])[TARGET].median()
        cm = tr.groupby('Crop')[TARGET].median()
        gm = tr[TARGET].median()
        out.iloc[teidx] = [dc.get((r.District, r.Crop), cm.get(r.Crop, gm)) for r in te.itertuples(index=False)]
    return out


def temporal_window(df, train_start, train_end, test_start, test_end, n_estimators=500):
    train = df[(df.Year >= train_start) & (df.Year <= train_end)].copy()
    test = df[(df.Year >= test_start) & (df.Year <= test_end)].copy()
    if train.empty or test.empty:
        return None
    model = make_model(n_estimators=n_estimators)
    model.fit(train[CAT + NUM], train[TARGET])
    pred = model.predict(test[CAT + NUM])
    result = metrics(test[TARGET], pred)
    result.update({
        'train_start': int(train_start),
        'train_end': int(train_end),
        'test_start': int(test_start),
        'test_end': int(test_end),
        'train_N': int(len(train)),
        'test_N': int(len(test)),
        'test_years': sorted(map(int, test.Year.unique())),
    })
    dc = train.groupby(['District','Crop'])[TARGET].median()
    cm = train.groupby('Crop')[TARGET].median()
    gm = train[TARGET].median()
    base_pred = np.array([dc.get((r.District, r.Crop), cm.get(r.Crop, gm)) for r in test.itertuples(index=False)])
    result['baseline'] = metrics(test[TARGET], base_pred)
    return result


def expanding_five_year_windows(df):
    """Leakage-safe expanding-window validation with three fixed five-year test blocks.

    Final 2004-2025 specification:
      train 2004-2010 -> test 2011-2015
      train 2004-2015 -> test 2016-2020
      train 2004-2020 -> test 2021-2025

    The final production model is fitted only after validation on the complete
    2004-2025 analytical panel.
    """
    y0 = int(df.Year.min())
    ymax = int(df.Year.max())
    requested = [
        (y0, 2010, 2011, 2015),
        (y0, 2015, 2016, 2020),
        (y0, 2020, 2021, 2025),
    ]
    windows = []
    for train_start, train_end, test_start, test_end in requested:
        if train_start < y0 or test_end > ymax:
            continue
        res = temporal_window(df, train_start, train_end, test_start, test_end)
        if res is not None:
            windows.append(res)
    return windows



def leave_one_district_out_validation(df):
    """Spatial transferability test: every district is held out once.

    This is intentionally stricter than the primary GroupKFold-by-year validation.
    It asks whether the model transfers to a district whose observations were not
    available during fitting.
    """
    rows = []
    all_y, all_p = [], []
    for district in sorted(df['District'].dropna().astype(str).unique()):
        train = df[df['District'].astype(str) != district].copy()
        test = df[df['District'].astype(str) == district].copy()
        if train.empty or test.empty:
            continue
        model = make_model(n_estimators=250)
        model.fit(train[CAT + NUM], train[TARGET])
        pred = model.predict(test[CAT + NUM])
        m = metrics(test[TARGET], pred)
        rows.append({'District': district, 'N': int(len(test)), **m})
        all_y.extend(test[TARGET].astype(float).tolist())
        all_p.extend(map(float, pred))
    overall = metrics(np.asarray(all_y), np.asarray(all_p)) if all_y else {'MAE':None,'RMSE':None,'R2':None}
    overall['N'] = int(len(all_y))
    overall['districts'] = int(len(rows))
    return overall, rows


def residual_prediction_intervals(df, pred, coverage=0.90):
    """Empirical out-of-sample residual intervals by crop.

    These are uncertainty bands based on grouped out-of-sample residuals, not formal
    parametric confidence intervals. They are packaged for transparent UI/reporting.
    """
    tmp = df[['Crop', TARGET]].copy()
    tmp['pred'] = np.asarray(pred, float)
    tmp['abs_error'] = (tmp[TARGET] - tmp['pred']).abs()
    q = float(coverage)
    rows = {}
    for crop, g in tmp.groupby('Crop'):
        half = float(g['abs_error'].quantile(q))
        empirical = float((g['abs_error'] <= half + 1e-12).mean())
        rows[str(crop)] = {
            'N': int(len(g)),
            'coverage_target': q,
            'half_width_centners_ha': half,
            'empirical_coverage': empirical,
            'method': 'absolute grouped-OOS residual quantile',
        }
    all_half = float(tmp['abs_error'].quantile(q))
    return {
        'coverage_target': q,
        'overall_half_width_centners_ha': all_half,
        'overall_empirical_coverage': float((tmp['abs_error'] <= all_half + 1e-12).mean()),
        'by_crop': rows,
        'interpretation': 'empirical prediction-uncertainty band; not a parametric confidence interval',
    }


def main():
    df = load_core_data()
    X = df[CAT + NUM]
    y = df[TARGET]
    groups = df['Year'].astype(str)

    # Primary leakage-safe grouped validation: all rows from the same year stay in one fold.
    cv = GroupKFold(n_splits=min(5, groups.nunique()))
    pred = cross_val_predict(make_model(), X, y, cv=cv, groups=groups)
    overall = metrics(y, pred)

    per_crop = {}
    tmp = df[['Crop', TARGET]].copy()
    tmp['pred'] = pred
    for crop, g in tmp.groupby('Crop'):
        per_crop[crop] = {'N': int(len(g)), **metrics(g[TARGET], g['pred'])}

    # Spatial transferability and empirical prediction-uncertainty diagnostics.
    lodo_overall, lodo_by_district = leave_one_district_out_validation(df)
    prediction_intervals = residual_prediction_intervals(df, pred, coverage=0.90)

    # Production-equivalent fit on the complete validated historical panel.
    model = make_model(n_estimators=350)
    model.fit(X, y)
    train_metrics = metrics(y, model.predict(X))

    # Chronological expanding-window validation with five-year test blocks.
    expanding = expanding_five_year_windows(df)

    # A deliberately severe long-horizon test when the sample is long enough:
    # first ten years for training, next ten years for testing (current panel: 2004-2013 -> 2014-2023).
    stress = None
    y0 = int(df.Year.min())
    if int(df.Year.max()) >= y0 + 19:
        stress = temporal_window(df, y0, y0 + 9, y0 + 10, y0 + 19, n_estimators=500)

    cv_base = metrics(y, fold_baseline(df))

    robust = []
    settings = [
        ('leaf1', 1, None, 1.0, 350),
        ('leaf2', 2, None, 1.0, 350),
        ('leaf4', 4, None, 1.0, 350),
        ('depth12', 2, 12, 1.0, 350),
        ('sqrt', 2, None, 'sqrt', 350),
        ('trees200', 2, None, 1.0, 200),
        ('trees500', 2, None, 1.0, 500),
    ]
    for name, leaf, depth, mf, trees in settings:
        p = cross_val_predict(
            make_model(min_leaf=leaf, max_depth=depth, max_features=mf, n_estimators=trees),
            X, y, cv=cv, groups=groups,
        )
        robust.append({'specification': name, **metrics(y, p)})

    result = {
        'dataset': {
            'N': int(len(df)),
            'years': int(df.Year.nunique()),
            'year_min': int(df.Year.min()),
            'year_max': int(df.Year.max()),
            'districts': int(df.District.nunique()),
            'crops': int(df.Crop.nunique()),
            'production_training_period': f"{int(df.Year.min())}-{int(df.Year.max())}",
        },
        'groupkfold_by_year': overall,
        'training_fit': train_metrics,
        'expanding_five_year_validation': expanding,
        'ten_year_stress_holdout': stress,
        'baseline_groupkfold': cv_base,
        'per_crop_groupkfold': per_crop,
        'leave_one_district_out': {
            'overall': lodo_overall,
            'by_district': lodo_by_district,
            'interpretation': 'spatial transferability stress test; each district held out from training in turn',
        },
        'prediction_intervals_90': prediction_intervals,
        'hyperparameter_robustness': robust,
    }
    (ROOT / 'data' / 'scientific_validation.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8'
    )

    rows = [
        {'scheme': 'GroupKFold-by-year RF', **overall},
        {'scheme': 'GroupKFold median baseline', **cv_base},
    ]
    for w in expanding:
        rows.append({
            'scheme': f"Expanding RF train {w['train_start']}-{w['train_end']} test {w['test_start']}-{w['test_end']}",
            'MAE': w['MAE'], 'RMSE': w['RMSE'], 'R2': w['R2'],
        })
        rows.append({
            'scheme': f"Expanding median baseline train {w['train_start']}-{w['train_end']} test {w['test_start']}-{w['test_end']}",
            'MAE': w['baseline']['MAE'], 'RMSE': w['baseline']['RMSE'], 'R2': w['baseline']['R2'],
        })
    if stress is not None:
        rows.append({
            'scheme': f"10-year stress RF train {stress['train_start']}-{stress['train_end']} test {stress['test_start']}-{stress['test_end']}",
            'MAE': stress['MAE'], 'RMSE': stress['RMSE'], 'R2': stress['R2'],
        })
        rows.append({
            'scheme': f"10-year stress median baseline train {stress['train_start']}-{stress['train_end']} test {stress['test_start']}-{stress['test_end']}",
            'MAE': stress['baseline']['MAE'], 'RMSE': stress['baseline']['RMSE'], 'R2': stress['baseline']['R2'],
        })
    rows.append({'scheme': 'Training fit RF (reference only)', **train_metrics})
    pd.DataFrame(rows)[['scheme','MAE','RMSE','R2']].to_csv(ROOT / 'data' / 'model_metrics.csv', index=False)
    pd.DataFrame([{'Crop': k, **v} for k, v in per_crop.items()]).to_csv(ROOT / 'data' / 'model_metrics_by_crop.csv', index=False)
    pd.DataFrame(lodo_by_district).to_csv(ROOT / 'data' / 'model_metrics_leave_one_district_out.csv', index=False)
    pd.DataFrame([{'Crop': k, **v} for k, v in prediction_intervals['by_crop'].items()]).to_csv(ROOT / 'data' / 'prediction_intervals_by_crop.csv', index=False)
    return result


if __name__ == '__main__':
    r = main()
    print(json.dumps(r, ensure_ascii=False, indent=2))
