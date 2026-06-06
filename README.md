# 맛집 찾기 AI Agent

### ReAct + Agentic Design Patterns 기반 맛집 추천 에이전트

단순히 LLM에게 `"맛집 추천해줘"`라고 묻는 것이 아니라,
Agent가 사용자의 요청을 분석하고, 계획을 세우고, 필요한 도구를 호출한 뒤 Observation을 바탕으로 최종 추천을 생성하는 구조로 구현했습니다.

이번 과제의 핵심인 **“Agent가 어떤 방식으로 생각하고, 도구를 사용하며, 결과를 개선하는지”**가 실행 Trace에 드러나도록 구성했습니다.

---

## 1. 프로젝트 개요

이 프로젝트는 사용자의 조건에 맞는 맛집을 추천하는 AI Agent입니다.

사용자 요청 예시:

> 전주 객사 근처에서 친구랑 저녁 먹기 좋은 맛집을 찾아줘.
> 너무 비싸지 않고, 리뷰가 좋은 곳 위주로 3곳 추천해줘.

Agent는 위 요청을 다음과 같이 처리합니다.

1. 사용자 요청 분석
2. 지역, 음식 종류, 가격대, 방문 목적 파악
3. 필요한 도구 선택
4. 맛집 검색 도구 호출
5. Observation 수신
6. 거리, 평점, 리뷰 수, 가격대 기준 필터링
7. 조건이 부족하거나 결과가 부족한 경우 Reflection 수행
8. 최종 맛집 추천 결과 생성

---

## 2. 실행 방법

### 필요 환경

```bash
Python 3.9 이상
```

기본 실행은 표준 라이브러리만 사용하기 때문에 추가 패키지 없이도 실행 가능합니다.
외부 API 또는 LLM 기능을 사용하려면 `requirements.txt`를 설치하면 됩니다.

---

### 빠른 실행

#### 1) 과제 필수 시나리오와 예외 처리 시나리오 실행

```bash
python run_demo.py
```

#### 2) 단일 질문 실행

```bash
python -m src.main "전주 객사 근처에서 친구랑 저녁 먹기 좋은 맛집 3곳 추천해줘"
```

```bash
python -m src.main "부산 해운대 근처에서 친구랑 저녁 회 3곳 추천해줘"
```

> 부산 등 샘플 데이터에 없는 지역은 `KAKAO_API_KEY`가 있을 때 전국 검색이 가능합니다.

#### 3) 대화형 모드 실행

```bash
python -m src.main
```

대화형 모드에서는 같은 세션 안에서 사용자의 선호 조건을 기억하는 **Memory Pattern**을 확인할 수 있습니다.

---

## 3. 실행 모드

API Key가 없으면 자동으로 오프라인 모드로 실행됩니다.
API Key를 설정하면 실제 LLM 또는 카카오 로컬 API를 사용할 수 있습니다.

| 조건                  | 실행 모드           | 설명                      |
| ------------------- | --------------- | ----------------------- |
| `OPENAI_API_KEY` 있음 | LLM 주도 ReAct 모드 | LLM이 매 턴 직접 도구를 선택하며 추론 |
| API Key 없음          | 규칙기반 ReAct 모드   | 샘플 데이터와 규칙 기반 로직으로 실행   |

환경변수로 실행 모드를 강제할 수도 있습니다.

```bash
AGENT_MODE=llm
```

```bash
AGENT_MODE=rule
```

---

## 4. 외부 API / LLM 사용 방법

외부 API는 선택 사항입니다.
키가 없으면 자동으로 샘플 데이터 기반 오프라인 모드로 동작합니다.

### 패키지 설치

```bash
pip install -r requirements.txt
```

### 환경변수 설정

프로젝트 루트에 `.env` 파일을 만들고 아래와 같이 작성합니다.

```env
OPENAI_API_KEY=your_openai_api_key
KAKAO_API_KEY=your_kakao_rest_api_key
```

> `.env` 파일에는 개인 API Key가 들어가므로 GitHub에 업로드하지 않습니다.

---

## 5. 검색 지역 범위

| 조건                 | 검색 범위                 |
| ------------------ | --------------------- |
| `KAKAO_API_KEY` 있음 | 전국 검색 가능              |
| API Key 없음         | 샘플 데이터에 포함된 지역만 검색 가능 |

기본 샘플 데이터는 다음 지역을 중심으로 구성했습니다.

* 전주 객사
* 서울 홍대

---

## 6. 폴더 구조

