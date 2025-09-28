# pages/20_PDF_OCR変換.py
# ------------------------------------------------------------
# 🧾 画像PDF → テキストPDF 一括変換（OCR）＋ 全PDFのテキスト(.txt)保存
# - data/pdf/<year>/*.pdf を走査
#   1) 画像PDFのみ OCR → data/converted_pdf/<year>/<元名>_converted.pdf
#   2) 全PDFについてテキスト(.txt)を data/text/<year>/<対象名>.txt に保存
#      - すでに .txt がある場合はスキップ
#      - *_converted.pdf はそのファイル自身からテキスト抽出
#      - 元pdf に対して converted が存在する場合は converted 側から抽出
# - ocrmypdf は Python API 優先、無ければ CLI
# - force_ocr / rotate_pages を常に有効化（必ずテキスト層を作る）
# ------------------------------------------------------------
from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any, Tuple
import shutil
import subprocess

import streamlit as st

APP_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = APP_ROOT / "data"
SRC_ROOT_DEFAULT = DATA_DIR / "pdf"
DST_ROOT_DEFAULT = DATA_DIR / "converted_pdf"
TXT_ROOT_DEFAULT = DATA_DIR / "text"

# ========= 画像PDFかどうかの軽量判定 =========
@st.cache_data(show_spinner=False)
def pdf_quick_info(pdf_path: str, mtime_ns: int, sample_pages: int = 6, text_ratio_threshold: float = 0.3) -> Dict[str, Any]:
    import fitz
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return {"pages": 0, "kind": "画像PDF", "text_ratio": 0.0}
    try:
        n = doc.page_count
        check = min(sample_pages, max(n, 1))
        text_pages = 0
        for i in range(check):
            try:
                p = doc.load_page(i)
                txt = (p.get_text("text") or "").strip()
                if len(txt) >= 20:
                    text_pages += 1
            except Exception:
                pass
        ratio = text_pages / max(check, 1)
        kind = "テキストPDF" if ratio >= text_ratio_threshold else "画像PDF"
        return {"pages": n, "kind": kind, "text_ratio": ratio}
    finally:
        doc.close()

# ========= OCR 実行（Python API → CLI フォールバック） =========
def _run_ocrmypdf_python(src: Path, dst: Path, *, lang: str, optimize: int, jobs: int,
                         rotate_pages: bool, sidecar_path: Path | None) -> None:
    import ocrmypdf
    kwargs = dict(
        language=lang,
        output_type="pdf",
        optimize=optimize,
        deskew=True,
        clean=True,
        progress_bar=False,
        jobs=jobs,
        force_ocr=True,       # 🔑 常にOCR
        skip_text=False,
    )
    if rotate_pages:
        kwargs["rotate_pages"] = True
    if sidecar_path is not None:
        kwargs["sidecar"] = str(sidecar_path)

    ocrmypdf.ocr(str(src), str(dst), **kwargs)

def _run_ocrmypdf_cli(src: Path, dst: Path, *, lang: str, optimize: int, jobs: int,
                      rotate_pages: bool, sidecar_path: Path | None) -> None:
    exe = shutil.which("ocrmypdf")
    if not exe:
        raise RuntimeError("ocrmypdf が見つかりません。")
    cmd = [
        exe,
        "--language", lang,
        "--output-type", "pdf",
        "--deskew", "--clean",
        "--optimize", str(optimize),
        "--jobs", str(jobs),
        "--force-ocr",         # 🔑 常にOCR
    ]
    if rotate_pages:
        cmd.append("--rotate-pages")
    if sidecar_path is not None:
        cmd.extend(["--sidecar", str(sidecar_path)])
    cmd.extend([str(src), str(dst)])

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(res.stderr or res.stdout or "ocrmypdf 実行に失敗しました。")

def run_ocr(src: Path, dst: Path, *, lang: str, optimize: int = 1, jobs: int = 2,
            rotate_pages: bool = True, sidecar_path: Path | None = None) -> None:
    try:
        _run_ocrmypdf_python(src, dst, lang=lang, optimize=optimize, jobs=jobs,
                             rotate_pages=rotate_pages, sidecar_path=sidecar_path)
    except Exception:
        _run_ocrmypdf_cli(src, dst, lang=lang, optimize=optimize, jobs=jobs,
                          rotate_pages=rotate_pages, sidecar_path=sidecar_path)

# ========= テキスト抽出 =========
def extract_text_pdf(p_pdf: Path, sidecar: Path | None = None) -> str:
    import fitz
    text = ""
    try:
        doc = fitz.open(str(p_pdf))
        parts = []
        for i in range(doc.page_count):
            txt = doc.load_page(i).get_text("text") or ""
            parts.append(txt)
        text = "\n".join(parts).strip()
    except Exception:
        text = ""
    finally:
        if 'doc' in locals():
            doc.close()

    if not text and sidecar and sidecar.exists():
        text = sidecar.read_text(encoding="utf-8", errors="ignore").strip()
    return text

def write_text_file(txt_path: Path, content: str) -> None:
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    with txt_path.open("w", encoding="utf-8") as f:
        f.write(content)

