"""스탠드얼론 메인 윈도우.

레이아웃:
    [계정 picker 영역] 계정: [드롭다운]  [추가] [삭제] [닉네임 변경]
    [시즌 영역]       시즌: [드롭다운]    [지금 동기화]
    [통계 + 차트]     StatsView
    [footer]          🟢 마지막 동기화: ...

핵심 동작:
    - 계정 picker는 meta.json 기반. 활성 계정 전환시 fc_stats_db는 자동으로
      해당 ouid의 DB 파일을 가리킨다.
    - sync는 별도 스레드. 진행 중 progress modal 표시 (grab 없음).
    - 닉네임 변경은 같은 ouid 유지 (DB 보존). 다른 닉네임의 계정은 '추가'로.
"""

from __future__ import annotations

import re
import threading
from tkinter import messagebox
from typing import Optional

import customtkinter as ctk

from core import accounts, app_state, fc_api, fc_stats, fc_stats_db as db, fc_sync
from ui.stats_view import StatsView
from ui.theme import THEME

PAD = 12
PAD_SMALL = 6
DEFAULT_W, DEFAULT_H = 820, 820
MIN_SIZE = (760, 760)

_GEOM_RE = re.compile(r"^(\d+)x(\d+)([+-]\d+)([+-]\d+)$")


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.configure(fg_color=THEME["APP_BG"])

        self.title("FC 채굴 통계")
        self.minsize(*MIN_SIZE)
        self._apply_initial_geometry()

        self._sync_thread: Optional[threading.Thread] = None
        self._cancel_event = threading.Event()
        self._progress_modal: Optional[ctk.CTkToplevel] = None
        self._progress_label: Optional[ctk.CTkLabel] = None
        self._progress_bar: Optional[ctk.CTkProgressBar] = None
        self._progress_bar_value = 0.0
        self._progress_start_count = 0
        self._progress_poll_alive = False
        self._sync_stats: Optional[fc_sync.SyncStats] = None

        self._account_label_to_ouid: dict[str, str] = {}
        self._season_label_to_id: dict[str, int] = {}
        self._selected_season: Optional[int] = None

        self._build_ui()
        self._refresh_all()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ─────────────────────────────────────────
    # UI 구축
    # ─────────────────────────────────────────

    def _build_ui(self):
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_account_section()
        self._build_season_section()
        self._build_body_section()
        self._build_footer_section()

    def _build_account_section(self):
        frame = ctk.CTkFrame(self, fg_color=THEME["PANEL_BG"])
        frame.grid(row=0, column=0, padx=PAD, pady=(PAD, PAD_SMALL), sticky="ew")
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            frame, text="계정:", width=60, anchor="w",
            text_color=THEME["TEXT"],
        ).grid(row=0, column=0, padx=(PAD, PAD_SMALL), pady=PAD_SMALL, sticky="w")

        self.account_menu = ctk.CTkOptionMenu(
            frame, values=["(계정 없음)"],
            command=self._on_account_changed,
        )
        self.account_menu.grid(row=0, column=1, padx=PAD_SMALL, pady=PAD_SMALL, sticky="ew")

        self.btn_add = ctk.CTkButton(
            frame, text="추가", width=80, command=self._on_add_account,
        )
        self.btn_add.grid(row=0, column=2, padx=PAD_SMALL, pady=PAD_SMALL)

        self.btn_remove = ctk.CTkButton(
            frame, text="삭제", width=70,
            fg_color="transparent", border_width=1,
            command=self._on_remove_account,
        )
        self.btn_remove.grid(row=0, column=3, padx=(PAD_SMALL, PAD), pady=PAD_SMALL)

    def _build_season_section(self):
        frame = ctk.CTkFrame(self, fg_color=THEME["PANEL_BG"])
        frame.grid(row=1, column=0, padx=PAD, pady=PAD_SMALL, sticky="ew")
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            frame, text="시즌:", width=60, anchor="w",
            text_color=THEME["TEXT"],
        ).grid(row=0, column=0, padx=(PAD, PAD_SMALL), pady=PAD_SMALL, sticky="w")

        self.season_menu = ctk.CTkOptionMenu(
            frame, values=["(데이터 없음)"],
            command=self._on_season_changed,
        )
        self.season_menu.grid(row=0, column=1, padx=PAD_SMALL, pady=PAD_SMALL, sticky="ew")

        self.btn_sync = ctk.CTkButton(
            frame, text="지금 동기화", width=120, command=self._on_sync_now,
        )
        self.btn_sync.grid(row=0, column=2, padx=(PAD_SMALL, PAD), pady=PAD_SMALL)

    def _build_body_section(self):
        self.stats_view = StatsView(self)
        self.stats_view.grid(row=2, column=0, padx=PAD, pady=PAD_SMALL, sticky="nsew")

    def _build_footer_section(self):
        frame = ctk.CTkFrame(self, fg_color=THEME["PANEL_BG"])
        frame.grid(row=3, column=0, padx=PAD, pady=(PAD_SMALL, PAD), sticky="ew")
        frame.grid_columnconfigure(0, weight=1)

        self.footer_status = ctk.CTkLabel(
            frame, text="아직 동기화한 적 없음", anchor="w",
            text_color=THEME["TEXT_MUTED"],
        )
        self.footer_status.grid(row=0, column=0, padx=PAD, pady=PAD_SMALL, sticky="w")

    # ─────────────────────────────────────────
    # 상태 갱신
    # ─────────────────────────────────────────

    def _refresh_all(self):
        self._refresh_account_picker()
        self._refresh_seasons()
        self.stats_view.set_season(self._selected_season)
        self._refresh_footer()
        self._refresh_buttons()

    def _refresh_account_picker(self):
        accs = accounts.list_accounts()
        active_ouid = accounts.get_active_ouid()
        if not accs:
            self.account_menu.configure(values=["(계정 없음)"])
            self.account_menu.set("(계정 없음)")
            self._account_label_to_ouid = {}
            return

        labels = []
        self._account_label_to_ouid = {}
        for a in accs:
            label = f"{a['nickname']}  ({a['ouid'][:8]}…)"
            labels.append(label)
            self._account_label_to_ouid[label] = a["ouid"]

        self.account_menu.configure(values=labels)
        active_label = next(
            (lbl for lbl, ouid in self._account_label_to_ouid.items() if ouid == active_ouid),
            labels[0],
        )
        self.account_menu.set(active_label)

    def _refresh_seasons(self):
        if not accounts.get_active_ouid():
            self.season_menu.configure(values=["(데이터 없음)"])
            self.season_menu.set("(데이터 없음)")
            self._selected_season = None
            self._season_label_to_id = {}
            return

        try:
            seasons = fc_stats.get_known_seasons()
        except db.NoActiveAccountError:
            seasons = []

        if not seasons:
            self.season_menu.configure(values=["(데이터 없음)"])
            self.season_menu.set("(데이터 없음)")
            self._selected_season = None
            self._season_label_to_id = {}
            return

        labels = [fc_stats.format_season_id(s) for s in seasons]
        self._season_label_to_id = dict(zip(labels, seasons))
        self.season_menu.configure(values=labels)
        if self._selected_season is None or self._selected_season not in seasons:
            self._selected_season = seasons[0]
        self.season_menu.set(fc_stats.format_season_id(self._selected_season))

    def _refresh_footer(self):
        if not accounts.get_active_ouid():
            self.footer_status.configure(text="계정을 추가하고 동기화해주세요")
            return
        try:
            last = db.get_state("last_synced_at")
        except db.NoActiveAccountError:
            last = None

        if not last:
            self.footer_status.configure(text="아직 동기화한 적 없음")
            return
        fresh = fc_stats.get_today_freshness()
        kst = fc_stats._utc_iso_to_kst(last).strftime("%Y-%m-%d %H:%M")
        state_icon = {"green": "🟢", "red": "🔴", "yellow": "🟡", "empty": "⚪"}.get(
            fresh["state"], ""
        )
        self.footer_status.configure(text=f"{state_icon} 마지막 동기화: {kst}")

    def _refresh_buttons(self):
        has_active = accounts.get_active_ouid() is not None
        state = "normal" if has_active else "disabled"
        self.btn_remove.configure(state=state)
        self.btn_sync.configure(state=state)

    # ─────────────────────────────────────────
    # 계정 picker 이벤트
    # ─────────────────────────────────────────

    def _on_account_changed(self, label: str):
        if self._sync_running():
            # sync 중에는 변경 막고 원래 값으로 되돌림
            self._refresh_account_picker()
            return
        ouid = self._account_label_to_ouid.get(label)
        if not ouid or ouid == accounts.get_active_ouid():
            return
        accounts.set_active_ouid(ouid)
        db.init_db()  # 새 활성 계정 DB 스키마 보장
        self._selected_season = None
        self._refresh_all()

    def _on_add_account(self):
        if self._sync_running():
            return
        nickname = _prompt_text(self, "계정 추가", "FC 온라인 닉네임을 입력하세요:")
        if not nickname:
            return
        nickname = nickname.strip()
        if not nickname:
            return

        # ouid 조회는 짧지만 그래도 별도 다이얼로그에서 진행 표시
        self._lookup_and_add(nickname)

    def _lookup_and_add(self, nickname: str):
        """닉네임 → ouid 조회 후 계정 추가, 그리고 자동 sync."""
        modal = self._open_lookup_modal(nickname)

        def worker():
            try:
                ouid = fc_api.get_ouid(nickname)
            except fc_api.FcApiError as e:
                msg = str(e)
                self.after(0, lambda: self._on_lookup_error(modal, msg))
                return
            self.after(0, lambda: self._on_lookup_done(modal, ouid, nickname))

        threading.Thread(target=worker, daemon=True).start()

    def _open_lookup_modal(self, nickname: str) -> ctk.CTkToplevel:
        modal = ctk.CTkToplevel(self)
        modal.title("계정 조회 중")
        modal.geometry("360x120")
        modal.transient(self)
        modal.configure(fg_color=THEME["APP_BG"])
        ctk.CTkLabel(modal, text=f"닉네임 조회 중: {nickname}",
                     text_color=THEME["TEXT"]).pack(pady=(PAD, PAD_SMALL))
        bar = ctk.CTkProgressBar(modal, width=280, mode="indeterminate")
        bar.pack(pady=PAD_SMALL)
        bar.start()
        modal._bar = bar  # type: ignore[attr-defined]
        self._center_child(modal)
        return modal

    def _on_lookup_done(self, modal, ouid: str, nickname: str):
        try:
            modal._bar.stop()
        except Exception:
            pass
        modal.destroy()

        existing = accounts.get_account(ouid)
        if existing:
            messagebox.showinfo(
                "이미 등록된 계정",
                f"이 ouid는 이미 '{existing['nickname']}'으로 등록되어 있습니다.\n"
                "계정을 전환합니다.",
                parent=self,
            )
            accounts.set_active_ouid(ouid)
            # 닉네임이 다르면 갱신
            if existing["nickname"] != nickname:
                accounts.update_nickname(ouid, nickname)
        else:
            accounts.add_account(ouid, nickname, make_active=True)

        db.init_db()
        self._selected_season = None
        self._refresh_all()
        self._start_sync()

    def _on_lookup_error(self, modal, msg: str):
        try:
            modal._bar.stop()
        except Exception:
            pass
        modal.destroy()
        messagebox.showerror("계정 조회 실패", msg, parent=self)

    def _on_remove_account(self):
        if self._sync_running():
            return
        active = accounts.get_active_account()
        if not active:
            return
        # 3-way: 데이터까지 삭제 / 계정만 삭제 / 취소
        delete_db = messagebox.askyesnocancel(
            "계정 삭제",
            f"'{active['nickname']}' 계정을 목록에서 제거합니다.\n\n"
            f"매치 데이터 파일(fc_stats_{active['ouid'][:8]}….db)도 함께 삭제할까요?\n\n"
            "  예 → 데이터까지 모두 삭제 (되돌릴 수 없음)\n"
            "  아니오 → 계정만 제거하고 데이터 파일은 보존\n"
            "       (나중에 같은 닉네임으로 다시 추가하면 데이터 자동 복원)\n"
            "  취소 → 아무것도 하지 않음",
            parent=self,
        )
        if delete_db is None:
            return  # 취소
        accounts.remove_account(active["ouid"], delete_db=delete_db)
        if accounts.get_active_ouid():
            db.init_db()
        self._selected_season = None
        self._refresh_all()

    # ─────────────────────────────────────────
    # 시즌 + sync
    # ─────────────────────────────────────────

    def _on_season_changed(self, value: str):
        sid = self._season_label_to_id.get(value)
        if sid is None:
            return
        self._selected_season = sid
        self.stats_view.set_season(sid)

    def _on_sync_now(self):
        if self._sync_running() or not accounts.get_active_ouid():
            return
        self._start_sync()

    # ─────────────────────────────────────────
    # Sync 스레드 관리
    # ─────────────────────────────────────────

    def _sync_running(self) -> bool:
        return self._sync_thread is not None and self._sync_thread.is_alive()

    def _start_sync(self):
        ouid = accounts.get_active_ouid()
        if not ouid:
            return
        self._cancel_event.clear()
        try:
            self._progress_start_count = db.get_match_count()
        except db.NoActiveAccountError:
            self._progress_start_count = 0
        self._sync_stats = fc_sync.SyncStats()
        self._open_progress_modal()
        self._progress_poll_alive = True
        self._poll_progress_tick()

        stats = self._sync_stats

        def worker():
            try:
                result = fc_sync.sync_user(
                    ouid,
                    on_progress=None,
                    cancel_event=self._cancel_event,
                    stats=stats,
                )
                self.after(0, lambda: self._on_sync_done(result))
            except fc_api.FcApiError as e:
                msg = str(e)
                self.after(0, lambda: self._on_sync_error(msg))
            except Exception as e:
                msg = f"동기화 중 오류: {e}"
                self.after(0, lambda: self._on_sync_error(msg))

        self._sync_thread = threading.Thread(target=worker, daemon=True)
        self._sync_thread.start()

    def _poll_progress_tick(self):
        """SyncStats 카운터 → label + progressbar 진행률 비례 set.

        DB 락을 안 잡으므로 worker와 경합 없음. progressbar는 phase별
        가중치로 실제 진행률을 반영해 차오른다."""
        if not self._progress_poll_alive:
            return
        snap = self._sync_stats.snapshot() if self._sync_stats else None
        self._update_progress_label_from(snap)
        if self._progress_bar is not None and snap is not None:
            try:
                ratio = _progress_ratio(snap)
                self._progress_bar.set(ratio)
            except Exception:
                pass
        try:
            if self._progress_modal is not None:
                self._progress_modal.update_idletasks()
        except Exception:
            pass
        self.after(120, self._poll_progress_tick)

    def _update_progress_label_from(self, snap):
        if self._progress_label is None or snap is None:
            return
        gained = snap["new_count"]
        total = self._progress_start_count + gained
        phase = snap["phase"]
        phase_kr = {
            "starting": "시작 중",
            "warmup":   "워커 준비 중",
            "list":     "매치 목록 조회",
            "filter":   "기존 데이터 비교",
            "detail":   "매치 상세 다운로드",
            "upsert":   "DB 저장",
            "done":     "완료",
        }.get(phase, phase)

        if phase == "list" and snap["list_total"] > 0:
            sub = f" {snap['list_done']}/{snap['list_total']} 페이지"
        elif phase == "detail" and snap["detail_total"] > 0:
            sub = f" {snap['detail_done']}/{snap['detail_total']}건"
        else:
            sub = ""

        self._progress_label.configure(
            text=(
                f"매치 데이터 불러오는 중... ({phase_kr}{sub})\n"
                f"받은 매치: {total:,}건 (+{gained:,})"
            )
        )

    def _on_sync_done(self, result: dict):
        self._progress_poll_alive = False
        self._close_progress_modal()
        if result.get("cancelled"):
            messagebox.showinfo("취소", "동기화가 취소되었습니다.", parent=self)
        else:
            ouid = result.get("ouid")
            finished = result.get("finished_at")
            if ouid:
                accounts.touch_last_synced(ouid, finished)
        self._refresh_all()

    def _on_sync_error(self, msg: str):
        self._progress_poll_alive = False
        self._close_progress_modal()
        messagebox.showerror("동기화 오류", msg, parent=self)
        self._refresh_all()

    # ─────────────────────────────────────────
    # Progress modal (grab 없음)
    # ─────────────────────────────────────────

    def _open_progress_modal(self):
        if self._progress_modal is not None:
            return
        modal = ctk.CTkToplevel(self)
        modal.title("동기화 중")
        modal.geometry("400x160")
        modal.transient(self)
        modal.configure(fg_color=THEME["APP_BG"])
        modal.protocol("WM_DELETE_WINDOW", self._on_cancel_sync)

        self._progress_modal = modal

        ctk.CTkLabel(modal, text="매치 데이터 동기화 중",
                     text_color=THEME["TEXT"]).pack(pady=(PAD, PAD_SMALL))
        self._progress_label = ctk.CTkLabel(
            modal, text="시작 중...", justify="center",
            text_color=THEME["TEXT_MUTED"],
        )
        self._progress_label.pack(pady=PAD_SMALL)

        # determinate 모드 + 직접 step. indeterminate의 자체 after-timer가
        # worker의 GIL 점유로 늦게 호출되어 멈춰 보이는 문제를 회피한다.
        self._progress_bar = ctk.CTkProgressBar(modal, width=320, mode="determinate")
        self._progress_bar.pack(pady=PAD_SMALL)
        self._progress_bar_value = 0.0
        self._progress_bar.set(0.0)

        ctk.CTkButton(
            modal, text="취소", width=80, command=self._on_cancel_sync,
        ).pack(pady=(PAD_SMALL, PAD))

        self._center_child(modal)

    def _close_progress_modal(self):
        if self._progress_modal is not None:
            self._progress_modal.destroy()
            self._progress_modal = None
            self._progress_label = None
            self._progress_bar = None

    def _on_cancel_sync(self):
        self._cancel_event.set()
        if self._progress_label is not None:
            self._progress_label.configure(text="취소 요청 중... 대기")

    # ─────────────────────────────────────────
    # 종료
    # ─────────────────────────────────────────

    def _on_close(self):
        self._cancel_event.set()
        self._close_progress_modal()
        try:
            app_state.set_geometry(self.geometry())
        except Exception:
            pass
        try:
            fc_sync.shutdown_pool()
        except Exception:
            pass
        self.destroy()

    # ─────────────────────────────────────────
    # 윈도우 위치 / 크기
    # ─────────────────────────────────────────

    def _apply_initial_geometry(self):
        saved = app_state.get_geometry()
        if saved and self._is_geometry_visible(saved):
            self.geometry(saved)
            return
        # 화면 정중앙
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - DEFAULT_W) // 2)
        y = max(0, (sh - DEFAULT_H) // 2)
        self.geometry(f"{DEFAULT_W}x{DEFAULT_H}+{x}+{y}")

    def _is_geometry_visible(self, geom: str) -> bool:
        """저장된 geometry가 현재 화면 가시 영역 안에 있는지 대략 검사.
        primary 모니터 기준이라 다중 모니터에선 보수적으로 판단 — 가시영역
        밖이라고 판단되면 정중앙으로 fallback."""
        m = _GEOM_RE.match(geom)
        if not m:
            return False
        w, h = int(m.group(1)), int(m.group(2))
        x, y = int(m.group(3)), int(m.group(4))
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        # 적어도 80px 가시 영역이 primary 모니터 안에 걸쳐있어야 OK로 인정
        if x + w < 80 or x > sw - 80:
            return False
        if y + h < 80 or y > sh - 80:
            return False
        if w < MIN_SIZE[0] or h < MIN_SIZE[1]:
            return False
        return True

    def _center_child(self, child):
        """자식 윈도우를 메인 윈도우 정중앙에 배치. child는 ctk.CTkToplevel."""
        try:
            self.update_idletasks()
            child.update_idletasks()
            cw = child.winfo_width()
            ch = child.winfo_height()
            # geometry()로 잡은 직후엔 winfo_width=1 인 경우가 있어 fallback
            if cw <= 1 or ch <= 1:
                req_w = child.winfo_reqwidth()
                req_h = child.winfo_reqheight()
                cw = max(cw, req_w)
                ch = max(ch, req_h)
            pw = self.winfo_width()
            ph = self.winfo_height()
            px = self.winfo_rootx()
            py = self.winfo_rooty()
            x = px + max(0, (pw - cw) // 2)
            y = py + max(0, (ph - ch) // 2)
            child.geometry(f"+{x}+{y}")
        except Exception:
            pass


# ─────────────────────────────────────────────
# 간단 입력 다이얼로그 (메인 윈도우 정중앙 + initial 값 지원)
# ─────────────────────────────────────────────

class _TextInputDialog(ctk.CTkToplevel):
    """CTkInputDialog 대체. 부모 정중앙 배치 + initial 미리 입력 지원."""

    def __init__(self, parent: "MainWindow", title: str, prompt: str, initial: str = ""):
        super().__init__(parent)
        self.title(title)
        self.geometry("440x220")
        self.minsize(440, 200)
        self.transient(parent)
        self.configure(fg_color=THEME["APP_BG"])
        self._result: Optional[str] = None

        ctk.CTkLabel(
            self, text=prompt, justify="left", anchor="w",
            text_color=THEME["TEXT"], wraplength=400,
        ).pack(pady=(PAD, PAD_SMALL), padx=PAD, anchor="w", fill="x")

        self._entry = ctk.CTkEntry(self, width=400)
        self._entry.pack(pady=PAD_SMALL, padx=PAD, fill="x")
        if initial:
            self._entry.insert(0, initial)
            self._entry.select_range(0, "end")
        self._entry.bind("<Return>", lambda e: self._ok())
        self._entry.bind("<Escape>", lambda e: self._cancel())

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(pady=PAD, padx=PAD, anchor="e")
        ctk.CTkButton(btns, text="확인", width=80, command=self._ok).pack(
            side="left", padx=(0, PAD_SMALL)
        )
        ctk.CTkButton(
            btns, text="취소", width=80,
            fg_color="transparent", border_width=1, command=self._cancel,
        ).pack(side="left")

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        parent._center_child(self)
        self.after(50, self._focus_entry)
        self.grab_set()

    def _focus_entry(self):
        try:
            self._entry.focus_force()
        except Exception:
            pass

    def _ok(self):
        self._result = self._entry.get()
        self.destroy()

    def _cancel(self):
        self._result = None
        self.destroy()

    def get_input(self) -> Optional[str]:
        self.wait_window()
        return self._result


def _prompt_text(parent: "MainWindow", title: str, prompt: str, initial: str = "") -> Optional[str]:
    """단순 텍스트 입력 다이얼로그. None=취소/빈문자, str=확정값."""
    return _TextInputDialog(parent, title, prompt, initial).get_input()


# ─────────────────────────────────────────────
# Progressbar 진행률 매핑
# ─────────────────────────────────────────────
# phase별 가중치로 0~1 사이 ratio 계산. detail이 sync 시간의 대부분을
# 차지하므로 가장 큰 비중을 받는다.

_PHASE_RANGES = {
    "starting": (0.00, 0.02),
    "warmup":   (0.00, 0.02),
    "list":     (0.02, 0.10),
    "filter":   (0.10, 0.12),
    "detail":   (0.12, 0.96),
    "upsert":   (0.96, 0.99),
    "done":     (1.00, 1.00),
}


def _progress_ratio(snap: dict) -> float:
    phase = snap.get("phase", "starting")
    lo, hi = _PHASE_RANGES.get(phase, (0.0, 0.0))
    if phase == "list" and snap.get("list_total", 0) > 0:
        frac = snap["list_done"] / snap["list_total"]
        return lo + (hi - lo) * frac
    if phase == "detail" and snap.get("detail_total", 0) > 0:
        frac = snap["detail_done"] / snap["detail_total"]
        return lo + (hi - lo) * frac
    return hi
