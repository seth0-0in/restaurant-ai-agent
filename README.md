# 맛집 찾기 AI Agent (ReAct + Agentic Design Patterns)

단순히 LLM에게 "맛집 추천해줘"라고 묻는 것이 아니라, Agent가 스스로
**요청 분석 → 계획 수립 → 도구 호출 → Observation 수신 → 결과 검토/개선 → 최종 추천**
하는 구조로 구현했습니다. 과제 핵심인 *"Agent가 어떻게 생각하고 도구를 사용하며 결과를
개선하는지"* 가 실행 Trace에 그대로 드러납니다.

---

## 1. 실행 방법

### 필요 환경
- Python 3.9 이상
- 추가 패키지 없이도 실행됩니다(표준 라이브러리만 사용). 외부 API를 켜려면 아래 패키지 설치.

### 빠른 실행
```bash
# 1) 과제 필수 시나리오 + 예외/Memory 시나리오 한 번에 실행 (Trace 출력)
python run_demo.py

# 2) 단일 질문 실행
python -m src.main "전주 객사 근처에서 친구랑 저녁 먹기 좋은 맛집 3곳 추천해줘"
python -m src.main "부산 해운대 근처에서 친구랑 저녁 회 3곳 추천해줘"   # 전국 검색(카카오 키 필요)

# 3) 대화형 모드 (Memory 패턴 확인 — 같은 세션에서 여러 번 질문)
python -m src.main
```

### 외부 API / LLM 켜기 (선택)
키가 없으면 자동으로 **오프라인 모드(샘플 데이터 + 규칙기반 추론)** 로 동작합니다.
키를 넣으면 실제 LLM/지도 API로 업그레이드됩니다.
```bash
pip install -r requirements.txt
```
OPENAI_API_KEY=...      # (선택) LLM 주도 ReAct 모드
KAKAO_API_KEY=...       # (선택) 전국 실제 맛집 검색
```
### 실행 모드 (자동 선택)
| 조건 | 모드 | 설명 |
|------|------|------|
| `OPENAI_API_KEY` 있음 | **LLM 주도 ReAct** | LLM이 매 턴 **직접 도구를 선택**하며 추론 (`src/llm_react.py`) |
| 키 없음(기본) | **규칙기반 ReAct** | 키 없이 바로 실행, 동일한 Trace 구조 (`src/agent.py`) |

`AGENT_MODE=llm` / `AGENT_MODE=rule` 환경변수로 강제할 수 있습니다.

### 검색 지역 범위
| 조건 | 범위 |
|------|------|
| `KAKAO_API_KEY` 있음 | **전국** — 모르는 지역도 카카오 좌표 검색으로 자동 처리 |
| 키 없음(기본) | 샘플 데이터에 든 지역(**전주·서울**)만 |

---

## 2. 폴더 구조
```
matjip_agent/
├── README.md                ← 본 문서
├── requirements.txt         ← 실행 환경(선택 패키지 표시)
├── .env                     ← API Key 입력 파일 (키만 넣어 사용; 실제 키 넣으면 제출 제외)
├── .gitignore               ← .env, __pycache__ 등 제외 규칙
├── run_demo.py              ← 과제 제출용 데모 (필수 프롬프트 + 예외 5종)
├── trace_example.txt        ← run_demo.py 실행 로그(Trace) 
├── data/
│   └── restaurants.json     ← 직접 만든 샘플 맛집 데이터셋(전주 객사·서울 홍대)
└── src/
    ├── __init__.py          ← 패키지 초기화 (.env 자동 로드 + 출력 UTF-8 설정)
    ├── agent.py             ← 규칙기반 ReAct 루프 (패턴 5종 오케스트레이션)
    ├── llm_react.py         ← LLM 주도 ReAct 루프 (LLM이 도구를 직접 선택)
    ├── tools.py             ← 6개 도구(검색/거리/평점/가격/랭킹/지역검증) + 카카오 연동
    ├── memory.py            ← Memory 패턴 + 자연어 요청 파서(지역/음식/가격/목적 추출)
    ├── trace.py             ← 단계별 판단 과정 로거
    ├── llm.py               ← (규칙기반 모드용) OpenAI로 Thought/답변 문구 보강
    └── main.py              ← CLI 진입점 (모드 자동 선택)
