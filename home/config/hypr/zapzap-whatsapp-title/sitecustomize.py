"""Small runtime patch for ZapZap in this Hyprland setup.

Keeps the window title as WhatsApp / WhatsApp (*) so Hyprland/Waybar can show
communication state without patching files in /nix/store.
"""

import importlib.abc
import importlib.machinery
import sys

_PATCHED = set()
_TARGETS = {
    "zapzap.ui.components.main_window",
    "zapzap.features.browser.shell.browser_controller",
}


def _patch_main_window(module):
    cls = getattr(module, "MainWindowView", None)
    if cls is None or getattr(cls, "_hypr_whatsapp_title_patched", False):
        return

    original = cls.retranslate_ui

    def retranslate_ui(self):
        original(self)
        self.setWindowTitle("WhatsApp")

    cls.retranslate_ui = retranslate_ui
    cls._hypr_whatsapp_title_patched = True


def _patch_browser_controller(module):
    cls = getattr(module, "BrowserController", None)
    if cls is None or getattr(cls, "_hypr_whatsapp_title_patched", False):
        return

    def _update_total_notifications(self):
        total_notifications = sum(
            runtime.button.number_notifications
            for runtime in self._active_runtimes()
        )
        module.SysTrayManager.set_number_notifications(total_notifications)

        window = module.QApplication.instance().getWindow()
        if window is not None:
            window.setWindowTitle("WhatsApp (*)" if total_notifications else "WhatsApp")

    cls._update_total_notifications = _update_total_notifications
    cls._hypr_whatsapp_title_patched = True


def _patch(module):
    name = getattr(module, "__name__", "")
    if name in _PATCHED:
        return
    if name == "zapzap.ui.components.main_window":
        _patch_main_window(module)
    elif name == "zapzap.features.browser.shell.browser_controller":
        _patch_browser_controller(module)
    _PATCHED.add(name)


class _PatchLoader(importlib.abc.Loader):
    def __init__(self, wrapped):
        self.wrapped = wrapped

    def create_module(self, spec):
        if hasattr(self.wrapped, "create_module"):
            return self.wrapped.create_module(spec)
        return None

    def exec_module(self, module):
        self.wrapped.exec_module(module)
        _patch(module)


class _PatchFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname not in _TARGETS:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec and spec.loader:
            spec.loader = _PatchLoader(spec.loader)
        return spec


sys.meta_path.insert(0, _PatchFinder())

# If anything imported before the hook was installed, patch it now.
for name in _TARGETS:
    module = sys.modules.get(name)
    if module is not None:
        _patch(module)
