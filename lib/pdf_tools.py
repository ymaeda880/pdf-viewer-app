"""
pdf_tools.py (legacy facade)
=================================
旧コードからの移行用の互換モジュール。
内部は `lib.pdf` からエクスポートを再公開するだけです。

- 当面は既存の `from lib.pdf_tools import ...` を壊さないために残置。
- 新規コードでは `from lib.pdf import ...` を推奨します。
"""
from .pdf import *  # noqa: F401,F403
