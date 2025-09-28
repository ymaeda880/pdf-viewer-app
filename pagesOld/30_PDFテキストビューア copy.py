# pages/13_PDFテキストビューア.py
# ------------------------------------------------------------
# 📄 PDF + テキストビューア（lib/pdf_tools を利用）
# - 左に PDF サムネイル（lib.render_thumb_png）
# - 右に PDF ビューア（st.pdf, lib.read_pdf_bytes）
# - 同時に text フォルダー内の抽出済みテキストを表示（lib.make_text_pathで探索）
# ------------------------------------------------------------
from __future__ import annotations
from pathlib import Path
import streamlit as st

# 互換レイヤ（内部は lib/pdf を再エクスポート）
from lib.pdf_tools import (
    render_thumb_png, read_pdf_bytes,
    iter_pdfs, rel_from, make_text_path
)

# ========== パス ==========
APP_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = APP_ROOT / "data"
PDF_ROOT_DEFAULT = DATA_DIR / "pdf"
CONVERTED_ROOT_DEFAULT = DATA_DIR / "converted_pdf"
TEXT_ROOT_DEFAULT = DATA_DIR / "text"

# ========== UI ==========
st.set_page_config(page_title="PDF + テキストビューア", page_icon="📄", layout="wide")
st.title("📄 PDF + テキストビューア")

with st.sidebar:
    st.header("ルート設定")
    pdf_root = Path(st.text_input("PDFルートフォルダ", value=str(PDF_ROOT_DEFAULT))).expanduser().resolve()
    converted_root = Path(st.text_input("converted PDF ルート", value=str(CONVERTED_ROOT_DEFAULT))).expanduser().resolve()
    text_root = Path(st.text_input("テキスト出力ルート", value=str(TEXT_ROOT_DEFAULT))).expanduser().resolve()

    st.header("表示設定")
    thumb_px = st.number_input("サムネ幅(px)", 120, 600, 200, 20)
    grid_cols = st.number_input("グリッド列数", 2, 6, 3, 1)
    viewer_height = st.slider("PDFビューア高さ(px)", 400, 1400, 800, 20)

if "pdf_selected" not in st.session_state:
    st.session_state.pdf_selected = None

# ========== PDF一覧取得 ==========
pdf_paths = iter_pdfs(pdf_root)
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
                cols[c].image(png, caption=rel, use_container_width=True)
            except Exception as e:
                cols[c].warning(f"サムネ生成失敗: {rel}\n{e}")

            if cols[c].button("👁 開く", key=f"open_{rel}", use_container_width=True):
                st.session_state.pdf_selected = rel

# ========== 右：ビューア & テキスト ==========
with right:
    st.subheader("👁 ビューア & テキスト")
    current_rel = st.session_state.pdf_selected or rel_from(pdf_paths[0], pdf_root)
    current_abs = (pdf_root / current_rel).resolve()
    stem = current_abs.stem

    if not current_abs.exists():
        st.error("選択されたファイルが見つかりません。")
    else:
        st.write(f"**{current_rel}**")

        # PDF表示（lib.read_pdf_bytes）
        try:
            data = read_pdf_bytes(str(current_abs), current_abs.stat().st_mtime_ns)
            st.pdf(data, height=int(viewer_height), key=f"stpdf_{current_rel}")
        except Exception as e:
            st.error(f"PDFの読み込みに失敗しました: {e}")

        # テキスト表示（make_text_path を使って最も自然な出力先を推定）
        # 元PDF or convertedPDF のパスから、text_root 配下の .txt パスを計算
        txt_path = make_text_path(current_abs, pdf_root, converted_root, text_root)

        # 互換: 既存の <stem>.txt / <stem>_converted.txt / <stem>_converted.sidecar.txt も試す
        candidates = [
            txt_path,
            text_root / f"{stem}.txt",
            text_root / f"{stem}_converted.txt",
            text_root / f"{stem}_converted.sidecar.txt",
        ]

        st.divider()
        st.subheader("📝 抽出テキスト（OCR済の .txt があれば表示）")

        chosen = next((p for p in candidates if p.exists()), None)
        if chosen:
            try:
                text = chosen.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                text = "(テキスト読み込みに失敗しました)"
            st.text_area("テキスト内容", text, height=300)
            st.download_button("📥 テキストをダウンロード", text, file_name=chosen.name, mime="text/plain")
            st.caption(f"表示中: {chosen}")
        else:
            st.info("対応するテキストファイルが見つかりません。")
