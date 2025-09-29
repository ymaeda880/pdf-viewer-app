# pages/10_PDFビューア.py
# ------------------------------------------------------------
# 📄 PDF ビューア（サムネイル）
# - サムネ下に「テキストPDF/画像PDF」＋ページ数を表示
# - 右ペインは ①pdf.js（streamlit-pdf-viewer） ②Streamlit内蔵（st.pdf）
#   ③ブラウザPDFプラグイン のいずれかで表示可能（サイドバー）
# - ビューアの幅/高さをサイドバーで調整
# - 左上に倍率バッジ（自前ラベル）を重ね表示
#
# 【機能（既存）】
# - 画像埋め込み解析：総数・形式別集計・ページ別内訳
# - テキスト抽出：ページ別に冒頭500文字プレビュー
# - 調査方式切替：全ページ / 先頭Nページ（既定：全ページ）
#
# 【今回の変更点（埋め込み画像の“抽出”対応）】
# 1) 「埋め込み画像を表示する」時の抽出モードを追加（サイドバー）
#    - XObjectそのまま抽出（真の埋め込み画像）：色空間をRGB化、SMask合成してPNG化
#    - ページ見た目サイズで再サンプリング（視覚的抽出）：get_image_rects + クリップレンダリング
# 2) 画像はページごとにサムネ表示。キャプションに「幅×高さ / 容量」を表示
# 3) 現在の抽出モードで得た画像を ZIP で一括ダウンロード可能
# 4) 解析関数で SMask xref を保持（合成に使用）
# ------------------------------------------------------------
from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any
import io
import zipfile
import base64
import streamlit as st

# Optional: pdf.js ビューア
try:
    from streamlit_pdf_viewer import pdf_viewer  # pip install streamlit-pdf-viewer
    HAS_PDFJS = True
except Exception:
    HAS_PDFJS = False

# ========== パス ==========
APP_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = APP_ROOT / "data"
PDF_ROOT_DEFAULT = DATA_DIR / "pdf"

# ========== サムネ & PDF読み ==========
@st.cache_data(show_spinner=False)
def render_thumb_png(pdf_path: str, thumb_px: int, mtime_ns: int) -> bytes:
    import fitz  # PyMuPDF
    doc = fitz.open(pdf_path)
    try:
        page = doc.load_page(0)
        w = page.rect.width
        zoom = max(0.5, min(5.0, float(thumb_px) / max(w, 1.0)))
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()

@st.cache_data(show_spinner=False)
def read_pdf_bytes(pdf_path: str, mtime_ns: int) -> bytes:
    return Path(pdf_path).read_bytes()

@st.cache_data(show_spinner=False)
def read_pdf_b64(pdf_path: str, mtime_ns: int) -> str:
    return base64.b64encode(Path(pdf_path).read_bytes()).decode("ascii")

@st.cache_data(show_spinner=False)
def quick_pdf_info(pdf_path: str, mtime_ns: int, sample_pages: int = 6) -> dict:
    """
    先頭 sample_pages をざっくり解析して
    - pages: 総ページ数
    - kind : 'テキストPDF' or '画像PDF'
    を返す（キャッシュはパス＋mtimeで無効化）。
    """
    import fitz
    doc = fitz.open(pdf_path)
    try:
        n = doc.page_count
        check = min(sample_pages, n if n > 0 else 1)
        text_pages = 0
        for i in range(check):
            p = doc.load_page(i)
            txt = (p.get_text("text") or "").strip()
            if len(txt) >= 20:
                text_pages += 1
        ratio = (text_pages / max(check, 1))
        kind = "テキストPDF" if ratio >= 0.3 else "画像PDF"
        return {"pages": n, "kind": kind, "ratio": ratio, "checked": check}
    finally:
        doc.close()

