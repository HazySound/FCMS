"""ImageReactor 시절 fc_stats.db의 옛 매치를 FCMS의 ouid별 DB로 병합.

단발성 마이그레이션 스크립트. 빌드본에는 포함되지 않음.

사용:
    venv\\Scripts\\python.exe merge_legacy_db.py            # dry-run (수치만 출력)
    venv\\Scripts\\python.exe merge_legacy_db.py --apply    # 실제 병합

동작:
    1. Target DB를 .bak으로 백업
    2. Source의 matches 중 Target에 없는 match_id만 INSERT
    3. 병합 후 모든 매치의 fc_earned를 현재 정책으로 재계산
       (몰수승 +FC 포함 — 통합본 초기엔 0이었을 수 있음)
"""

import shutil
import sqlite3
import sys
from pathlib import Path

SRC = Path(r"D:\박시몬\ImageReactor\ImageReactor\data\fc_stats.db")
TGT = Path(r"D:\박시몬\파이썬 프로젝트\FcMiningStats\data\fc_stats_287db7a34f1feb2fca4654e09bc0ba41.db")

APPLY = "--apply" in sys.argv


def fmt(n):
    return f"{n:,}"


def main():
    if not SRC.exists():
        print(f"Source DB가 없습니다: {SRC}")
        return 1
    if not TGT.exists():
        print(f"Target DB가 없습니다: {TGT}")
        return 1

    c = sqlite3.connect(str(TGT))
    c.row_factory = sqlite3.Row
    c.execute("ATTACH DATABASE ? AS src", (str(SRC),))

    src_total = c.execute("SELECT COUNT(*) FROM src.matches").fetchone()[0]
    tgt_total = c.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    new_count = c.execute(
        "SELECT COUNT(*) FROM src.matches "
        "WHERE match_id NOT IN (SELECT match_id FROM matches)"
    ).fetchone()[0]

    src_oldest = c.execute("SELECT MIN(match_date) FROM src.matches").fetchone()[0]
    src_newest = c.execute("SELECT MAX(match_date) FROM src.matches").fetchone()[0]
    tgt_oldest = c.execute("SELECT MIN(match_date) FROM matches").fetchone()[0]
    tgt_newest = c.execute("SELECT MAX(match_date) FROM matches").fetchone()[0]

    print()
    print(f"  Source DB ({SRC.name})")
    print(f"    매치 수: {fmt(src_total)}")
    print(f"    기간:    {src_oldest}  ~  {src_newest}")
    print()
    print(f"  Target DB ({TGT.name})")
    print(f"    매치 수: {fmt(tgt_total)}")
    print(f"    기간:    {tgt_oldest}  ~  {tgt_newest}")
    print()
    print(f"  → Source에만 있는 매치: {fmt(new_count)}건")

    if new_count == 0:
        print("\n병합할 매치가 없습니다. 종료.")
        c.execute("DETACH DATABASE src")
        c.close()
        return 0

    if not APPLY:
        print("\n실제 병합을 진행하려면 --apply 옵션을 주세요:")
        print("  venv\\Scripts\\python.exe merge_legacy_db.py --apply")
        c.execute("DETACH DATABASE src")
        c.close()
        return 0

    # ── 실제 병합 ───────────────────────────────────────
    backup = TGT.with_suffix(".db.bak")
    shutil.copy2(TGT, backup)
    print(f"\n  백업 생성: {backup.name}")

    c.execute(
        "INSERT OR IGNORE INTO matches "
        "(match_id, match_date, match_type, season_id, division, "
        " match_result, match_end_type, fc_earned, fetched_at) "
        "SELECT match_id, match_date, match_type, season_id, division, "
        "       match_result, match_end_type, fc_earned, fetched_at "
        "FROM src.matches"
    )

    # fc_earned 재계산 — 현재 정책(몰수승 포함)으로 통일
    c.execute("""
        UPDATE matches SET fc_earned = CASE
            WHEN match_result = '승' AND division = 800 THEN 20
            WHEN match_result = '승' AND division = 900 THEN 15
            ELSE 0
        END
    """)
    c.commit()

    after_total = c.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    after_oldest = c.execute("SELECT MIN(match_date) FROM matches").fetchone()[0]
    after_newest = c.execute("SELECT MAX(match_date) FROM matches").fetchone()[0]
    added = after_total - tgt_total

    print(f"  병합 후 매치 수: {fmt(after_total)}  (+{fmt(added)})")
    print(f"  병합 후 기간:    {after_oldest}  ~  {after_newest}")
    print()
    print("  완료. FCMS를 다시 띄우면 갱신된 통계가 보입니다.")
    print(f"  문제 발생 시 백업 복원: {backup.name} → {TGT.name}")

    c.execute("DETACH DATABASE src")
    c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