# ========= ユーティリティ =========
def rel_from(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return path.name

def iter_pdfs(root: Path) -> List[Path]:
    if not root.exists():
        return []
    return sorted(root.rglob("*.pdf"))

def make_converted_path(src_path: Path, src_root: Path, dst_root: Path) -> Path:
    rel = src_path.relative_to(src_root) if src_path.is_relative_to(src_root) else Path(src_path.name)
    converted_name = f"{src_path.stem}_converted.pdf"
    return (dst_root / rel).with_name(converted_name)

def make_text_path(source_pdf: Path, src_root: Path, dst_root: Path, txt_root: Path) -> Path:
    try:
        rel = source_pdf.relative_to(src_root)
        base = txt_root / rel
    except ValueError:
        try:
            rel = source_pdf.relative_to(dst_root)
            base = txt_root / rel
        except ValueError:
            base = txt_root / source_pdf.name
    return base.with_suffix(".txt")

# ========= UI =========
st.set_page_config(page_title="画像PDF → テキストPDF 変換", page_icon="🧾", layout="wide")
st.title("🧾 画像PDF → テキストPDF 変換（OCR）＋ 全PDFテキスト保存")

with st.sidebar:
    st.header("対象と出力")
    src_root = Path(st.text_input("入力フォルダ", value=str(SRC_ROOT_DEFAULT))).expanduser().resolve()
    dst_root = Path(st.text_input("変換PDF出力フォルダ", value=str(DST_ROOT_DEFAULT))).expanduser().resolve()
    txt_root = Path(st.text_input("テキスト出力フォルダ", value=str(TXT_ROOT_DEFAULT))).expanduser().resolve()

    st.subheader("フィルタ（任意）")
    name_filter = st.text_input("ファイル名フィルタ", value="").strip()
    year_filter = st.text_input("年フォルダ（例: 2024,2025）", value="").strip()

    st.subheader("OCR 設定")
    lang = st.text_input("言語（tesseract langs）", value="jpn+eng")
    optimize = st.select_slider("最適化（圧縮）", options=[0, 1, 2, 3], value=1)
    jobs = st.slider("並列ジョブ数", min_value=1, max_value=8, value=2, step=1)
    rotate_pages = st.checkbox("自動回転補正", value=True)
    save_sidecar = st.checkbox("sidecar 保存", value=True)

    overwrite_pdf = st.checkbox("変換PDFを上書き再変換", value=False)
    do_text_export = st.checkbox("全PDFをテキスト保存", value=True)

    st.divider()
    st.subheader("環境チェック")
    ocrmypdf_ok = (shutil.which("ocrmypdf") is not None)
    tesseract_ok = (shutil.which("tesseract") is not None)
    try:
        import ocrmypdf as _m
        ocrmypdf_py = True
    except Exception:
        ocrmypdf_py = False
    st.write(f"ocrmypdf (Python): {'✅' if ocrmypdf_py else '❌'}")
    st.write(f"ocrmypdf (CLI)   : {'✅' if ocrmypdf_ok else '❌'}")
    st.write(f"tesseract        : {'✅' if tesseract_ok else '❌'}")

# 入力ファイル列挙
src_files = iter_pdfs(src_root)
if name_filter:
    src_files = [p for p in src_files if name_filter.lower() in p.name.lower()]
if year_filter:
    years = {y.strip() for y in year_filter.split(",") if y.strip()}
    if years:
        src_files = [p for p in src_files if any(part in years for part in p.relative_to(src_root).parts[:2])]
if not src_files:
    st.warning("対象PDFが見つかりません。")
    st.stop()

# OCR対象リスト作成
rows: List[Dict[str, Any]] = []
with st.spinner("判定中…"):
    for p in src_files:
        if p.stem.endswith("_converted"):
            continue
        info = pdf_quick_info(str(p), p.stat().st_mtime_ns)
        if info["kind"] != "画像PDF":
            continue
        out_path = make_converted_path(p, src_root, dst_root)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        status = "未変換"
        if out_path.exists():
            status = "出力あり（スキップ）" if not overwrite_pdf else "上書き対象"
        rows.append({"src_rel": rel_from(p, src_root), "dst_rel": rel_from(out_path, dst_root),
                     "pages": info["pages"], "status": status, "src": p, "dst": out_path})

if rows:
    st.markdown(f"### OCR 対象: {len(rows)} 件")
    st.dataframe([{"入力": r["src_rel"], "出力": r["dst_rel"], "pages": r["pages"], "status": r["status"]} for r in rows])

# 実行
do_convert = st.button("🧾 OCR 実行", type="primary")
if do_convert:
    ok, ng, skip = 0, 0, 0
    logs: List[str] = []
    for r in rows:
        src, dst = r["src"], r["dst"]
        if dst.exists() and not overwrite_pdf:
            skip += 1
            logs.append(f"⏭️ スキップ: {r['src_rel']}")
            continue
        try:
            sidecar_path = dst.with_suffix(".sidecar.txt") if save_sidecar else None
            run_ocr(src, dst, lang=lang, optimize=int(optimize), jobs=int(jobs),
                    rotate_pages=rotate_pages, sidecar_path=sidecar_path)
            ok += 1
            logs.append(f"✅ 完了: {r['src_rel']}")
        except Exception as e:
            ng += 1
            logs.append(f"❌ 失敗: {r['src_rel']} : {e}")
    st.success(f"OCR 完了: 成功 {ok} / 失敗 {ng} / スキップ {skip}")
    st.write("\n".join(logs))

    # 全PDFテキスト保存
    if do_text_export:
        text_ok, text_skip, text_ng = 0, 0, 0
        for p in src_files:
            # 元 or converted を選択
            if p.stem.endswith("_converted"):
                spdf = p
            else:
                conv = make_converted_path(p, src_root, dst_root)
                spdf = conv if conv.exists() else p
            txt_path = make_text_path(spdf, src_root, dst_root, txt_root)
            if txt_path.exists():
                text_skip += 1
                continue
            sidecar = spdf.with_suffix(".sidecar.txt")
            txt = extract_text_pdf(spdf, sidecar)
            if txt:
                write_text_file(txt_path, txt)
                text_ok += 1
            else:
                text_ng += 1
        st.success(f"テキスト保存: 成功 {text_ok} / スキップ {text_skip} / 失敗 {text_ng}")
