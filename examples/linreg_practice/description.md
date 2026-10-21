# Линейная регрессия на практике

Цены домов из `data/houses.csv` (цена — в сотнях тысяч): **split → scaler → LinearRegression → метрики**.

Собрано из кирпичиков:

- `from bricks.split import train_test_split`
- `from bricks.scaler import StandardScaler`
- `from bricks.model import LinearRegression` — а внутри него `from slots.loss import loss`

`run()` возвращает лоссы по эпохам и метрики на тесте. Тесты: формы, лосс падает, R² на тесте > 0.5.
