"""
llm.py
======
(선택) OpenAI LLM 연동.
OPENAI_API_KEY 가 설정되어 있고 openai 패키지가 있으면,
 - 각 단계의 Thought 문장
 - 최종 추천 문구
를 GPT로 생성한다. 키가 없으면 규칙기반 문구로 자동 대체한다.

도구 호출(제어 흐름)은 재현성을 위해 agent.py의 규칙기반 루프가 담당하고,
LLM은 '자연어 추론/설명' 부분을 보강하는 하이브리드 구조다.
"""

import os
import json


def llm_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def _client():
    from openai import OpenAI
    return OpenAI()


def narrate_thought(context: str, fallback: str) -> str:
    """현재 상황을 받아 ReAct의 Thought 한 문장을 생성. 실패 시 fallback."""
    if not llm_available():
        return fallback
    try:
        client = _client()
        r = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content":
                    "너는 맛집 추천 ReAct 에이전트다. 현재 상황을 보고 다음에 무엇을 왜 "
                    "하려는지 'Thought'를 한국어 한 문장으로 간결하게 설명하라."},
                {"role": "user", "content": context},
            ],
            max_tokens=120, temperature=0.4,
        )
        return r.choices[0].message.content.strip()
    except Exception as e:  # pragma: no cover
        print(f"   [경고] OpenAI Thought 생성 실패({e}) → 규칙기반 문구 사용")
        return fallback


def compose_answer(payload: dict, fallback: str) -> str:
    """추천 결과(payload)를 자연어 최종 답변으로 생성. 실패 시 fallback."""
    if not llm_available():
        return fallback
    try:
        client = _client()
        r = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content":
                    "너는 친절한 맛집 큐레이터다. 주어진 JSON(사용자 조건 + 추천 맛집 목록)을 "
                    "바탕으로 각 맛집을 왜 추천하는지 한국어로 따뜻하게 설명하라. "
                    "없는 사실을 지어내지 말고 주어진 정보만 사용하라."},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            max_tokens=500, temperature=0.6,
        )
        return r.choices[0].message.content.strip()
    except Exception as e:  # pragma: no cover
        print(f"   [경고] OpenAI 답변 생성 실패({e}) → 규칙기반 답변 사용")
        return fallback