```

---

## 3. 맛집 검색 도구 (Tool Use)

`src/tools.py` 의 도구 6종. 모든 도구는 `{"ok","data","error","tool","meta"}` 형태의 **표준
Observation** 을 반환하며, 오류가 나도 예외를 던지지 않고 `ok=False` Observation 을 돌려준다.

| 도구 | 역할 |
|------|------|
| `validate_region` | 지역/랜드마크 존재 검증 + 기준 좌표 확보 (카카오 키 있으면 전국 지오코딩) |
| `search_restaurants` | 지역·음식종류·저녁영업으로 후보 검색 (카카오 키 있으면 실제 검색) |
| `filter_by_distance` | 기준 좌표 반경(km) 필터 (Haversine 거리 계산) |
| `filter_by_rating` | 평점/리뷰 수 필터 |
| `filter_by_price` | 가격대(price_level 1~4) 필터 |
| `rank_restaurants` | 평점·리뷰·거리·방문목적 가중 점수화 후 상위 K개 |

### 데이터 소스
- **기본(키 없음): 직접 만든 샘플 데이터셋**(`data/restaurants.json`, 전주 객사·서울 홍대 중심).
  필드: 이름, 지역, 랜드마크, 음식종류, 평점, 리뷰수, 가격대, 좌표, 방문목적, 대표메뉴 등.
  오프라인이라 데이터에 든 지역만 검색됩니다.
- **(권장) 카카오 로컬 API → 전국 검색**: `KAKAO_API_KEY` 설정 시 전국 어디든 동작.
  마트·편의점 등 비식당은 결과에서 자동 제외하여 추천 품질을 높입니다.

> **추천 품질 규칙**
> - 요청에 **식사 키워드(저녁/점심/아침/밥/식사 등)** 가 있으면 카페·디저트 업종을 제외합니다
>   (밥 먹는 자리에 베이커리·카페가 추천되지 않도록). 단, 사용자가 "카페"·"디저트"를
>   직접 요청하면 그대로 보여줍니다. 식사 키워드 없는 일반 "맛집 추천"에는 디저트도 포함됩니다.
> - "술 한잔 / 한잔 / 이자카야" 등은 **주점**으로 인식해 '술집'으로 검색합니다.

---

## 4. 외부 API 사용 방법 (선택)

### Kakao Local API (실제 맛집 데이터 / 전국)
공식 문서: https://developers.kakao.com/docs/ko/local/dev-guide

1. https://developers.kakao.com → [내 애플리케이션] → 앱 생성
2. [앱] → **[플랫폼 키]** 에서 **REST API 키** 복사
3. **[카카오맵] → [사용 설정] → 상태 ON** (2024.12 이후 신규 앱은 필수)
4. `.env` 에 `KAKAO_API_KEY=복사한_REST_API_키` 입력 후 실행

동작:
- 지역 검증: `validate_region` 이 카카오 '키워드 장소 검색'으로 좌표를 찾음(전국).
- 맛집 검색: `GET /v2/local/search/keyword.json`, 헤더 `Authorization: KakaoAK {키}`,
  파라미터 `query`(예: "회 맛집"), `category_group_code`(음식점 FD6/카페 CE7),
  좌표 기준 `x,y,radius,sort=distance`, `size=15`. 응답의 `distance`·`place_url` 활용.
- 호출 실패 시 Observation에 실패 기록 후 **샘플 데이터로 자동 폴백** (예외 처리에 해당).

> ⚠️ 카카오는 **평점·리뷰를 제공하지 않습니다.** 따라서 카카오 모드에서는 `filter_by_rating`
> 이 자연스럽게 무시되고(평점 없는 항목 통과), 추천은 **거리·관련도 순**으로 이뤄집니다.
> 평점 기반 정밀 추천을 보려면 샘플 데이터셋 모드를 사용하세요.
> (도구의 능력에 맞춰 에이전트가 동작을 바꾸는 사례이기도 합니다.)

### OpenAI API (LLM 추론)
1. `.env` 에 `OPENAI_API_KEY=...` 입력 (모델은 `OPENAI_MODEL`, 기본 `gpt-4o-mini`)
2. `LLM 주도 ReAct` 모드로 전환되어, LLM이 매 턴 다음 도구를 JSON으로 직접 선택합니다.

---

## 5. 적용한 Agentic Design Pattern (5종)
과제 요구: 최소 2개 이상, ReAct 필수 → **5개 적용**.

1. **ReAct** — `Thought → Action → Observation` 반복으로 도구를 호출하고 결과를 보고
   다음 행동을 결정. 규칙기반(`agent.py`)·LLM 주도(`llm_react.py`) 두 구현 제공.
2. **Tool Use** — 6개 도구를 상황에 맞게 직접 선택·호출.
3. **Plan-and-Solve** — 요청을 (지역검증→검색→거리→평점→가격→랭킹) 단계로 분해해 계획 수립.
4. **Reflection** — 결과가 0건이거나 요청 개수보다 적으면 스스로 검토하고
   음식종류/가격/평점 조건을 완화해 재검토.
5. **Memory** — 지역·랜드마크·음식종류·가격대·방문목적 선호를 세션 동안 기억하고
   다음 요청의 부족한 조건을 자동 보완.

---

## 6. 예외 처리 (모두 Observation 기반 대안 제시)

| 상황 | 처리 |
|------|------|
| 존재하지 않는 지역 | `validate_region` ok=false → (카카오로도 못 찾으면) 정확한 지명 재입력 안내 |
| 검색 결과 없음 | 음식종류→저녁영업 조건 완화 후 재검색 (Reflection) |
| 음식 종류가 모호함 | "맛있는 거" 등 → 전체 종류로 검색 후 점수순 추천 |
| API 호출 실패 | Observation에 실패 기록 후 샘플 데이터로 폴백 |
| 사용자 조건 부족 | Memory로 보완, 그래도 지역이 없으면 되물음 |

---

## 7. 실행 테스트 시나리오 (필수 프롬프트)
> "전주 객사 근처에서 친구랑 저녁 먹기 좋은 맛집을 찾아줘. 너무 비싸지 않고, 리뷰가 좋은 곳 위주로 3곳 추천해줘."

도구 호출 순서(요약): `validate_region` → `search_restaurants` → `filter_by_distance`
→ `filter_by_rating` → `filter_by_price` → `rank_restaurants`.
단계별 전체 Trace 는 `trace_example.txt` 참고.
