import random

from solution import quicksort


def test_basic():
    assert quicksort([3, 1, 2]) == [1, 2, 3]


def test_empty_and_single():
    assert quicksort([]) == []
    assert quicksort([5]) == [5]


def test_duplicates():
    assert quicksort([2, 3, 2, 1, 3, 1]) == [1, 1, 2, 2, 3, 3]


def test_random_matches_sorted():
    rng = random.Random(0)
    for _ in range(50):
        xs = [rng.randint(-100, 100) for _ in range(rng.randint(0, 40))]
        assert quicksort(xs) == sorted(xs)


def test_does_not_mutate_input():
    xs = [3, 1, 2]
    quicksort(xs)
    assert xs == [3, 1, 2]
