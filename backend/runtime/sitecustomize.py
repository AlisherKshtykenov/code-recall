"""Подключается автоматически во всех процессах CODE RECALL (папка runtime/ в PYTHONPATH):
после импорта matplotlib.pyplot подменяет plt.show() — фигуры сохраняются в results/ и
показываются в выводе. matplotlib при этом не импортируется заранее."""
import importlib.abc
import importlib.util
import sys


class _PyplotHook(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name != "matplotlib.pyplot":
            return None
        sys.meta_path.remove(self)  # дальше ищем как обычно; хук нужен один раз
        spec = importlib.util.find_spec(name)
        if spec is None or spec.loader is None:
            return spec
        original = spec.loader.exec_module

        def exec_module(module):
            original(module)
            try:
                import recall
                recall._patch_pyplot(module)
            except Exception:
                pass

        spec.loader.exec_module = exec_module
        return spec


sys.meta_path.insert(0, _PyplotHook())
