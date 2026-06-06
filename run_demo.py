"""
run_demo.py
===========
과제 제출용 데모. 아래 시나리오를 순서대로 실행하며 단계별 Trace를 출력한다.

  [시나리오 0] (필수 테스트 프롬프트)
      "전주 객사 근처에서 친구랑 저녁 먹기 좋은 맛집을 찾아줘.
       너무 비싸지 않고, 리뷰가 좋은 곳 위주로 3곳 추천해줘."
  [시나리오 1] 존재하지 않는 지역
  [시나리오 2] 검색 결과 없음 → 조건 완화
  [시나리오 3] 음식 종류가 모호함
  [시나리오 4] 사용자 조건 부족 → 되물음 → Memory 활용
  [시나리오 5] Memory: 앞서 말한 선호를 기억해 부족 조건 보완

각 시나리오는 README의 'ReAct Agent 도구 호출 Trace' 근거가 된다.
"""

from src.main import build_agent
from src.memory import UserMemory


def make_agent():
    return build_agent(UserMemory())


def banner(title):
    print("\n\n" + "█" * 72)
    print(f"█ {title}")
    print("█" * 72)


def show(agent, query):
    print("\n" + "=" * 72)
    print(f"🙋 사용자: {query}")
    print("=" * 72)
    res = agent.run(query)
    print("\n----- 실행 Trace ----------------------------------------------------")
    print(res["trace"].render())
    print("\n----- 최종 답변 -----------------------------------------------------")
    print(res["answer"])
    print(f"\n[status] {res['status']}")
    return res


def main():
    # 시나리오 0~4 는 독립 메모리, 시나리오 5 는 같은 세션 메모리 사용
    banner("시나리오 0 — 필수 테스트 프롬프트 (정상 추천)")
    show(make_agent(),
         "전주 객사 근처에서 친구랑 저녁 먹기 좋은 맛집을 찾아줘. "
         "너무 비싸지 않고, 리뷰가 좋은 곳 위주로 3곳 추천해줘.")

    banner("시나리오 1 — 존재하지 않는 지역 (예외 처리)")
    show(make_agent(),
         "독도 근처에서 저녁 먹을 맛집 추천해줘")

    banner("시나리오 2 — 검색 결과 없음 → 조건 완화 (Reflection)")
    show(make_agent(),
         "서울 홍대 근처에서 저녁에 중국집 가고 싶어, 3곳 추천해줘")

    banner("시나리오 3 — 음식 종류가 모호함 (예외 처리)")
    show(make_agent(),
         "전주 객사 근처에서 뭔가 맛있는 거 먹고 싶어, 2곳만 알려줘")

    banner("시나리오 4 — 사용자 조건 부족 → 되물음 (예외 처리)")
    show(make_agent(),
         "맛집 추천해줘")

    banner("시나리오 5 — Memory 패턴 (같은 세션, 선호 기억)")
    session_agent = make_agent()
    show(session_agent, "전주 객사 근처에서 친구랑 저렴한 일식 저녁 먹을 곳 알려줘")
    # 지역/목적/가격을 다시 말하지 않아도 기억으로 보완되는지 확인
    show(session_agent, "리뷰 좋은 곳으로 2곳만 더 추천해줘")

    # 아래 두 시나리오는 전국 검색 예시입니다.
    # KAKAO_API_KEY 가 설정돼 있으면 카카오로 실제 맛집을 찾고,
    # 키가 없으면 "정확한 지명 입력/카카오 키 설정" 안내로 빠집니다(정상 동작).
    banner("시나리오 6 — 전국 검색: 부산 해운대 (카카오 키 설정 시 실제 검색)")
    show(make_agent(),
         "부산 해운대 근처에서 친구랑 저녁 회 3곳 추천해줘")

    banner("시나리오 7 — 전국 검색: 강남역 (카카오 키 설정 시 실제 검색)")
    show(make_agent(),
         "강남역 맛집 추천해줘")


if __name__ == "__main__":
    main()