```text
restaurant-ai-agent/
├── data/
│   └── restaurants.json          # 직접 만든 샘플 맛집 데이터셋
│
├── src/
│   ├── __init__.py               # 패키지 초기화
│   ├── agent.py                  # 규칙기반 ReAct Agent 실행 루프
│   ├── llm_react.py              # LLM 주도 ReAct Agent 실행 루프
│   ├── llm.py                    # LLM 호출 관련 보조 모듈
│   ├── main.py                   # CLI 실행 진입점
│   ├── memory.py                 # Memory Pattern 및 사용자 조건 파싱
│   ├── tools.py                  # 맛집 검색, 필터링, 랭킹 도구
│   └── trace.py                  # 단계별 Trace 로그 관리
│
├── .gitignore                    # .env, __pycache__ 등 제외 규칙
├── README.md                     # 프로젝트 설명 문서
├── requirements.txt              # 실행 환경 및 선택 패키지
├── run_demo.py                   # 과제 제출용 실행 데모
└── trace_example.txt             # ReAct Agent 도구 호출 Trace 예시
```

> `__pycache__`, `.env`, `.venv` 등은 제출 및 GitHub 업로드 대상에서 제외합니다.

---

## 7. 맛집 검색 도구

`src/tools.py`에 맛집 추천을 위한 도구를 구현했습니다.

모든 도구는 다음과 같은 표준 Observation 형식으로 결과를 반환합니다.

```python
{
    "ok": True,
    "data": [],
    "error": None,
    "tool": "tool_name",
    "meta": {}
}
```

오류가 발생하더라도 프로그램이 바로 종료되지 않고, `ok=False` 형태의 Observation을 반환하여 Agent가 대안을 선택할 수 있도록 했습니다.

| 도구 이름                | 역할                                   |
| -------------------- | ------------------------------------ |
| `validate_region`    | 지역 또는 랜드마크 존재 여부 검증                  |
| `search_restaurants` | 지역, 음식 종류, 영업 조건 기반 맛집 후보 검색         |
| `filter_by_distance` | 기준 좌표를 중심으로 거리 필터링                   |
| `filter_by_rating`   | 평점과 리뷰 수 기준 필터링                      |
| `filter_by_price`    | 가격대 기준 필터링                           |
| `rank_restaurants`   | 평점, 리뷰 수, 거리, 방문 목적 등을 기준으로 최종 순위 계산 |

---

## 8. 데이터 소스

### 1) 기본 모드: 샘플 데이터셋

외부 API Key가 없을 경우 `data/restaurants.json` 파일에 저장된 샘플 데이터를 사용합니다.

샘플 데이터에는 다음 정보가 포함됩니다.

* 식당 이름
* 지역
* 랜드마크
* 음식 종류
* 평점
* 리뷰 수
* 가격대
* 좌표
* 방문 목적
* 대표 메뉴

### 2) 선택 모드: Kakao Local API

`KAKAO_API_KEY`가 설정되어 있으면 카카오 로컬 API를 사용해 실제 지역 기반 검색을 수행합니다.

사용 API:

```text
GET /v2/local/search/keyword.json
```

사용 방식:

* 지역 검증
* 기준 좌표 탐색
* 음식점 또는 카페 검색
* 거리 기준 정렬
* 검색 실패 시 샘플 데이터로 폴백

주의 사항:

> 카카오 로컬 API는 평점과 리뷰 수를 제공하지 않습니다.
> 따라서 카카오 API 모드에서는 평점 필터가 제한적으로 동작하며, 거리와 검색 관련도를 중심으로 추천합니다.

---

## 9. 적용한 Agentic Design Pattern

과제 요구사항인 ReAct Pattern을 필수로 포함하고, 총 5가지 Agentic Design Pattern을 적용했습니다.

### 1) ReAct Pattern

Agent가 Thought, Action, Observation 흐름을 반복하며 최종 답변을 생성합니다.

```text
Thought → Action → Observation → Thought → Action → Observation → Final Answer
```

구현 파일:

```text
src/agent.py
src/llm_react.py
```

---

### 2) Tool Use Pattern

Agent가 상황에 따라 필요한 도구를 직접 선택하고 호출합니다.

사용 도구 예시:

```text
validate_region
search_restaurants
filter_by_distance
filter_by_rating
filter_by_price
rank_restaurants
```

---

### 3) Plan-and-Solve Pattern

사용자 요청을 한 번에 처리하지 않고 다음 단계로 나누어 해결합니다.

```text
지역 분석
→ 음식 종류 파악
→ 후보 검색
→ 거리 필터링
→ 평점/리뷰 수 필터링
→ 가격대 필터링
→ 최종 랭킹 생성
```

---

### 4) Reflection Pattern

검색 결과가 부족하거나 사용자의 조건을 만족하지 못하는 경우, Agent가 스스로 조건을 검토하고 완화합니다.

