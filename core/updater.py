"""업데이트 체크 + 자동 교체.

ImageReactor의 검증된 updater 로직을 거의 그대로 가져왔다. 관리자 권한과
무관한 흐름이라 우리(uac_admin=False) 환경에서도 그대로 동작한다.

핵심:
    check_latest_release()  — GitHub Releases 에서 최신 exe 릴리즈 정보 반환
    download_exe(url, dest) — 진행률 콜백과 함께 임시 위치에 다운로드
    apply_update(new_exe)   — 배치 스크립트로 현재 exe 교체 + explorer.exe 재실행

흐름:
    1) 현재 exe 옆에 새 exe 다운로드 (FCMS_new.exe)
    2) 배치 파일 생성: 현재 PID 종료 대기 → move /Y로 rename → explorer.exe 재실행
    3) sys.exit(0)으로 현재 프로세스 종료 → 배치가 교체 진행
"""

from __future__ import annotations

import json
import os
import ssl
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()

from version import APP_VERSION, GITHUB_REPO

API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
ALL_RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"

_USER_AGENT = "FCMS-Updater/1.0"


# ──────────────────────────────────────────
# 버전 파싱/비교
# ──────────────────────────────────────────

def _parse_version(v: str) -> tuple[int, ...]:
    """'v0.1.0', 'V0.1.0', '0.1.0' → (0, 1, 0)"""
    v = v.strip().lstrip("vV")
    parts = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            break
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_newer(remote_tag: str, current: str = APP_VERSION) -> bool:
    return _parse_version(remote_tag) > _parse_version(current)


# ──────────────────────────────────────────
# GitHub API
# ──────────────────────────────────────────

def _extract_exe_asset(assets: list) -> dict | None:
    """release assets 리스트에서 FCMS exe asset 추출. 없으면 None."""
    for a in assets:
        name: str = a.get("name", "")
        if name.lower().endswith(".exe") and "fcms" in name.lower():
            return {
                "name": name,
                "url": a["browser_download_url"],
                "size": a.get("size", 0),
            }
    return None


def check_latest_release(timeout: int = 15) -> dict | None:
    """자동 업데이트용 최신 릴리즈 정보 반환.

    반환:
        {
          tag_name: str,
          html_url: str,
          body: str,
          exe_asset: {name, url, size},
        }

    동작:
        /releases 로 published_at 내림차순 모든 릴리즈 조회. 그 중
        'exe asset 첨부 + prerelease/draft 아님' 인 가장 최근 릴리즈 반환.

    네트워크 오류 시 None 반환. 실패 원인은 check_latest_release.last_error 에 저장.
    """
    check_latest_release.last_error = ""
    try:
        req = Request(ALL_RELEASES_URL, headers={"User-Agent": _USER_AGENT})
        with urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            releases = json.loads(resp.read().decode())

        for rel in releases:
            if rel.get("prerelease", False) or rel.get("draft", False):
                continue
            exe_asset = _extract_exe_asset(rel.get("assets", []) or [])
            if exe_asset is None:
                continue
            return {
                "tag_name": rel.get("tag_name", ""),
                "html_url": rel.get("html_url", RELEASES_URL),
                "body": rel.get("body", ""),
                "exe_asset": exe_asset,
            }
        return None
    except Exception as e:
        err = str(e)
        check_latest_release.last_error = err
        print(f"[updater] 업데이트 확인 실패: {err}")
        return None


check_latest_release.last_error = ""


# ──────────────────────────────────────────
# 다운로드
# ──────────────────────────────────────────

def download_exe(url: str, dest: Path, progress_cb=None,
                 expected_size: int = 0) -> None:
    """exe를 dest에 다운로드.
    progress_cb(downloaded_bytes: int, total_bytes: int) — 선택
    expected_size > 0 이면 다운로드 완료 후 크기 검증. 불일치 시 손상된 dest 삭제 + IOError.
    """
    req = Request(url, headers={"User-Agent": _USER_AGENT})
    with urlopen(req, timeout=120, context=_SSL_CTX) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        downloaded = 0
        chunk_size = 65536
        with open(dest, "wb") as f:
            while True:
                buf = resp.read(chunk_size)
                if not buf:
                    break
                f.write(buf)
                downloaded += len(buf)
                if progress_cb:
                    progress_cb(downloaded, total)

    if expected_size > 0:
        try:
            actual = dest.stat().st_size
        except Exception:
            actual = -1
        if actual != expected_size:
            try:
                dest.unlink()
            except Exception:
                pass
            raise IOError(
                f"다운로드 크기 불일치: 예상 {expected_size:,} 실제 {actual:,}"
            )


# ──────────────────────────────────────────
# 자동 교체 (frozen exe 전용)
# ──────────────────────────────────────────

def apply_update(new_exe: Path) -> None:
    """배치 스크립트로 현재 exe를 새 버전으로 교체 + 재시작.

    성공 시 이 함수는 반환하지 않는다 (sys.exit). frozen 환경에서만 동작.

    핵심 설계 (ImageReactor 검증된 패턴):
      1) 파일 교체는 `move` (같은 볼륨 rename). 실행 중 .exe는 del은
         막히지만 rename은 Windows가 허용.
      2) 재실행은 `explorer.exe` — onefile 부트로더의 _MEIPASS2 미상속으로
         구 프로세스 트리와 분리. 삭제 중인 구 _MEI 참조 crash 회피.
      3) PID 종료 대기는 `tasklist` + `ping` (콘솔 불필요). 단일 인스턴스
         락 해제 + 구 _MEI 정리 후 재실행 보장 (상한 도달 시도 진행).
      4) 교체 전 잔존 _old.exe 선삭제로 rename 충돌 방지.
    """
    if not getattr(sys, "frozen", False):
        raise RuntimeError("개발 환경에서는 자동 교체를 지원하지 않습니다.")

    current_exe = Path(sys.executable).resolve()
    old_exe = current_exe.with_name(current_exe.stem + "_old.exe")
    bat_path = current_exe.parent / "_fcms_update.bat"
    pid = os.getpid()

    bat = (
        "@echo off\n"
        "setlocal ENABLEDELAYEDEXPANSION\n"
        "set WAITN=0\n"
        ":wait\n"
        f'tasklist /FI "PID eq {pid}" 2>NUL | find /I "{pid}" >NUL\n'
        "if not errorlevel 1 (\n"
        "    set /a WAITN+=1\n"
        "    if !WAITN! gtr 150 goto swap\n"
        "    ping -n 2 127.0.0.1 >NUL\n"
        "    goto wait\n"
        ")\n"
        ":swap\n"
        f'del /F /Q "{old_exe}" >NUL 2>&1\n'
        f'move /Y "{current_exe}" "{old_exe}" >NUL 2>&1\n'
        f'move /Y "{new_exe}" "{current_exe}" >NUL 2>&1\n'
        f'if not exist "{current_exe}" goto end\n'
        f'explorer.exe "{current_exe}"\n'
        f'del /F /Q "{old_exe}" >NUL 2>&1\n'
        ":end\n"
        "endlocal\n"
        'del "%~f0"\n'
    )
    bat_path.write_text(bat, encoding="mbcs")

    subprocess.Popen(
        ["cmd", "/c", str(bat_path)],
        creationflags=subprocess.CREATE_NO_WINDOW,
        close_fds=True,
    )
    sys.exit(0)
