# pages/13_PDFテキストビューア.py
# ------------------------------------------------------------
# 📄 PDF + テキストビューア（新規ページ）
# - 左に PDF サムネイル
# - 右に PDF ビューア（st.pdf）
# - 同時に text フォルダー内の抽出済みテキストを表示
# ------------------------------------------------------------
from pathlib import Path
import base64
import streamlit as st

import fitz  # PyMuPDF

# ========== パス ==========
APP_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = APP_ROOT / "data"
PDF_ROOT = DATA_DIR / "pdf"
TEXT_ROOT = DATA_DIR / "text"

# ========== サムネ生成 ==========
@st.cache_data(show_spinner=False)
def render_thumb_png(pdf_path: str, thumb_px: int, mtime_ns: int) -> bytes:
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

# ========== PDF一覧 ==========
def list_pdfs(root: Path):
    if not root.exists():
        return []
    return sorted(root.rglob("*.pdf"))

def rel_from(pdf_path: Path, base: Path) -> str:
    try:
        return str(pdf_path.relative_to(base))
    except ValueError:
        return pdf_path.name

# ========== UI ==========
st.set_page_config(page_title="PDF + テキストビューア", page_icon="📄", layout="wide")
st.title("📄 PDF + テキストビューア")

with st.sidebar:
    st.header("設定")
    pdf_root_str = st.text_input("PDFルートフォルダ", value=str(PDF_ROOT))
    pdf_root = Path(pdf_root_str).expanduser().resolve()

    thumb_px = st.number_input("サムネ幅(px)", 120, 600, 200, 20)
    grid_cols = st.number_input("グリッド列数", 2, 6, 3, 1)

if "pdf_selected" not in st.session_state:
    st.session_state.pdf_selected = None

# PDF一覧取得
pdf_paths = list_pdfs(pdf_root)
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

        # PDF表示
        with open(current_abs, "rb") as f:
            st.pdf(f.read(), height=800, key=f"stpdf_{current_rel}")

        # テキスト表示
        txt_file = TEXT_ROOT / f"{stem}.txt"
        if not txt_file.exists():
            txt_file = TEXT_ROOT / f"{stem}_converted.txt"
        if not txt_file.exists():
            txt_file = TEXT_ROOT / f"{stem}_converted.sidecar.txt"

        st.divider()
        st.subheader("📝 抽出テキスト（OCRが必要な場合はOCRしてテキスト抽出）")
        if txt_file.exists():
            text = txt_file.read_text(encoding="utf-8", errors="ignore")
            st.text_area("テキスト内容", text, height=300)
            st.download_button("📥 テキストをダウンロード", text, file_name=txt_file.name, mime="text/plain")
        else:
            st.info("対応するテキストファイルが見つかりません。")
