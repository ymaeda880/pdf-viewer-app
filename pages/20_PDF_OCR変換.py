# pages/20_PDF_OCR変換.py
# ------------------------------------------------------------
# 🧾 画像PDF → テキストPDF 一括変換（OCR）＋ 全PDFのテキスト(.txt)保存
#  PDF処理ロジックは lib/pdf_tools.py に分離
# ------------------------------------------------------------
from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any

import streamlit as st
from lib.pdf_tools import (
    quick_pdf_info, run_ocr, extract_text_pdf, write_text_file,
    rel_from, iter_pdfs, make_converted_path, make_text_path, env_checks
)

APP_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = APP_ROOT / "data"
SRC_ROOT_DEFAULT = DATA_DIR / "pdf"
DST_ROOT_DEFAULT = DATA_DIR / "converted_pdf"
TXT_ROOT_DEFAULT = DATA_DIR / "text"

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
    env = env_checks()
    st.write(f"ocrmypdf (Python): {'✅' if env['ocrmypdf_py'] else '❌'}")
    st.write(f"ocrmypdf (CLI)   : {'✅' if env['ocrmypdf_cli'] else '❌'}")
    st.write(f"tesseract        : {'✅' if env['tesseract'] else '❌'}")

# 入力ファイル列挙
src_files = iter_pdfs(src_root)
if name_filter:
    src_files = [p for p in src_files if name_filter.lower() in p.name.lower()]
if year_filter:
    years = {y.strip() for y in year_filter.split(",") if y.strip()}
    if years:
        src_files = [
            p for p in src_files
            if any(part in years for part in p.relative_to(src_root).parts[:2])
        ]

if not src_files:
    st.warning("対象PDFが見つかりません。")
    st.stop()

# OCR対象リスト
rows: List[Dict[str, Any]] = []
with st.spinner("判定中…"):
    for p in src_files:
        if p.stem.endswith("_converted"):
            continue
        info = quick_pdf_info(str(p), p.stat().st_mtime_ns)
        if info["kind"] != "画像PDF":
            continue
        out_path = make_converted_path(p, src_root, dst_root)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        status = "未変換"
        if out_path.exists():
            status = "出力あり（スキップ）" if not overwrite_pdf else "上書き対象"
        rows.append({
            "src_rel": rel_from(p, src_root),
            "dst_rel": rel_from(out_path, dst_root),
            "pages": info["pages"],
            "status": status,
            "src": p,
            "dst": out_path
        })

if rows:
    st.markdown(f"### OCR 対象: {len(rows)} 件")
    st.dataframe([
        {"入力": r["src_rel"], "出力": r["dst_rel"], "pages": r["pages"], "status": r["status"]}
        for r in rows
    ])

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
            run_ocr(
                src, dst,
                lang=lang, optimize=int(optimize), jobs=int(jobs),
                rotate_pages=rotate_pages, sidecar_path=sidecar_path
            )
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
            spdf = p if p.stem.endswith("_converted") else (
                make_converted_path(p, src_root, dst_root)
            )
            if not spdf.exists():
                spdf = p
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
