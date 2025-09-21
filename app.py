# app.py
# ------------------------------------------------------------
# 📄 PDF Viewer (Streamlit, single-purpose)
# - 起動時に pages/61_PDFビューア.py へ自動遷移（対応環境）
# - 非対応環境ではリンクボタンで遷移
# ------------------------------------------------------------
from __future__ import annotations
import streamlit as st
from pathlib import Path

st.set_page_config(page_title="PDF Viewer", page_icon="📄", layout="wide")
st.title("📄 PDF Viewer")

# ここでは最小限のホーム画面だけ用意し、対応環境なら即ページ遷移します
with st.sidebar:
    st.header("ナビゲーション")
    # フォールバック用のリンク（自動遷移できない環境でも使える）
    st.page_link("pages/10_PDFビューア.py", label="📄 PDF ビューアを開く")

# 起動直後に自動で PDF ビューアページへ遷移（対応していないStreamlit版もあるため try 保護）
# Streamlit 1.22+ 目安。古い環境では except に落ちてホーム画面に留まります。
try:
    st.switch_page("pages/61_PDFビューア.py")
except Exception:
    st.info("自動遷移できない環境です。左の『📄 PDF ビューアを開く』から移動してください。")