# ========== 画像埋め込み解析 ==========
@st.cache_data(show_spinner=True)
def analyze_pdf_images(
    pdf_path: str,
    mtime_ns: int,
    mode: str = "all",          # "all" or "sample"
    sample_pages: int = 6
) -> Dict[str, Any]:
    """
    PDF内の画像埋め込みを走査して集計する。
    戻り値:
      {
        "scanned_pages": int,
        "total_pages": int,
        "total_images": int,
        "formats_count": {"jpg": 5, ...},
        "pages": [
          {"page": 1, "count": 2, "formats": ["jpg","png"], "xrefs":[..], "smasks":[..]},
          ...
        ]
      }
    """
    import fitz
    from collections import Counter

    doc = fitz.open(pdf_path)
    try:
        total_pages = doc.page_count
        if total_pages <= 0:
            return {"scanned_pages": 0, "total_pages": 0, "total_images": 0, "formats_count": {}, "pages": []}

        if mode == "sample":
            end = min(sample_pages, total_pages)
            page_range = range(0, end)
        else:
            page_range = range(0, total_pages)

        pages_info = []
        formats_all = []
        total_images = 0

        for i in page_range:
            page = doc.load_page(i)
            images = page.get_images(full=True)  # (xref, smask, w, h, bpc, colorspace, ...)
            cnt = len(images)
            fmts, xrefs, smasks = [], [], []
            if cnt > 0:
                for im in images:
                    xref = im[0]
                    smask = im[1]  # 0 or xref
                    try:
                        meta = doc.extract_image(xref)
                        ext = (meta.get("ext") or "bin").lower()
                    except Exception:
                        ext = "bin"
                    fmts.append(ext)
                    xrefs.append(xref)
                    smasks.append(smask)
                    formats_all.append(ext)
                total_images += cnt

            pages_info.append({"page": i + 1, "count": cnt, "formats": fmts, "xrefs": xrefs, "smasks": smasks})

        formats_count = dict(Counter(formats_all))
        return {
            "scanned_pages": len(page_range),
            "total_pages": total_pages,
            "total_images": total_images,
            "formats_count": formats_count,
            "pages": pages_info
        }
    finally:
        doc.close()

# ========== テキスト抽出解析 ==========
@st.cache_data(show_spinner=True)
def analyze_pdf_texts(
    pdf_path: str,
    mtime_ns: int,
    mode: str = "all",
    sample_pages: int = 6
) -> Dict[str, Any]:
    """
    PDF内のテキストを抽出して返す（ページごとに冒頭500文字までプレビュー）。
    """
    import fitz
    doc = fitz.open(pdf_path)
    try:
        total_pages = doc.page_count
        if total_pages <= 0:
            return {"scanned_pages": 0, "total_pages": 0, "pages": []}

        if mode == "sample":
            end = min(sample_pages, total_pages)
            page_range = range(0, end)
        else:
            page_range = range(0, total_pages)

        pages_info = []
        for i in page_range:
            page = doc.load_page(i)
            txt = (page.get_text("text") or "").strip()
            # preview = txt[:500] + ("..." if len(txt) > 500 else "")
            # pages_info.append({"page": i + 1, "text": preview})
            pages_info.append({"page": i + 1, "text": txt})

        return {"scanned_pages": len(page_range), "total_pages": total_pages, "pages": pages_info}
    finally:
        doc.close()

def list_pdfs(root: Path) -> List[Path]:
    if not root.exists():
        return []
    return sorted(root.rglob("*.pdf"))

def rel_from(pdf_path: Path, base: Path) -> str:
    try:
        return str(pdf_path.relative_to(base))
    except ValueError:
        return pdf_path.name

# ========== UI ==========
st.set_page_config(page_title="PDF ビューア", page_icon="📄", layout="wide")
st.title("📄 PDF ビューア")

