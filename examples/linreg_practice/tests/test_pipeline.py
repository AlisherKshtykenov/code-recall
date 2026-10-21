from pipeline import load, run


def test_shapes(data_dir):
    X, y = load(str(data_dir / "houses.csv"))
    res = run(str(data_dir / "houses.csv"), epochs=5)
    assert X.shape[1] == 4 and res["n_train"] + res["n_test"] == len(y)
    assert res["pred_shape"] == (res["n_test"],)


def test_loss_decreases(data_dir):
    losses = run(str(data_dir / "houses.csv"), epochs=60)["losses"]
    assert losses[-1] < losses[0]


def test_r2_on_test(data_dir):
    r2 = run(str(data_dir / "houses.csv"))["r2_test"]
    assert r2 > 0.5, f"R² на тесте {r2:.3f} <= 0.5"
