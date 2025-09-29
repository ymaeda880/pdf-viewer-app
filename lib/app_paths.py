# lib/app_paths.py
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, Optional
import os

# --- optional: Streamlit is not required ---
try:
    import streamlit as st  # noqa: F401
except Exception:
    st = None  # 非Streamlit環境でもOK

# --- toml loader (3.11+: tomllib / fallback: tomli) ---
try:  # Python 3.11+
    import tomllib as _toml
except Exception:  # 3.10以下など
    try:
        import tomli as _toml  # type: ignore
    except Exception:
        _toml = None  # toml 読み込み不可

APP_ROOT = Path(__file__).resolve().parents[1]

# ============= ユーティリティ =============

def _load_toml(path: Path) -> Dict[str, Any]:
    """
    TOML を辞書で返す。存在しない/読めない場合は空 dict。
    """
    if not path.exists() or not path.is_file() or _toml is None:
        return {}
    try:
        with path.open("rb") as f:
            return dict(_toml.load(f))
    except Exception:
        return {}

def _get_settings_file() -> Path:
    """
    設定ファイルの探索順:
    1) 環境変数 APP_SETTINGS_FILE（絶対/相対どちらでも）
    2) APP_ROOT/config/settings.toml
    """
    env = os.getenv("APP_SETTINGS_FILE")
    if env:
        p = Path(env)
        if not p.is_absolute():
            p = (APP_ROOT / p)
        return p.resolve()
    return (APP_ROOT / "config" / "settings.toml").resolve()

def _resolve(spec: Optional[str], *, mounts: Dict[str, Any], default: Path) -> Path:
    """ project:/ mount:/ 絶対/相対 を実パスへ解決。相対は APP_ROOT 基準。"""
    if not spec:
        return default
    s = str(spec).strip()

    if s.startswith("project:"):
        rel = s.split(":", 1)[1].strip()
        return (APP_ROOT / rel).resolve()

    if s.startswith("mount:"):
        rest = s.split(":", 1)[1].strip()
        if "/" in rest:
            mname, sub = rest.split("/", 1)
            base = mounts.get(mname)
            if base:
                return (Path(str(base)).expanduser() / sub).resolve()
        # mount 名が見つからない等 → 既定
        return default

    p = Path(s)
    if not p.is_absolute():
        p = (APP_ROOT / p)
    return p.resolve()

# ============= 本体クラス =============

class AppPaths:
    """
    config/settings.toml の [env], [mounts], [locations.<env>] を読み込み、
    アプリ内で使う標準パスを提供する。
    - secrets.toml は使わない（APIキー等の秘密のみ別管理）
    - 設定不足時は data/* 配下にフォールバック
    """

    def __init__(self, settings_path: Optional[Path] = None) -> None:
        # 設定ファイルロード
        self.settings_path: Path = settings_path or _get_settings_file()
        self.settings: Dict[str, Any] = _load_toml(self.settings_path)

        # セクション取得（無ければ空）
        env_sec   = dict(self.settings.get("env", {}))
        mounts    = dict(self.settings.get("mounts", {}))
        locs_sec  = dict(self.settings.get("locations", {}))

        # 現在のロケーション（デフォルト "Home"）
        self.env: str = str(env_sec.get("location") or "Home")

        # 基本パス
        self.app_root: Path = APP_ROOT
        self.data_dir: Path = self.app_root / "data"

        # 既定フォールバック
        default_pdf     = self.data_dir / "pdf"
        default_conv    = self.data_dir / "converted_pdf"
        default_text    = self.data_dir / "text"
        default_library = self.data_dir / "library"

        # 現在ロケーションの定義を取得
        cur = locs_sec.get(self.env, {}) if isinstance(locs_sec, dict) else {}

        # 解決
        self.pdf_root       = _resolve(cur.get("pdf_root"),       mounts=mounts, default=default_pdf)
        self.converted_root = _resolve(cur.get("converted_root"), mounts=mounts, default=default_conv)
        self.text_root      = _resolve(cur.get("text_root"),      mounts=mounts, default=default_text)
        self.library_root   = _resolve(cur.get("library_root"),   mounts=mounts, default=default_library)

        # 必要なら自動作成（読み取り専用の外部ディスク等で例外にならないよう exist_ok）
        for p in (self.pdf_root, self.converted_root, self.text_root, self.library_root):
            try:
                p.mkdir(parents=True, exist_ok=True)
            except Exception:
                # 権限や読み取り専用の場合は黙ってスキップ（ログが必要ならここに入れる）
                pass

    def __repr__(self) -> str:
        return (
            "AppPaths(\n"
            f"  env             = {self.env}\n"
            f"  settings_path   = {self.settings_path}\n"
            f"  app_root        = {self.app_root}\n"
            f"  data_dir        = {self.data_dir}\n"
            f"  pdf_root        = {self.pdf_root}\n"
            f"  converted_root  = {self.converted_root}\n"
            f"  text_root       = {self.text_root}\n"
            f"  library_root    = {self.library_root}\n"
            ")"
        )

# 既定インスタンス（そのまま import して使える）
PATHS = AppPaths()