with st.sidebar:
    st.header("設定")
    pdf_root_str = st.text_input("PDF ルートフォルダ", value=str(PDF_ROOT_DEFAULT))
    pdf_root = Path(pdf_root_str).expanduser().resolve()

    c1, c2 = st.columns(2)
    with c1:
        grid_cols = st.number_input("グリッド列数", 2, 8, 4, 1)
    with c2:
        thumb_px = st.number_input("サムネ幅(px)", 120, 600, 260, 20)

    st.divider()
    name_filter = st.text_input("ファイル名フィルタ（部分一致）", value="").strip()
    year_filter = st.text_input("年フォルダフィルタ（例: 2024,2025）", value="").strip()

    st.divider()
    st.subheader("ビューア表示")
    viewer_width  = st.slider("幅(px)", 600, 1400, 900, 20)
    viewer_height = st.slider("高さ(px)", 400, 1400, 820, 20)

    viewer_choices = ["Streamlit内蔵（st.pdf）"]
    if HAS_PDFJS:
        viewer_choices.append("pdf.js（streamlit_pdf_viewer）")
    viewer_choices.append("ブラウザPDFプラグイン")
    viewer_mode = st.radio("方式", viewer_choices, index=0)

    zoom_preset = st.selectbox("初期倍率（プラグイン時）", ["page-fit", "page-width", "100", "125", "75"], index=0)

    st.divider()
    st.subheader("解析範囲")
    scan_mode_label = st.radio("調査方式", ["全ページを調査", "先頭Nページのみ調査"], index=0)
    if scan_mode_label == "先頭Nページのみ調査":
        scan_sample_pages = st.slider("先頭Nページ", 1, 50, 6, 1)
        scan_mode = "sample"
    else:
        scan_sample_pages = 6
        scan_mode = "all"

    st.divider()
    st.subheader("埋め込み画像の出力設定")
    show_embedded_images = st.checkbox("埋め込み画像を表示する", value=False)
    extract_mode = st.radio(
        "抽出モード",
        ["XObjectそのまま（真の埋め込み画像）", "ページ見た目サイズで再サンプリング"],
        index=0,
        help="前者はPDFに埋め込まれた元画像をそのまま（小さい場合あり）。後者はページ上の見た目サイズで切出し。"
    )
    resample_dpi = st.slider("再サンプリング時のDPI", 72, 300, 144, 12, help="抽出モードが再サンプリングの時のみ有効")

if "pdf_selected" not in st.session_state:
    st.session_state.pdf_selected = None

# ========== データ取得 ==========
pdf_paths = list_pdfs(pdf_root)
if name_filter:
    pdf_paths = [p for p in pdf_paths if name_filter.lower() in p.name.lower()]
if year_filter:
    years = {y.strip() for y in year_filter.split(",") if y.strip()}
    if years:
        def _has_year(p: Path) -> bool:
            parts = p.relative_to(pdf_root).parts
            return any(part in years for part in parts[:2])
        pdf_paths = [p for p in pdf_paths if _has_year(p)]

if not pdf_paths:
    st.info("PDF が見つかりません。")
    st.stop()

left, right = st.columns([2, 3], gap="large")

# ========== 左：サムネ ==========
with left:
    st.subheader("📚 サムネイル")
    rows = (len(pdf_paths) + grid_cols - 1) // grid_cols
    idx = 0
    for _ in range(rows):
        cols = st.columns(grid_cols)
        for c in range(grid_cols):
            if idx >= len(pdf_paths):
                break
            p = pdf_paths[idx]; idx += 1
            rel = rel_from(p, pdf_root)
            mtime_ns = p.stat().st_mtime_ns

            try:
                png = render_thumb_png(str(p), int(thumb_px), mtime_ns)
                cols[c].image(png, caption=rel, width="stretch")
            except Exception as e:
                cols[c].warning(f"サムネ生成失敗: {rel}\n{e}")

            try:
                info = quick_pdf_info(str(p), mtime_ns)
                cols[c].markdown(
                    f"<div style='font-size:12px;color:#555;'>🧾 <b>{info['kind']}</b>・📄 {info['pages']}ページ</div>",
                    unsafe_allow_html=True,
                )
            except Exception:
                cols[c].markdown("<div style='font-size:12px;color:#555;'>🧾 種別不明・📄 ページ数不明</div>", unsafe_allow_html=True)

            if cols[c].button("👁 開く", key=f"open_{rel}", width="stretch"):
                st.session_state.pdf_selected = rel

