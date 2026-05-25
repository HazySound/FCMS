"""앱 버전 + GitHub 저장소.

릴리즈마다 APP_VERSION을 bump하고 같은 값으로 GitHub Releases의 태그(v0.x.x)를
만들면 자동 업데이트 체크에 사용된다.

GITHUB_REPO는 'username/repo' 형식. 처음 한 번 정확히 설정.
"""

APP_VERSION = "0.1.0"
GITHUB_REPO = "HazySound/FCMS"  # ← TODO: 실제 GitHub username/repo로 확인
