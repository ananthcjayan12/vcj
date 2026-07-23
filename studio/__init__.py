"""Repo-local Physics Production Studio.

The standalone Reel-pack feature is installed only when the normal
``python3 -m studio.server`` entrypoint constructs its HTTP server.  This keeps
imports and tests side-effect free while preserving the existing launch command.
"""
from __future__ import annotations

import http.server
import sys
from typing import Any


def _requested_studio_server() -> bool:
    arguments = list(getattr(sys, "orig_argv", sys.argv))
    return "studio.server" in arguments or any(str(item).endswith("studio/server.py") for item in arguments)


def _bootstrap_reel_pack_extension() -> None:
    if not _requested_studio_server():
        return
    original = http.server.ThreadingHTTPServer.__init__
    if getattr(original, "_mav_reel_pack_bootstrap", False):
        return

    def wrapped(
        instance: http.server.ThreadingHTTPServer,
        server_address: Any,
        request_handler_class: type,
        bind_and_activate: bool = True,
    ) -> None:
        try:
            if request_handler_class.__name__ == "StudioHandler":
                module = sys.modules.get(request_handler_class.__module__)
                if module is not None:
                    from .reel_pack_extension import install

                    install(module)
        finally:
            http.server.ThreadingHTTPServer.__init__ = original
        original(instance, server_address, request_handler_class, bind_and_activate)

    wrapped._mav_reel_pack_bootstrap = True  # type: ignore[attr-defined]
    http.server.ThreadingHTTPServer.__init__ = wrapped


_bootstrap_reel_pack_extension()
