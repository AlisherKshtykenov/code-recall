"""sigmoid своими руками — как torch.sigmoid, численно устойчиво при больших |x| (без переполнения exp)."""
import torch


def sigmoid(input):
    """σ(x) = 1 / (1 + e^(−x)). Для x < 0 считаем как e^x / (1 + e^x): exp от отрицательного числа не переполняется."""
    if not isinstance(input, torch.Tensor):  # как torch.sigmoid: только тензоры
        raise TypeError(f"sigmoid(): argument 'input' must be Tensor, not {type(input).__name__}")
    x = input if input.is_floating_point() else input.to(torch.get_default_dtype())  # целые -> float (как torch)
    # e^(−|x|) ∈ (0, 1]: никогда не inf, поэтому нет NaN ни в значении, ни в градиенте.
    # −|x| пишем через where, а не abs: у abs в нуле градиент 0, и σ'(0) получилась бы 0 вместо 0.25.
    z = torch.exp(torch.where(x >= 0, -x, x))
    positive = 1 / (1 + z)  # для x ≥ 0: 1 / (1 + e^(−x))
    negative = z / (1 + z)  # для x < 0: e^x / (1 + e^x)
    return torch.where(x >= 0, positive, negative)  # NaN: сравнение ложно -> ветка negative, а там NaN — как в torch


activation = sigmoid  # реализация слота activation
