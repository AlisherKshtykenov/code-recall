"""normalize_images через torch / torchvision."""
import torch  # тензоры
import torchvision.transforms.functional as TF  # готовая нормализация картинок


def normalize(tensor, mean, std, inplace=False):
    """(x − mean[c]) / std[c] по каналам — функция torchvision."""
    return TF.normalize(tensor, mean, std, inplace=inplace)  # проверки типов и форм — внутри torchvision


def compute_mean_std(data, unbiased=False):
    """mean и std каждого канала по датасету: самый простой практический способ — собрать всё в один тензор."""
    if isinstance(data, torch.Tensor):
        x = data  # уже весь датасет (N, C, H, W)
    else:
        batches = [b[0] if isinstance(b, (tuple, list)) else b for b in data]  # из DataLoader берём картинки
        if not batches:
            raise ValueError("пустой датасет: не по чему считать mean и std")
        x = torch.cat(batches)  # весь датасет в память (для больших — считайте суммы по батчам)
    if x.numel() == 0:
        raise ValueError("пустой датасет: не по чему считать mean и std")
    x = x.double()  # точность накопления
    mean = x.mean(dim=(0, 2, 3))  # среднее по батчу и пикселям — для каждого канала
    std = x.std(dim=(0, 2, 3), unbiased=unbiased)  # разброс каждого канала
    return mean.float(), std.float()
