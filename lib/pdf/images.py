"""
images.py
=================================
PDF の埋め込み画像（XObject）解析と、画像の抽出（PNG）＋ ZIP 作成。

機能概要
--------
- 解析: `analyze_pdf_images()`  
  ページごとの埋め込み画像 (xref, smask, 拡張子) を収集。
- 抽出: `extract_embedded_images()`  
  - XObject そのまま抽出（真の埋め込み画像）
  - ページ見た目サイズで再サンプリング（矩形クリップ＋DPI指定）

Tips
----
- XObject は PDF 内で複数回描画されることがあるため、
  再サンプリングモードでは `get_image_rects(xref)` の全矩形を切り出します。

公開関数一覧
------------
- analyze_pdf_images(pdf_path, mtime_ns, mode="all", sample_pages=6) -> dict  
    PDF 内の埋め込み画像の構造を解析し、フォーマット・件数などを要約。

- extract_embedded_images(pdf_path, img_index, mode="xobject", dpi=144) -> dict  
    埋め込み画像を抽出し、PNG として ZIP に格納して返す。
"""


from __future__ import annotations
from typing import Dict, Any, List
import io
import zipfile
from .cache import cache_data

__all__ = ["analyze_pdf_images", "extract_embedded_images"]


def _human_size(n: int) -> str:
    """人間に読みやすい単位のサイズ表記（B/KB/MB/…）。"""
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(n)
    for u in units:
        if size < 1024 or u == units[-1]:
            return f"{size:.0f} {u}" if u == "B" else f"{size:.1f} {u}"
        size /= 1024


@cache_data()(show_spinner=True)
def analyze_pdf_images(
    pdf_path: str,
    mtime_ns: int,
    mode: str = "all",
    sample_pages: int = 6
) -> Dict[str, Any]:
    """埋め込み画像の構造を解析し、ページごとに要約する。"""
    import fitz
    from collections import Counter

    doc = fitz.open(pdf_path)
    try:
        total_pages = doc.page_count
        if total_pages <= 0:
            return {"scanned_pages": 0, "total_pages": 0, "total_images": 0, "formats_count": {}, "pages": []}
        page_range = range(0, min(sample_pages, total_pages)) if mode == "sample" else range(0, total_pages)

        pages_info: List[Dict[str, Any]] = []
        formats_all: List[str] = []
        total_images = 0

        for i in page_range:
            page = doc.load_page(i)
            images = page.get_images(full=True)  # (xref, smask, w, h, bpc, colorspace, ...)
            fmts, xrefs, smasks = [], [], []
            for im in images:
                xref, smask = im[0], im[1]
                try:
                    ext = (doc.extract_image(xref).get("ext") or "bin").lower()
                except Exception:
                    ext = "bin"
                fmts.append(ext)
                xrefs.append(xref)
                smasks.append(smask)
            total_images += len(images)
            pages_info.append({"page": i + 1, "count": len(images), "formats": fmts, "xrefs": xrefs, "smasks": smasks})
            formats_all.extend(fmts)

        return {
            "scanned_pages": len(page_range),
            "total_pages": total_pages,
            "total_images": total_images,
            "formats_count": dict(Counter(formats_all)),
            "pages": pages_info
        }
    finally:
        doc.close()


def _export_xobject_png(doc, xref: int, smask: int):
    """XObject（真の埋め込み画像）を PNG(RGB/RGBA) に正規化して返す。"""
    import fitz
    pix = fitz.Pixmap(doc, xref)
    # 多チャンネル（CMYK 等）→ RGB
    if pix.n > 4 and pix.alpha == 0:
        pix = fitz.Pixmap(fitz.csRGB, pix)
    # SMask 合成（アルファ）
    if smask and smask > 0:
        m = fitz.Pixmap(doc, smask)
        pix = fitz.Pixmap(pix, m)
    return pix.tobytes("png"), pix.width, pix.height


def _export_resampled_png(page, rect, dpi: int):
    """ページ上の矩形 `rect` を DPI 指定でレンダリングして PNG へ。"""
    import fitz
    mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
    pm = page.get_pixmap(clip=rect, matrix=mat, alpha=False)
    return pm.tobytes("png"), pm.width, pm.height


def extract_embedded_images(
    pdf_path,
    img_index: Dict[str, Any],
    mode: str = "xobject",
    dpi: int = 144
) -> Dict[str, Any]:
    """埋め込み画像を抽出し、ZIP（メモリ）に格納して返す。

    Parameters
    ----------
    img_index : dict
        `analyze_pdf_images()` の結果。各ページの xref / smask を使用。
    mode : {"xobject","resample"}
        - "xobject"   : 埋め込み画像データをそのまま PNG 正規化
        - "resample"  : ページ見た目サイズの矩形を全て切出し（なければ xobject にフォールバック）
    dpi : int
        再サンプリング時のレンダリング DPI
    """
    import fitz
    doc = fitz.open(str(pdf_path))
    pages_out: List[Dict[str, Any]] = []
    zip_buf = io.BytesIO()
    zf = zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED)

    try:
        for row in img_index.get("pages", []):
            if row.get("count", 0) == 0:
                continue
            pno = int(row["page"])
            page = doc.load_page(pno - 1)
            smasks = row.get("smasks", [0] * len(row.get("xrefs", [])))
            imgs: List[Dict[str, Any]] = []

            for idx_in_page, (xref, smask) in enumerate(zip(row.get("xrefs", []), smasks), start=1):
                try:
                    if mode == "resample":
                        try:
                            rects = page.get_image_rects(xref)
                        except Exception:
                            rects = []
                        if rects:
                            for rep_idx, r in enumerate(rects, start=1):
                                png_bytes, w, h = _export_resampled_png(page, r, dpi)
                                label = f"切出し {w}×{h}（{_human_size(len(png_bytes))}）"
                                fname = f"p{pno:03d}_img{idx_in_page:02d}_rep{rep_idx}_x{xref}.png"
                                imgs.append({"bytes": png_bytes, "label": label, "filename": fname})
                                zf.writestr(fname, png_bytes)
                            continue  # 次の xref へ

                    # xobject or fallback
                    png_bytes, w, h = _export_xobject_png(doc, xref, smask)
                    label = f"XObject {w}×{h}（{_human_size(len(png_bytes))}）"
                    fname = f"p{pno:03d}_img{idx_in_page:02d}_x{xref}.png"
                    imgs.append({"bytes": png_bytes, "label": label, "filename": fname})
                    zf.writestr(fname, png_bytes)

                except Exception as e:
                    imgs.append({"bytes": b"", "label": f"画像抽出失敗: {e}", "filename": ""})

            if imgs:
                pages_out.append({"page": pno, "images": imgs})

    finally:
        zf.close()
        doc.close()

    return {"pages": pages_out, "zip_bytes": zip_buf.getvalue()}
