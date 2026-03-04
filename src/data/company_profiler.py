"""
회사 프로필 생성기 (CompanyProfiler)

CLI에서 대화형으로 회사 정보를 수집해 company_data/company_profile.json 파일을 생성합니다.
이 파일이 있으면 content_generator가 Phase 6(WHY US)에 실제 역량·실적을 채워
플레이스홀더 남용 문제를 해결합니다.

사용 방법:
    python main.py setup-company
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


# 회사 프로필 표준 템플릿
PROFILE_TEMPLATE: Dict[str, Any] = {
    "company_name": "",
    "founded_year": "",
    "employee_count": "",
    "representative": "",
    "headquarters": "",
    "main_services": [],
    "certifications": [],
    "key_clients": [],
    "past_projects": [],
    "team_members": [],
    "financial": {
        "annual_revenue": "",
        "credit_rating": "",
    },
    "awards": [],
    "unique_strengths": [],
    "contact": {
        "phone": "",
        "email": "",
        "website": "",
    },
}


def _ask(prompt: str, default: str = "") -> str:
    """사용자 입력 받기 (기본값 지원)."""
    if default:
        result = input(f"{prompt} [{default}]: ").strip()
        return result if result else default
    result = input(f"{prompt}: ").strip()
    return result


def _ask_list(prompt: str, hint: str = "쉼표로 구분") -> List[str]:
    """리스트 형식 입력 받기."""
    raw = input(f"{prompt} ({hint}): ").strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _ask_projects() -> List[Dict[str, str]]:
    """수행 실적 대화형 입력."""
    projects = []
    print("\n  [수행 실적 입력] (없으면 엔터로 종료)")
    idx = 1
    while True:
        print(f"\n  [{idx}번 실적]")
        client = _ask("  발주처")
        if not client:
            break
        project = _ask("  프로젝트명")
        year = _ask("  수행연도 (예: 2024)")
        amount = _ask("  계약금액 (예: 1.2억원)")
        achievement = _ask("  주요 성과 (수치 포함, 예: 팔로워 +5000명)")
        projects.append({
            "client": client,
            "project": project,
            "year": year,
            "amount": amount,
            "achievement": achievement,
        })
        idx += 1
        more = input(f"  추가 실적 입력? (y/n) [n]: ").strip().lower()
        if more != "y":
            break
    return projects


def _ask_team_members() -> List[Dict[str, Any]]:
    """핵심 인력 대화형 입력."""
    members = []
    print("\n  [핵심 인력 입력] (없으면 엔터로 종료)")
    idx = 1
    while True:
        print(f"\n  [{idx}번 인력]")
        name = _ask("  성명")
        if not name:
            break
        role = _ask("  역할/직책 (예: 프로젝트 매니저)")
        exp = _ask("  경력 연수 (예: 10)")
        expertise = _ask_list("  전문 분야", "쉼표로 구분")
        certs = _ask_list("  보유 자격증", "쉼표로 구분")
        members.append({
            "name": name,
            "role": role,
            "experience_years": int(exp) if exp.isdigit() else 0,
            "expertise": expertise,
            "certifications": certs,
        })
        idx += 1
        more = input(f"  추가 인력 입력? (y/n) [n]: ").strip().lower()
        if more != "y":
            break
    return members


def run_interactive_setup(output_path: Optional[Path] = None) -> Path:
    """
    대화형 회사 프로필 생성 워크플로우.

    Args:
        output_path: 저장 경로 (None이면 company_data/company_profile.json)

    Returns:
        저장된 파일 경로
    """
    if output_path is None:
        output_path = Path(__file__).parent.parent.parent / "company_data" / "company_profile.json"

    # 기존 파일 있으면 로드해 기본값 제공
    existing: Dict[str, Any] = {}
    if output_path.exists():
        try:
            existing = json.loads(output_path.read_text(encoding="utf-8"))
            print(f"\n기존 프로필을 로드했습니다: {output_path}")
            print("엔터를 누르면 기존 값 유지, 새 값을 입력하면 업데이트됩니다.\n")
        except Exception:
            pass

    print("=" * 60)
    print("  회사 프로필 설정 (Phase 6: WHY US 품질 향상)")
    print("=" * 60)

    profile = dict(PROFILE_TEMPLATE)

    # 기본 정보
    print("\n[기본 정보]")
    profile["company_name"] = _ask("회사명", existing.get("company_name", ""))
    profile["founded_year"] = _ask("설립연도 (예: 2010)", existing.get("founded_year", ""))
    profile["employee_count"] = _ask("직원 수 (예: 50명)", existing.get("employee_count", ""))
    profile["representative"] = _ask("대표자명", existing.get("representative", ""))
    profile["headquarters"] = _ask("본사 위치 (예: 서울특별시 강남구)", existing.get("headquarters", ""))

    # 서비스/역량
    print("\n[주요 서비스 및 역량]")
    existing_services = ", ".join(existing.get("main_services", []))
    profile["main_services"] = _ask_list(
        "주요 서비스·제품",
        f"쉼표로 구분 (현재: {existing_services})" if existing_services else "쉼표로 구분",
    ) or existing.get("main_services", [])

    profile["certifications"] = _ask_list(
        "보유 인증·특허 (예: ISO 9001, 벤처기업)",
        "쉼표로 구분",
    ) or existing.get("certifications", [])

    profile["key_clients"] = _ask_list(
        "주요 고객사 (예: 서울시, 삼성전자)",
        "쉼표로 구분",
    ) or existing.get("key_clients", [])

    profile["unique_strengths"] = _ask_list(
        "핵심 차별 강점 3~5개 (수치 포함, 예: 지역 인플루언서 47명 네트워크)",
        "쉼표로 구분",
    ) or existing.get("unique_strengths", [])

    # 수행 실적
    print("\n[수행 실적]")
    use_existing = ""
    if existing.get("past_projects"):
        use_existing = input(f"기존 실적 {len(existing['past_projects'])}건 유지? (y/n) [y]: ").strip().lower()
    if use_existing != "n" and existing.get("past_projects"):
        profile["past_projects"] = existing["past_projects"]
        print(f"  기존 실적 {len(profile['past_projects'])}건 유지.")
        add_more = input("  추가 실적 입력? (y/n) [n]: ").strip().lower()
        if add_more == "y":
            profile["past_projects"].extend(_ask_projects())
    else:
        profile["past_projects"] = _ask_projects()

    # 핵심 인력
    print("\n[핵심 인력]")
    use_existing_team = ""
    if existing.get("team_members"):
        use_existing_team = input(f"기존 인력 {len(existing['team_members'])}명 유지? (y/n) [y]: ").strip().lower()
    if use_existing_team != "n" and existing.get("team_members"):
        profile["team_members"] = existing["team_members"]
        print(f"  기존 인력 {len(profile['team_members'])}명 유지.")
    else:
        profile["team_members"] = _ask_team_members()

    # 재무/수상
    print("\n[기타 정보]")
    profile["financial"]["annual_revenue"] = _ask(
        "연간 매출 (예: 30억원)", existing.get("financial", {}).get("annual_revenue", "")
    )
    profile["awards"] = _ask_list(
        "수상 실적 (예: 2024 우수기업상)",
        "쉼표로 구분",
    ) or existing.get("awards", [])
    profile["contact"]["phone"] = _ask("대표전화", existing.get("contact", {}).get("phone", ""))
    profile["contact"]["email"] = _ask("대표이메일", existing.get("contact", {}).get("email", ""))
    profile["contact"]["website"] = _ask("홈페이지", existing.get("contact", {}).get("website", ""))

    # 저장
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n✅ 회사 프로필 저장 완료: {output_path}")
    print("   이제 제안서 생성 시 Phase 6(WHY US)에 실제 역량·실적이 자동으로 반영됩니다.")
    return output_path
