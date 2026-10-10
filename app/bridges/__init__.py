"""Mixin modules composing the PyWebView ``Api`` bridge (app.bridge.Api).

Each ``*_bridge.py`` module owns one section of the bridge surface and
defines a mixin class; ``app/bridge.py`` multi-inherits them into ``Api``
and applies the standard status-envelope wrapper to every public method.
"""
