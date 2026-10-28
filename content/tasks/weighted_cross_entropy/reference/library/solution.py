"""weighted_cross_entropy через torch: BCE по логитам с pos_weight."""
import torch.nn.functional as F  # потери torch


def binary_cross_entropy_with_logits(input, target, weight=None, reduction="mean", pos_weight=None):
    """sigmoid внутри — устойчиво при любых логитах; pos_weight — во сколько раз дороже ошибка на браке."""
    return F.binary_cross_entropy_with_logits(  # то же, что nn.BCEWithLogitsLoss(pos_weight=…)
        input, target,  # логиты и ответы той же формы (float)
        weight=weight,  # вес каждого элемента
        reduction=reduction,  # mean / sum / none
        pos_weight=pos_weight,  # = отрицательных / положительных (из class_weights)
    )


loss = binary_cross_entropy_with_logits  # реализация слота loss
