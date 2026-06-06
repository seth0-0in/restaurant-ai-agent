"""
main.py
=======
대화형 실행 진입점. (Memory 패턴 확인을 위해 같은 세션에서 여러 번 질문 가능)

실행 모드는 자동 선택된다:
  - OPENAI_API_KEY 가 있으면  → LLM 주도 ReAct (LLM이 도구를 직접 선택)
  - 없으면                    → 규칙기반 ReAct (키 없이 바로 실행)
  - 환경변수 AGENT_MODE=rule / llm 로 강제 지정 가능

실행:
    python -m src.main
    python -m src.main "전주 객사 근처 친구랑 저녁 맛집 3곳 추천해줘"
"""

import os
import sys
from .agent import MatjipAgent
from .memory import UserMemory


def build_agent(memory):
    mode = os.getenv("AGENT_MODE", "").lower()
    use_llm = (mode == "llm") or (mode != "rule" and os.getenv("OPENAI_API_KEY"))
    if use_llm:
        try:
            from .llm_react import LLMReActAgent
            print("🤖 실행 모드: LLM 주도 ReAct (OpenAI)")
            return LLMReActAgent(memory=memory)
        except Exception as e:
            print(f"   [경고] LLM 모드 초기화 실패({e}) → 규칙기반으로 폴백")
    print("⚙️  실행 모드: 규칙기반 ReAct (API 키 불필요)")
    return MatjipAgent(memory=memory)


def run_once(agent, query):
    print("\n" + "=" * 70)
    print(f"🙋 사용자: {query}")
    print("=" * 70)
    result = agent.run(query)
    print("\n----- [실행 Trace] --------------------------------------------------")
    print(result["trace"].render())
    print("\n----- [최종 답변] ---------------------------------------------------")
    print(result["answer"])
    print(f"\n[status] {result['status']}")
    return result


def main():
    agent = build_agent(UserMemory())

    if len(sys.argv) > 1:
        run_once(agent, " ".join(sys.argv[1:]))
        return

    print("🍽  맛집 추천 ReAct Agent (종료: q)")
    print("   예) 전주 객사 근처에서 친구랑 저녁 먹기 좋은 맛집 3곳 추천해줘")
    while True:
        try:
            q = input("\n질문> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n안녕히 가세요!")
            break
        if q.lower() in ("q", "quit", "exit", "종료"):
            print("안녕히 가세요!")
            break
        if not q:
            continue
        run_once(agent, q)


if __name__ == "__main__":
    main()
