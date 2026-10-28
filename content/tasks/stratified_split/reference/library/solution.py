"""stratified_split через sklearn: train_test_split со stratify."""
from sklearn.model_selection import train_test_split  # готовое разбиение train / test


def stratified_split(*arrays, test_size=None, train_size=None, random_state=None, shuffle=True, stratify=None):
    """Та же сигнатура, что у train_test_split; доли классов сохраняются, если передать stratify=y."""
    return train_test_split(  # режет все массивы одними и теми же индексами
        *arrays,  # X, y и любые другие массивы одной длины
        test_size=test_size,  # доля (вверх) или число объектов в test
        train_size=train_size,  # доля (вниз) или число объектов в train
        random_state=random_state,  # seed — повторяемое разбиение
        shuffle=shuffle,  # перемешивать (без этого стратификация невозможна)
        stratify=stratify,  # метки: доли классов в train и test — как во всей выборке
    )
