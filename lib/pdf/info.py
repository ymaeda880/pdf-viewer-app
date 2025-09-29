"""
info.py
=================================
PDF の軽量解析（quick scan）。

機能
----
- 総ページ数と、先頭 N ページのテキスト有無から
  「テキストPDF / 画像PDF」を推定。

設計メモ
--------
- PyMuPDF（fitz）で `get_text("text")` を使用。
- 一定以上の文字数（>=20）を含むページの割合で判定。
- キャッシュ可能（Streamlit 環境では `st.cache_data`）。

公開関数一覧
------------
- quick_pdf_info(pdf_path: str, mtime_ns: int, sample_pages: int = 6,
                 text_ratio_threshold: float = 0.3) -> dict  
    軽量に PDF の種別（テキストPDF / 画像PDF）を推定する。
"""


from __future__ import annotations
from typing import Dict, Any
from .cache import cache_data

__all__ = ["quick_pdf_info"]  # 公開関数を明示


@cache_data()(show_spinner=False)
def quick_pdf_info(
    pdf_path: str,
    mtime_ns: int,
    sample_pages: int = 6,
    text_ratio_threshold: float = 0.3
) -> Dict[str, Any]:
    """軽量に PDF 種別を推定（テキストPDF/画像PDF）。

    Parameters
    ----------
    pdf_path : str
        解析する PDF のパス
    mtime_ns : int
        無効化キー用の更新時刻（ns）
    sample_pages : int, default 6
        先頭から何ページを見るか
    text_ratio_threshold : float, default 0.3
        テキストページ比率のしきい値

    Returns
    -------
    dict
        {"pages": int, "kind": str, "text_ratio": float, "checked": int}
    """
    import fitz
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return {"pages": 0, "kind": "画像PDF", "text_ratio": 0.0, "checked": 0}
    try:
        n = doc.page_count
        check = min(sample_pages, max(n, 1))
        text_pages = 0
        for i in range(check):
            try:
                p = doc.load_page(i)
                if len((p.get_text("text") or "").strip()) >= 20:
                    text_pages += 1
            except Exception:
                pass
        ratio = text_pages / max(check, 1)
        return {
            "pages": n,
            "kind": "テキストPDF" if ratio >= text_ratio_threshold else "画像PDF",
            "text_ratio": ratio,
            "checked": check,
        }
    finally:
        doc.close()
