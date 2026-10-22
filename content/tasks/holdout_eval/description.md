# holdout_eval (оценка на отложенной выборке)

**Что делает.** Самый простой честный способ оценить модель: отложить часть данных (holdout, обычно 20%), обучить на остальном и посчитать метрики только на отложенном. Модель этих данных не видела — оценка не завышена.

## Как это делают в жизни

Отдельной функции нет — это три строки sklearn:

```python
from sklearn.model_selection import train_test_split
from sklearn.metrics import recall_score, f1_score, average_precision_score

X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, stratify=y, random_state=0)  # доли классов сохранены
model = LogisticRegression(max_iter=1000).fit(X_tr, y_tr)        # обучаем только на train
pred, prob = model.predict(X_te), model.predict_proba(X_te)[:, 1]
print(recall_score(y_te, pred), f1_score(y_te, pred), average_precision_score(y_te, prob))
```

## Параметры (наша функция)

| Параметр | По умолчанию | Что значит |
|---|---|---|
| `estimator` | — | модель с `fit` / `predict` (обучается копия) |
| `X`, `y` | — | данные |
| `metrics` | — | `{имя: f(y_true, y_pred)}` |
| `score_metrics` | `None` | `{имя: f(y_true, оценки)}`; оценки — `predict_proba[:, 1]` или `decision_function` |
| `test_size` | `0.2` | доля отложенной выборки |
| `random_state` | `None` | seed разбиения |
| `stratify` | `True` | сохранять доли классов (через `stratified_split`) |

## Подводные камни

1. **Один holdout — одна случайная оценка.** На 200 объектах с 10% брака в тесте всего 4 бракованных: recall прыгает 0 / 0.25 / 0.5 от seed. Повторите с несколькими seed или берите кросс-валидацию.
2. **Подбор порога и гиперпараметров на том же holdout** — он перестаёт быть честным. Нужно три части: train / validation / test.
3. **Предобработку — после split.** Scaler, веса классов, отбор признаков учатся только на train.
4. **Дубликаты и группы.** Почти одинаковые фото по обе стороны split завышают оценку — делите по изделиям.

## Где используется на карте

<!-- map:start -->
- [defect_detection](#/map/holdout_eval) — одна честная оценка baseline на отложенных 20%
<!-- map:end -->

## Задача

Напишите `holdout_eval(estimator, X, y, metrics, *, score_metrics=None, test_size=0.2, random_state=None, stratify=True)` в `solution.py`; разбиение — свой `from bricks.stratified_split import stratified_split`.
Аналога в sklearn нет — тесты сравнивают с ручным расчётом на том же разбиении и проверяют поведение (seed, копия модели, decision_function).