# ========== 右：ビューア ==========
with right:
    st.subheader("👁 ビューア")
    current_rel = st.session_state.pdf_selected or rel_from(pdf_paths[0], pdf_root)
    current_abs = (pdf_root / current_rel).resolve()
    st.write(f"**{current_rel}**")

    if not current_abs.exists():
        st.error("選択されたファイルが見つかりません。")
    else:
        try:
            # ---- 左上バッジに表示するラベル ----
            if viewer_mode == "ブラウザPDFプラグイン":
                zoom_label = f"倍率: {zoom_preset}"
            elif viewer_mode == "Streamlit内蔵（st.pdf）":
                zoom_label = "倍率: 可変（st.pdf）"
            else:
                zoom_label = "倍率: 可変（pdf.js）"

            # ---- 方式ごとの表示 ----
            if viewer_mode == "Streamlit内蔵（st.pdf）":
                st.markdown(
                    f"""
                    <div style="position:relative; height:0;">
                      <div style="position:absolute; left:0; top:-4px; background:#111827; color:#fff;
                                  font-size:12px; padding:4px 8px; border-radius:6px; box-shadow:0 1px 4px rgba(0,0,0,.15);">
                        {zoom_label}
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                data = read_pdf_bytes(str(current_abs), current_abs.stat().st_mtime_ns)
                st.pdf(data, height=int(viewer_height), key=f"stpdf_{current_rel}")

            elif viewer_mode.startswith("pdf.js") and HAS_PDFJS:
                st.markdown(
                    f"""
                    <div style="position:relative; height:0;">
                      <div style="position:absolute; left:0; top:-4px; background:#111827; color:#fff;
                                  font-size:12px; padding:4px 8px; border-radius:6px; box-shadow:0 1px 4px rgba(0,0,0,.15);">
                        {zoom_label}
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                data = read_pdf_bytes(str(current_abs), current_abs.stat().st_mtime_ns)
                pdf_viewer(data, width=int(viewer_width), height=int(viewer_height), key=f"pdfjs_{current_rel}")

            else:
                b64 = read_pdf_b64(str(current_abs), current_abs.stat().st_mtime_ns)
                st.components.v1.html(
                    f"""
                    <div style="position:relative; border:1px solid #e5e7eb;border-radius:8px;overflow:hidden">
                      <div style="position:absolute; left:8px; top:8px; background:#111827; color:#fff;
                                  font-size:12px; padding:4px 8px; border-radius:6px; box-shadow:0 1px 4px rgba(0,0,0,.15);">
                        {zoom_label}
                      </div>
                      <object data="data:application/pdf;base64,{b64}#zoom={zoom_preset}"
                              type="application/pdf" width="{int(viewer_width)}" height="{int(viewer_height)}">
                        <p>PDF を表示できません。下のボタンでダウンロードしてください。</p>
                      </object>
                    </div>
                    """,
                    height=int(viewer_height) + 16,
                )

            # DLボタン（共通）
            with open(current_abs, "rb") as f:
                st.download_button("📥 このPDFをダウンロード", data=f.read(), file_name=current_abs.name, mime="application/pdf")

            # ========== 画像埋め込み情報 ==========
            st.divider()
            st.subheader("🖼 画像埋め込み情報")
            img_info = analyze_pdf_images(str(current_abs), current_abs.stat().st_mtime_ns, mode=scan_mode, sample_pages=int(scan_sample_pages))

            c = st.columns(4)
            c[0].metric("走査ページ数", f"{img_info['scanned_pages']}/{img_info['total_pages']}")
            c[1].metric("画像総数", f"{img_info['total_images']}")
            if img_info["formats_count"]:
                formats_sorted = sorted(img_info["formats_count"].items(), key=lambda x: x[1], reverse=True)
                top_fmt = ", ".join([f"{k}:{v}" for k, v in formats_sorted[:2]])
                rest_total = sum(v for _, v in formats_sorted[2:])
                c[2].metric("形式の上位", top_fmt or "-")
                c[3].metric("他形式の合計", str(rest_total))
            else:
                c[2].metric("形式の上位", "-")
                c[3].metric("他形式の合計", "0")

            with st.expander("ページ別の詳細（形式と枚数）", expanded=False):
                lines = []
                for row in img_info["pages"]:
                    fmts = ", ".join(row["formats"]) if row["formats"] else "-"
                    lines.append(f"p.{row['page']:>4}: 画像 {row['count']:>3} 枚｜形式 [{fmts}]")
                st.text("\n".join(lines) if lines else "（画像は検出されませんでした）")

            # ========== 埋め込み画像の抽出＆表示（モード切替＋ZIP出力） ==========
            if show_embedded_images and img_info["total_images"] > 0:
                with st.expander("埋め込み画像を表示 / ダウンロード", expanded=False):
                    import fitz

                    def human_size(n: int) -> str:
                        units = ["B", "KB", "MB", "GB", "TB"]
                        size = float(n)
                        for u in units:
                            if size < 1024 or u == units[-1]:
                                return f"{size:.0f} {u}" if u == "B" else f"{size:.1f} {u}"
                            size /= 1024

                    def export_xobject_png(doc: fitz.Document, xref: int, smask: int):
                        """XObject（真の埋め込み画像）を PNG(RGB/RGBA) に正規化して返す。"""
                        pix = fitz.Pixmap(doc, xref)
                        # 多チャンネル（CMYK等）→ RGB
                        if pix.n > 4 and pix.alpha == 0:
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                        # SMask 合成
                        if smask and smask > 0:
                            m = fitz.Pixmap(doc, smask)
                            pix = fitz.Pixmap(pix, m)
                        return pix.tobytes("png"), pix.width, pix.height

                    def export_resampled_png(page: "fitz.Page", rect: "fitz.Rect", dpi: int):
                        """ページ上の見た目サイズで切り出してPNG化（視覚的抽出）。"""
                        mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
                        pm = page.get_pixmap(clip=rect, matrix=mat, alpha=False)
                        return pm.tobytes("png"), pm.width, pm.height

                    # 実PDFを開く
                    doc = fitz.open(str(current_abs))
                    zip_buf = io.BytesIO()
                    zf = zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED)

                    try:
                        for row in img_info["pages"]:
                            if row["count"] == 0:
                                continue
                            pno = row["page"]
                            st.markdown(f"**p.{pno} の画像**")
                            page = doc.load_page(pno - 1)
                            smasks = row.get("smasks", [0] * len(row["xrefs"]))
                            cols = st.columns(min(3, max(1, row["count"])))
                            col_idx = 0

                            for idx_in_page, (xref, smask) in enumerate(zip(row["xrefs"], smasks), start=1):
                                try:
                                    if extract_mode.startswith("XObject"):
                                        png_bytes, w, h = export_xobject_png(doc, xref, smask)
                                        label = f"XObject {w}×{h}（{human_size(len(png_bytes))}）"
                                        fname = f"p{pno:03d}_img{idx_in_page:02d}_x{xref}.png"
                                    else:
                                        rects = []
                                        try:
                                            rects = page.get_image_rects(xref)
                                        except Exception:
                                            rects = []
                                        if rects:
                                            # 1つの xref が複数回描画されることがある → すべて出す
                                            for rep_idx, r in enumerate(rects, start=1):
                                                png_bytes, w, h = export_resampled_png(page, r, resample_dpi)
                                                label = f"切出し {w}×{h}（{human_size(len(png_bytes))}）"
                                                fname = f"p{pno:03d}_img{idx_in_page:02d}_rep{rep_idx}_x{xref}.png"
                                                cols[col_idx % 3].image(png_bytes, caption=label, width="stretch")
                                                zf.writestr(fname, png_bytes)
                                                col_idx += 1
                                            # 続きへ（rep毎に描画済）
                                            continue
                                        else:
                                            # 矩形が取得できない場合はフォールバックでXObject抽出
                                            png_bytes, w, h = export_xobject_png(doc, xref, smask)
                                            label = f"XObject {w}×{h}（{human_size(len(png_bytes))}）"
                                            fname = f"p{pno:03d}_img{idx_in_page:02d}_x{xref}.png"

                                    # ここに来るのは XObject抽出（またはフォールバック）
                                    cols[col_idx % 3].image(png_bytes, caption=label, width="stretch")
                                    zf.writestr(fname, png_bytes)
                                    col_idx += 1

                                except Exception as e:
                                    cols[col_idx % 3].warning(f"画像抽出失敗: {e}")
                                    col_idx += 1

                    finally:
                        zf.close()
                        doc.close()

                    st.download_button(
                        "🗜 抽出画像をZIPでダウンロード",
                        data=zip_buf.getvalue(),
                        file_name=f"{current_abs.stem}_images.zip",
                        mime="application/zip"
                    )

            # ========== テキスト抽出情報 ==========
            st.divider()
            st.subheader("📝 抽出テキスト（get_textの抽出：OCRは行っていない）")
            text_info = analyze_pdf_texts(str(current_abs), current_abs.stat().st_mtime_ns, mode=scan_mode, sample_pages=int(scan_sample_pages))
            st.write(f"走査ページ数: {text_info['scanned_pages']}/{text_info['total_pages']}")
            if not text_info["pages"]:
                st.info("テキストが抽出できませんでした。")
            else:
                with st.expander("ページごとの抽出テキスト（各ページ冒頭500文字）", expanded=False):
                    for row in text_info["pages"]:
                        st.markdown(f"**p.{row['page']}**")
                        st.text(row["text"])

        except Exception as e:
            st.error(f"PDF 表示に失敗しました: {e}")
