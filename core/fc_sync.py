"""FC 매치 동기화 워커 (병렬 단순화 버전).

알고리즘:
    1. 매치 ID 페이지 전부를 병렬 fetch (offset 0, 100, ..., 2500).
       nexon API 한계인 2600매치까지 한 번에 ~1초 안에 ID 수집.
    2. ID 중 DB에 없는 신규만 골라 detail을 200 worker 풀로 병렬 fetch.
       2600건 cold start면 13 batch × 1.85초 ≈ 25초.
       후속 sync에서 신규 0~수십이면 1~2초.
    3. 모든 detail을 모아 한 번의 batch UPSERT.

이전 알고리즘의 Phase 1 (incremental) / Phase 2 (gap fill) 분기는 제거했다.
후속 sync에서 list API 25번 추가 호출되는 비용을 감수하고, cold start의 큰
시간 단축(약 5배)을 우선했다. quota 측면에서도 무의미한 양.

ImageReactor 원본의 watermark / season_depth 개념도 제거. 모든 sync는
"있는 매치 다 받는다"로 통일.

API rate limit 보호는 fc_api 내부 backoff에 위임.
"""

from __future__ import annotations

import datetime as _dt
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from core import accounts, fc_api, fc_stats_db as db

# stdout 진단 로그: FCSTATS_DEBUG=1 또는 콘솔 attach 시 출력
_DEBUG = os.environ.get("FCSTATS_DEBUG") == "1" or (sys.stdout and sys.stdout.isatty())


def _log(msg: str) -> None:
    if _DEBUG:
        try:
            print(f"[fc_sync {time.strftime('%H:%M:%S')}] {msg}", flush=True)
        except Exception:
            pass


PROGRESS_PHASE_RESOLVE = "resolve"
PROGRESS_PHASE_LIST    = "list"
PROGRESS_PHASE_DETAIL  = "detail"
PROGRESS_PHASE_DONE    = "done"

ProgressCb = Callable[[str, int, int, str], None]

PAGE_SIZE = 100
# 실측: 사용자가 가진 매치 수에 따라 nexon이 페이지 응답함. "2600 hard limit"은
# 우연이고, 사용자별로 실제 매치 수까지 받을 수 있다. 50페이지(5000매치)를
# 안전 범위로 잡고, 빈 페이지는 자연스럽게 0건으로 처리.
MAX_LIST_PAGES = 50
# urllib3 PoolManager maxsize와 동일. keep-alive로 TLS handshake가 사라져서
# 128 동시도 GIL을 묶지 않는다.
MAX_WORKERS = 128


