"""learning_curve своими руками — как sklearn.model_selection.learning_curve: для нескольких размеров обучающей
выборки обучить модель на каждом фолде кросс-валидации и посчитать качество на train и на test.
Работает с любым объектом, у которого есть fit / predict / score (как у sklearn)."""
import copy
import numbers
import time
import warnings

import numpy as np


def _take(X, idx):
    """Строки idx: pandas — через iloc, остальное — как numpy."""
    return X.iloc[idx] if hasattr(X, "iloc") else np.asarray(X)[idx]


def _is_classifier(est):
    tags = getattr(est, "__sklearn_tags__", None)
    if tags is not None:
        try:
            return tags().estimator_type == "classifier"
        except Exception:  # noqa: BLE001 — не sklearn-объект с несовместимыми тегами
            pass
    return getattr(est, "_estimator_type", None) == "classifier" or hasattr(est, "predict_proba")


def _kfold(n, k):
    """Как KFold без перемешивания: подряд идущие куски, первые n % k — на один больше."""
    if k > n:
        raise ValueError(f"Cannot have number of splits n_splits={k} greater than the number of samples: n_samples={n}.")
    sizes = np.full(k, n // k)
    sizes[: n % k] += 1
    start, out = 0, []
    for s in sizes:
        test = np.arange(start, start + s)
        out.append((np.r_[np.arange(0, start), np.arange(start + s, n)], test))
        start += s
    return out


def _stratified_kfold(y, k):
    """Как StratifiedKFold без перемешивания: каждый класс раскладывается по фолдам по кругу и блоками."""
    y = np.asarray(y)
    _, first_idx, inv = np.unique(y, return_index=True, return_inverse=True)
    order_of_appearance = np.argsort(np.argsort(first_idx))  # класс, встретившийся первым, — номер 0
    y_enc = order_of_appearance[inv]
    n_classes = len(first_idx)
    counts = np.array([np.sum(y_enc == c) for c in range(n_classes)])
    if np.all(k > counts):
        raise ValueError(f"n_splits={k} cannot be greater than the number of members in each class.")
    if k > counts.min():
        warnings.warn(f"The least populated class in y has only {counts.min()} members, which is less than n_splits={k}.", UserWarning)
    y_sorted = np.sort(y_enc)
    allocation = np.array([[np.sum(y_sorted[i::k] == c) for c in range(n_classes)] for i in range(k)])  # сколько класса c в фолде i
    test_fold = np.empty(len(y), dtype=int)
    for c in range(n_classes):
        test_fold[y_enc == c] = np.repeat(np.arange(k), allocation[:, c])  # объекты класса c по порядку — блоками по фолдам
    return [(np.flatnonzero(test_fold != i), np.flatnonzero(test_fold == i)) for i in range(k)]


def _splits(cv, X, y, groups, classifier):
    if cv is None:
        cv = 5  # по умолчанию 5 фолдов
    if isinstance(cv, numbers.Integral):
        y_arr = np.asarray(y)
        if classifier and y_arr.ndim == 1 and len(np.unique(y_arr)) >= 2:
            return _stratified_kfold(y_arr, int(cv))  # классификатор — стратифицированные фолды
        return _kfold(len(y_arr), int(cv))
    if hasattr(cv, "split"):
        return [(np.asarray(tr), np.asarray(te)) for tr, te in cv.split(X, y, groups)]  # любой splitter
    return [(np.asarray(tr), np.asarray(te)) for tr, te in cv]  # готовый список (train, test)


def _sizes(train_sizes, n_max):
    """Доли (0, 1] -> число объектов; целые — как есть; дубликаты убираются с предупреждением."""
    sizes = np.asarray(train_sizes)
    n_ticks = len(sizes)
    if np.issubdtype(sizes.dtype, np.floating):
        if sizes.min() <= 0.0 or sizes.max() > 1.0:
            raise ValueError("train_sizes has been interpreted as fractions of the maximum number of training samples and must be "
                             f"within (0, 1], but is within [{sizes.min():f}, {sizes.max():f}].")
        sizes = np.clip((sizes * n_max).astype(int), 1, n_max)  # доля от самого большого train
    elif sizes.min() <= 0 or sizes.max() > n_max:
        raise ValueError(f"train_sizes has been interpreted as absolute numbers of training samples and must be within (0, {n_max}], "
                         f"but is within [{sizes.min()}, {sizes.max()}].")
    sizes = np.unique(sizes)
    if len(sizes) < n_ticks:
        warnings.warn(f"Removed duplicate entries from 'train_sizes'. Number of ticks will be less than the size of "
                      f"'train_sizes': {len(sizes)} instead of {n_ticks}.", RuntimeWarning)
    return sizes


def learning_curve(estimator, X, y, *, groups=None, train_sizes=np.linspace(0.1, 1.0, 5), cv=None, scoring=None,
                   shuffle=False, random_state=None, error_score=np.nan, return_times=False):
    """-> (train_sizes_abs, train_scores, test_scores[, fit_times, score_times]); оценки — (n_ticks, n_folds)."""
    splits = _splits(cv, X, y, groups, _is_classifier(estimator))
    sizes = _sizes(train_sizes, len(splits[0][0]))  # «весь train» — train первого фолда (как в sklearn)
    if shuffle:  # перемешать train каждого фолда — тем же генератором, что sklearn (RandomState)
        rng = random_state if isinstance(random_state, np.random.RandomState) else np.random.RandomState(random_state)
        splits = [(rng.permutation(tr), te) for tr, te in splits]
    score = (lambda est, Xs, ys: est.score(Xs, ys)) if scoring is None else scoring  # по умолчанию — estimator.score
    shape = (len(sizes), len(splits))
    train_scores, test_scores, fit_times, score_times = (np.empty(shape) for _ in range(4))
    y = np.asarray(y)
    failures = []
    for j, (train, test) in enumerate(splits):
        for i, n in enumerate(sizes):
            part = train[:n]  # первые n объектов train-фолда
            model = copy.deepcopy(estimator)  # новая необученная копия на каждую точку
            t0 = time.perf_counter()
            try:
                model.fit(_take(X, part), y[part])
            except Exception as e:  # noqa: BLE001 — например, в маленьком train один класс
                if isinstance(error_score, str) and error_score == "raise":
                    raise
                failures.append(f"{type(e).__name__}: {e}")
                train_scores[i, j] = test_scores[i, j] = error_score  # как sklearn: точка = error_score (nan)
                fit_times[i, j], score_times[i, j] = time.perf_counter() - t0, 0.0
                continue
            t1 = time.perf_counter()
            test_scores[i, j] = score(model, _take(X, test), y[test])  # качество на отложенном фолде
            t2 = time.perf_counter()
            train_scores[i, j] = score(model, _take(X, part), y[part])  # качество на том, на чём учили
            fit_times[i, j], score_times[i, j] = t1 - t0, t2 - t1
    total = len(sizes) * len(splits)
    if len(failures) == total:  # не удалось ни одно обучение — это уже ошибка
        raise ValueError(f"All the {total} fits failed. Последняя ошибка: {failures[-1]}")
    if failures:
        warnings.warn(f"{len(failures)} fits failed out of a total of {total}. The score on these train-test partitions "
                      f"for these parameters will be set to {error_score}. Последняя ошибка: {failures[-1]}", UserWarning)
    out = (sizes, train_scores, test_scores)
    return out + (fit_times, score_times) if return_times else out
