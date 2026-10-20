import pandas as pd

from analysis import clean, load, summary


def test_load_reads_all_rows(data_dir):
    df = load(str(data_dir / "students.csv"))
    assert list(df.columns) == ["name", "group", "subject", "score"]
    assert len(df) == 52


def test_clean():
    df = clean(load())
    assert len(df) == 48                       # без пропуска, 140, -5 и дубликата
    assert df["score"].between(0, 100).all()
    assert set(df["group"]) == {"ml-1", "ml-2", "ds-1"}
    assert not df["name"].str.startswith(" ").any()


def test_summary_table():
    table = summary(clean(load()))
    expected = pd.DataFrame(
        {"students": [6, 5, 5], "mean_score": [74.4, 70.4, 65.0], "best": [100.0, 100.0, 93.0]},
        index=pd.Index(["ml-1", "ds-1", "ml-2"], name="group"))
    pd.testing.assert_frame_equal(table, expected, check_dtype=False)