class SyncStats:
    """동기화 진행 상황을 메모리에 보관하는 thread-safe 카운터.

    UI는 snapshot()만 polling하면 되므로 DB 락 경합 없이 매끄럽게 동작한다.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.new_count = 0
        self.list_done = 0
        self.list_total = 0
        self.detail_done = 0
        self.detail_total = 0
        self.phase = "starting"

    def inc_new(self, n: int = 1) -> None:
        with self._lock:
            self.new_count += n

    def inc_list(self, n: int = 1) -> None:
        with self._lock:
            self.list_done += n

    def set_list_total(self, total: int) -> None:
        with self._lock:
            self.list_total = total

    def inc_detail(self, n: int = 1) -> None:
        with self._lock:
            self.detail_done += n

    def set_detail_total(self, total: int) -> None:
        with self._lock:
            self.detail_total = total

    def set_phase(self, phase: str) -> None:
        with self._lock:
            self.phase = phase

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "new_count":     self.new_count,
                "list_done":     self.list_done,
                "list_total":    self.list_total,
                "detail_done":   self.detail_done,
                "detail_total":  self.detail_total,
                "phase":         self.phase,
            }


def _utcnow_iso() -> str:
    return _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")


def _notify(cb, phase, cur, total, msg):
    if cb is None:
        return
    try:
        cb(phase, cur, total, msg)
    except Exception:
        pass


def _cancelled(ev) -> bool:
    return ev is not None and ev.is_set()


def resolve_nickname(nickname: str) -> str:
    """닉네임 → ouid. 계정 등록/캐시는 accounts.py가 책임."""
    return fc_api.get_ouid(nickname)


def _fetch_detail_safe(match_id):
    try:
        return fc_api.get_match_detail(match_id)
    except fc_api.FcApiError:
        return None


def _fetch_list_safe(ouid: str, matchtype: int, offset: int) -> list[str]:
    try:
        return fc_api.get_match_ids(
            ouid, matchtype=matchtype, offset=offset, limit=PAGE_SIZE,
        )
    except fc_api.FcApiError:
        return []


# ─────────────────────────────────────────────
# Singleton thread pool — 앱 lifetime 재활용
# ─────────────────────────────────────────────

_pool: Optional[ThreadPoolExecutor] = None
_pool_lock = threading.Lock()
_pool_warm = False


def get_pool() -> ThreadPoolExecutor:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ThreadPoolExecutor(
                max_workers=MAX_WORKERS, thread_name_prefix="fc-detail",
            )
        return _pool


def warmup_pool() -> None:
    """모든 worker 스레드를 미리 spawn. 별도 스레드에서 호출 권장."""
    global _pool_warm
    pool = get_pool()
    if _pool_warm:
        return
    t0 = time.perf_counter()
    # batch로 spawn하면 burst를 분산해 메인 UI thread가 사이사이 GIL 잡을 기회.
    batch = 16
    for i in range(0, MAX_WORKERS, batch):
        size = min(batch, MAX_WORKERS - i)
        futs = [pool.submit(time.sleep, 0.01) for _ in range(size)]
        for f in futs:
            try:
                f.result(timeout=3.0)
            except Exception:
                pass
    _pool_warm = True
    _log(f"pool warmup done: {MAX_WORKERS} workers  ({(time.perf_counter()-t0)*1000:.0f}ms)")


def shutdown_pool() -> None:
    global _pool, _pool_warm
    with _pool_lock:
        if _pool is not None:
            _pool.shutdown(wait=False, cancel_futures=True)
            _pool = None
            _pool_warm = False


# ─────────────────────────────────────────────
# 메인 sync
# ─────────────────────────────────────────────

def sync_user(
    ouid: str,
    on_progress: Optional[ProgressCb] = None,
    matchtype: int = fc_api.MATCHTYPE_MANAGER,
    max_pages: Optional[int] = None,
    cancel_event=None,
    stats: Optional[SyncStats] = None,
):
    """매치 동기화.

    반환: {ouid, new_count, pages_scanned, unique_seasons, started_at, finished_at, cancelled}
    """
    started_at = _utcnow_iso()
    db.set_state("sync_complete", "0")
    cancelled = False
    new_count = 0

    pool = get_pool()
    if not _pool_warm:
        if stats:
            stats.set_phase("warmup")
        warmup_pool()

    pages = max_pages or MAX_LIST_PAGES

    # ── Step 1: 매치 ID 페이지 병렬 fetch ────────────────────────
    if stats:
        stats.set_phase("list")
        stats.set_list_total(pages)

    t_list = time.perf_counter()
    list_futures = {
        pool.submit(_fetch_list_safe, ouid, matchtype, i * PAGE_SIZE): i
        for i in range(pages)
    }
    all_ids: list[str] = []
    for fut in as_completed(list_futures):
        if _cancelled(cancel_event):
            cancelled = True
            for f in list_futures:
                f.cancel()
            break
        try:
            ids = fut.result()
            all_ids.extend(ids)
        except Exception:
            pass
        if stats:
            stats.inc_list()
    _log(f"  list 병렬 {pages}페이지 → {len(all_ids)}건  ({(time.perf_counter()-t_list)*1000:.0f}ms)")

    if cancelled:
        return _finalize(ouid, new_count, pages, started_at, cancelled=True,
                         on_progress=on_progress, stats=stats)

    # ── Step 2: existing 필터링 ──────────────────────────────────
    if stats:
        stats.set_phase("filter")
    t_filter = time.perf_counter()
    existing = db.get_existing_match_ids(all_ids)
    new_ids = [mid for mid in all_ids if mid not in existing]
    _log(f"  existing 필터: {len(existing)} existing / {len(new_ids)} 신규  ({(time.perf_counter()-t_filter)*1000:.0f}ms)")

    # ── Step 3: detail 병렬 fetch ────────────────────────────────
    details_map: dict[str, Optional[dict]] = {}
    if new_ids:
        if stats:
            stats.set_phase("detail")
            stats.set_detail_total(len(new_ids))

        t_detail = time.perf_counter()
        detail_futures = {
            pool.submit(_fetch_detail_safe, mid): mid for mid in new_ids
        }
        for fut in as_completed(detail_futures):
            if _cancelled(cancel_event):
                cancelled = True
                for f in detail_futures:
                    f.cancel()
                break
            mid = detail_futures[fut]
            try:
                details_map[mid] = fut.result()
            except Exception:
                details_map[mid] = None
            if stats:
                stats.inc_detail()
        _log(f"  detail 병렬 {len(details_map)}/{len(new_ids)}건  ({(time.perf_counter()-t_detail)*1000:.0f}ms)")

    # ── Step 4: 변환 + batch UPSERT ──────────────────────────────
    # 가장 최근 매치의 nickname을 추적해 메타에 자동 갱신 — 게임 내 닉네임
    # 변경을 별도 UI 없이 따라간다.
    latest_nickname: Optional[str] = None
    latest_date: str = ""
    if details_map and not cancelled:
        if stats:
            stats.set_phase("upsert")
        t_up = time.perf_counter()
        fetched_at = _utcnow_iso()
        new_records: list[dict] = []
        for mid, detail in details_map.items():
            if detail is None:
                continue
            info = fc_api.extract_user_match_info(detail, ouid)
            if info is None:
                continue
            fc_earned = fc_api.calc_fc(
                info["division"], info["matchResult"], info["matchEndType"] or 0,
            )
            match_date = detail.get("matchDate") or ""
            new_records.append({
                "match_id":       mid,
                "match_date":     match_date,
                "match_type":     detail.get("matchType", matchtype),
                "season_id":      info["seasonId"],
                "division":       info["division"],
                "match_result":   info["matchResult"],
                "match_end_type": info["matchEndType"] or 0,
                "fc_earned":      fc_earned,
                "fetched_at":     fetched_at,
            })
            nick = info.get("nickname")
            if nick and match_date > latest_date:
                latest_date = match_date
                latest_nickname = nick

        if new_records:
            db.upsert_matches(new_records)
            new_count = len(new_records)
            if stats:
                stats.inc_new(new_count)
        _log(f"  batch upsert {new_count}건  ({(time.perf_counter()-t_up)*1000:.0f}ms)")

    # 닉네임 자동 갱신 (이번 sync에서 매치를 1건 이상 받은 경우에만)
    if latest_nickname:
        try:
            accounts.update_nickname(ouid, latest_nickname)
        except Exception:
            pass

    return _finalize(ouid, new_count, pages, started_at, cancelled,
                     on_progress=on_progress, stats=stats)


def _finalize(ouid, new_count, pages, started_at, cancelled,
              on_progress=None, stats=None):
    """sync 종료 처리 — sync_state 갱신 + 콜백."""
    finished_at = _utcnow_iso()
    db.set_state("last_synced_at", finished_at)
    latest = db.get_latest_match_date()
    if latest:
        db.set_state("last_match_date", latest)
    if not cancelled:
        db.set_state("sync_complete", "1")

    if stats:
        stats.set_phase("done")
    msg = "취소됨" if cancelled else f"동기화 완료: 신규 {new_count}건"
    _notify(on_progress, PROGRESS_PHASE_DONE, new_count, new_count, msg)

    return {
        "ouid":            ouid,
        "new_count":       new_count,
        "pages_scanned":   pages,
        "unique_seasons":  [],
        "started_at":      started_at,
        "finished_at":     finished_at,
        "cancelled":       cancelled,
    }