예시:

* 결과가 0개인 경우 음식 종류 조건 완화
* 후보가 부족한 경우 가격 조건 완화
* 평점 조건이 너무 엄격한 경우 리뷰 기준 완화
* API 호출 실패 시 샘플 데이터셋으로 대체

---

### 5) Memory Pattern

대화형 모드에서 사용자의 선호 조건을 기억하고 다음 추천에 반영합니다.

기억하는 정보 예시:

* 선호 지역
* 음식 종류
* 가격대
* 방문 목적
* 함께 가는 사람

---

## 10. 예외 처리

아래 상황에 대해 단순 오류 출력이 아니라, Agent가 Observation을 바탕으로 대안을 제시하도록 구현했습니다.

| 예외 상황         | 처리 방식                                             |
| ------------- | ------------------------------------------------- |
| 존재하지 않는 지역 입력 | `validate_region`에서 `ok=False` 반환 후 정확한 지역 재입력 안내 |
| 검색 결과 없음      | 조건을 완화하고 재검색                                      |
| 음식 종류가 모호함    | 전체 음식 종류 대상으로 검색 후 점수순 추천                         |
| API 호출 실패     | 실패 Observation 기록 후 샘플 데이터로 폴백                    |
| 사용자 조건 부족     | Memory로 보완하거나 필요한 조건을 질문                          |

---

## 11. 실행 테스트 시나리오

과제에서 제시된 필수 프롬프트를 실행했습니다.

```text
전주 객사 근처에서 친구랑 저녁 먹기 좋은 맛집을 찾아줘. 너무 비싸지 않고, 리뷰가 좋은 곳 위주로 3곳 추천해줘.
```

도구 호출 흐름은 다음과 같습니다.

```text
validate_region
→ search_restaurants
→ filter_by_distance
→ filter_by_rating
→ filter_by_price
→ rank_restaurants
→ Final Answer
```

실행 Trace는 `trace_example.txt` 파일에서 확인할 수 있습니다.

---

## 12. ReAct Agent Trace 예시

Trace에는 다음 내용이 포함됩니다.

* Agent의 판단 과정
* 호출한 도구 이름
* 도구 입력값
* 도구 실행 결과
* Observation
* 최종 추천 결과

예시 흐름:

```text
Thought: 사용자의 요청에서 지역은 전주 객사, 목적은 친구와 저녁 식사, 조건은 저렴한 가격과 좋은 리뷰로 파악했다.

Action: validate_region
Action Input: {"region": "전주", "landmark": "객사"}

Observation: 지역 검증 성공. 전주 객사 기준 좌표를 확보했다.

Thought: 지역이 확인되었으므로 근처 맛집 후보를 검색한다.

Action: search_restaurants
Action Input: {"region": "전주", "landmark": "객사", "meal_time": "dinner"}

Observation: 조건에 맞는 맛집 후보를 찾았다.

Thought: 친구와 저녁 식사에 적합하고 너무 비싸지 않은 곳을 골라야 한다.

Action: filter_by_price
Action Input: {"max_price_level": 2}

Observation: 가격대가 높은 후보를 제외했다.

Thought: 리뷰가 좋은 곳 위주로 최종 순위를 매긴다.

Action: rank_restaurants
Action Input: {"top_k": 3, "sort_by": ["rating", "review_count", "distance"]}

Observation: 최종 추천 후보 3곳을 선정했다.

Final Answer: 전주 객사 근처에서 친구와 저녁 먹기 좋은 맛집 3곳을 추천한다.
```

---

## 13. 제출 항목

본 Repository에는 다음 제출 항목이 포함되어 있습니다.

```text
소스 코드
requirements.txt
README.md
실행 로그 또는 Trace 파일
사용한 Agentic Design Pattern 설명
ReAct Agent의 도구 호출 Trace
```

제외 항목:

```text
.env
.venv/
__pycache__/
node_modules/
API Key가 포함된 파일
```

---

## 14. 실행 로그 파일

과제 제출용 실행 로그는 아래 파일에 포함되어 있습니다.

```text
trace_example.txt
```

해당 파일에는 필수 테스트 프롬프트 실행 과정과 도구 호출 Trace가 기록되어 있습니다.

---

## 15. 프로젝트 특징 요약

* ReAct Pattern 기반 맛집 추천 Agent 구현
* Tool Use, Plan-and-Solve, Reflection, Memory Pattern 적용
* 샘플 데이터 기반 오프라인 실행 가능
* Kakao Local API를 통한 전국 검색 확장 가능
* API 실패 및 조건 부족 상황에 대한 예외 처리 포함
* 실행 Trace를 통해 Agent의 도구 호출 과정 확인 가능
