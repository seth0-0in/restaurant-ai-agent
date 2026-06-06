"""
llm_react.py
============
[진짜 ReAct 모드] LLM이 매 턴 직접 '어떤 도구를 호출할지'를 결정하는 에이전트.

기존 agent.py(규칙기반)와 달리, 도구 선택/순서/조건완화를 모두 LLM이 추론한다.
- LLM은 매 턴 JSON 하나만 출력: {"thought","action","action_input"} 또는 {"thought","final_answer"}
- 에이전트는 도구를 실행해 'Observation'(요약)을 돌려주고, 이를 messages에 넣어 루프를 돈다.
- 후보 목록(큰 데이터)은 LLM이 들고 다니지 않는다. 에이전트가 '작업셋(pool)'을 서버측에
  유지하고, 필터/랭킹 도구는 현재 작업셋에 적용된다. (실전 에이전트의 일반적 설계)

OPENAI_API_KEY 가 있을 때만 사용된다. 없으면 main.py가 규칙기반 agent.py로 폴백한다.
"""

import os
import json
import re

from . import tools
from .memory import UserMemory, parse_request
from .trace import Trace


TOOL_SPEC = """사용 가능한 도구(Action):
1. validate_region(region: str, landmark: str="")
   - 지역/랜드마크가 실제 존재하는지 확인하고 거리 계산용 기준 좌표를 확보한다.
   - 어떤 검색보다 먼저 호출해야 한다.
2. search_restaurants(food_type: str="", dinner_only: bool=false)
   - 확정된 지역의 맛집 후보를 불러와 '작업셋'에 적재한다. (지역/랜드마크는 validate_region 결과 사용)
   - food_type 예: 한식/일식/양식/중식/카페/디저트/주점. 비우면 전체.
3. filter_by_distance(max_km: float)
   - 작업셋을 기준 좌표 반경 max_km(km) 이내로 좁힌다.
4. filter_by_rating(min_rating: float, min_reviews: int)
   - 작업셋을 평점/리뷰수 기준으로 거른다.
5. filter_by_price(max_price_level: int)
   - 작업셋을 가격대(1=저렴 ~ 4=비쌈) 이하로 거른다.
6. rank_and_finish(purpose: str="", top_k: int=3)
   - 작업셋을 평점/리뷰/거리/방문목적으로 점수화해 상위 top_k를 '최종 추천'으로 확정한다.
   - 이 도구의 Observation에 추천 맛집의 상세 정보가 담긴다. 이후 final_answer를 작성하라."""

SYSTEM_PROMPT = f"""너는 맛집 추천 ReAct 에이전트다. 사용자의 조건에 맞는 맛집을 도구를 호출해 찾는다.

{TOOL_SPEC}

[출력 형식] 매 턴 아래 JSON '하나'만 출력한다. 마크다운/코드펜스/설명을 절대 붙이지 마라.
  도구 호출:   {{"thought":"왜 이 행동을 하는지", "action":"도구명", "action_input":{{...}}}}
  최종 답변:   {{"thought":"...", "final_answer":"사용자에게 보여줄 추천문(한국어)"}}

[행동 규칙]
- 가장 먼저 validate_region을 호출한다. 사용자 요청 문장에서 지역/랜드마크를 직접 추출해
  region/landmark 로 전달하라(예: '부산 해운대' → region="부산", landmark="해운대").
  힌트의 region이 비어 있어도, 카카오가 전국 어디든 좌표를 찾아주므로 그대로 시도하라.
- validate_region 결과가 ok=false면(카카오도 못 찾은 위치), 임의로 검색하지 말고
  final_answer로 지명을 더 정확히 입력해 달라고 안내한다.
- search_restaurants 결과가 0건이면 음식 종류 제한을 풀고(food_type="") 다시 검색한다. (Reflection)
- 음식 종류가 모호하면(예: '맛있는 거') 특정 종류로 좁히지 말고 전체로 검색한다.
- **rank_and_finish는 작업셋이 top_k보다 많아도 알아서 점수 상위 top_k만 고른다.**
  따라서 후보 수가 top_k 이상이면 굳이 더 좁히지 말고 곧바로 rank_and_finish를 호출하라.
  후보를 정확히 top_k개로 맞추려고 애쓰지 마라.
- **무한 반복 금지**: 어떤 필터를 호출했는데 결과 수(count)가 줄지 않으면(=효과 없음),
  그 필터를 더 완화/반복하지 말고 즉시 rank_and_finish로 마무리하라.
  같은 도구를 비슷한 입력으로 두 번 이상 호출하지 마라.
- **카카오 데이터에는 평점/가격 정보가 없을 수 있다.** 이 경우 filter_by_rating /
  filter_by_price는 결과를 줄이지 못한다(정상). 그러면 더 좁히려 하지 말고 거리 필터
  한 번 정도만 적용한 뒤 rank_and_finish로 마무리하라.
- 보통 3~5번의 Action이면 충분하다. 반드시 마지막에 rank_and_finish로 추천을 확정한 뒤,
  그 Observation의 상세 정보를 바탕으로 final_answer를 작성한다. 없는 사실을 지어내지 마라."""

MAX_STEPS = 10


class LLMReActAgent:
    def __init__(self, memory: UserMemory = None, model: str = None):
        self.memory = memory or UserMemory()
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        # 세션 작업 상태
        self.pool = []
        self.center = None
        self.region_info = None
        self.final_items = []

    # ------------------------------------------------------------------
    def run(self, query: str) -> dict:
        trace = Trace()
        self.pool, self.center, self.region_info, self.final_items = [], None, None, []

        # [Memory] 부족 조건 보완
        parsed = parse_request(query)
        hints = self.memory.fill_defaults(parsed)
        if hints.get("_memory_filled"):
            trace.memory(f"이전 선호로 보완: {', '.join(hints['_memory_filled'])}")
        self.memory.update(hints)
        self.hints = hints

        user_msg = (
            f"사용자 요청: {query}\n\n"
            f"요청에서 파악한 조건(참고용 힌트):\n"
            f"- 지역: {hints.get('region')}\n"
            f"- 랜드마크: {hints.get('landmark')}\n"
            f"- 음식종류: {hints.get('food_type')} (모호함={hints.get('food_ambiguous')})\n"
            f"- 최대가격대: {hints.get('max_price_level')}\n"
            f"- 방문목적: {hints.get('purpose')}\n"
            f"- 추천 개수: {hints.get('count')}\n"
            f"- 저녁여부: {'저녁' in query or '디너' in query}\n"
            "위 도구들을 사용해 단계적으로 추천을 완성하라. JSON 한 개만 출력."
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]

        client = self._client()
        filter_tools = {"filter_by_distance", "filter_by_rating", "filter_by_price"}
        no_progress = 0
        for step_i in range(MAX_STEPS):
            raw = self._chat(client, messages)
            step = self._parse(raw)
            if step is None:
                trace.error("LLM 출력 JSON 파싱 실패 → 한 번 더 형식을 요청합니다.")
                messages.append({"role": "user",
                                 "content": "직전 응답이 JSON 형식이 아니었다. JSON 객체 하나만 다시 출력하라."})
                continue

            trace.thought(step.get("thought", ""))

            if "final_answer" in step:
                trace.final(step["final_answer"])
                self.memory.remember_result(query, [r["name"] for r in self.final_items])
                trace.memory(f"현재 기억된 선호: {self.memory.snapshot()}")
                return {"answer": step["final_answer"], "items": self.final_items,
                        "status": "ok", "trace": trace}

            action = step.get("action", "")
            action_input = step.get("action_input", {}) or {}
            trace.action(action, action_input)

            before = len(self.pool)
            obs = self._execute(action, action_input)

            # 필터가 결과를 줄이지 못하면(효과 없음) 더 좁히지 말고 마무리하도록 유도
            if action in filter_tools and isinstance(obs, dict) and obs.get("count") == before:
                no_progress += 1
                obs["note"] = ("결과 수가 줄지 않았습니다(이 필터는 효과 없음). "
                               "더 좁히지 말고 rank_and_finish로 마무리하세요.")
            else:
                no_progress = 0

            trace.observation(obs)
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user",
                             "content": "Observation: " + json.dumps(obs, ensure_ascii=False)})

            # 진전이 없거나 스텝이 많이 진행되면 마무리를 강하게 지시
            if no_progress >= 2 or step_i >= MAX_STEPS - 3:
                messages.append({"role": "user",
                                 "content": "후보가 충분합니다. 더 이상 필터링하지 말고 지금 "
                                            "rank_and_finish(top_k 지정)를 호출해 추천을 확정한 뒤 "
                                            "final_answer를 작성하세요."})

        # 스텝 초과
        msg = "추천을 완성하지 못했어요. 조건을 조금 더 구체적으로 알려주시면 다시 시도하겠습니다."
        trace.final(msg)
        return {"answer": msg, "items": self.final_items, "status": "max_steps", "trace": trace}

    # ------------------------------------------------------------------
    # 도구 실행 (작업셋 mutate, LLM에는 '요약' Observation만 반환)
    # ------------------------------------------------------------------
    def _execute(self, action: str, inp: dict) -> dict:
        try:
            if action == "validate_region":
                region = inp.get("region") or self.hints.get("region") or ""
                landmark = inp.get("landmark") or self.hints.get("landmark") or ""
                res = tools.validate_region(region, landmark)
                if res["ok"]:
                    self.region_info = res["data"]
                    self.center = res["data"].get("coord")
                return {"ok": res["ok"], "tool": "validate_region",
                        "region": (res["data"] or {}).get("region") if res["ok"] else None,
                        "landmark": (res["data"] or {}).get("landmark") if res["ok"] else None,
                        "error": res.get("error")}

            if action == "search_restaurants":
                if not self.region_info:
                    return {"ok": False, "tool": "search_restaurants",
                            "error": "먼저 validate_region으로 지역을 확정해야 한다."}
                res = tools.search_restaurants(
                    region=self.region_info["region"],
                    landmark=self.region_info.get("landmark") or "",
                    food_type=inp.get("food_type", "") or "",
                    dinner_only=bool(inp.get("dinner_only", False)),
                    center=self.center,
                    exclude_cafe_dessert=(
                        bool(self.hints.get("meal_context"))
                        and (inp.get("food_type", "") or "") not in ("카페", "디저트")))
                self.pool = res["data"]
                return self._summary("search_restaurants", res["ok"])

            if action == "filter_by_distance":
                res = tools.filter_by_distance(self.pool, self.center,
                                               max_km=float(inp.get("max_km", 1.0)))
                self.pool = res["data"] if res["data"] else self.pool
                return self._summary("filter_by_distance", True)

            if action == "filter_by_rating":
                res = tools.filter_by_rating(self.pool,
                                             min_rating=float(inp.get("min_rating", 4.0)),
                                             min_reviews=int(inp.get("min_reviews", 300)))
                self.pool = res["data"]
                return self._summary("filter_by_rating", True)

            if action == "filter_by_price":
                res = tools.filter_by_price(self.pool,
                                            max_price_level=int(inp.get("max_price_level", 4)))
                self.pool = res["data"]
                return self._summary("filter_by_price", True)

            if action == "rank_and_finish":
                res = tools.rank_restaurants(self.pool,
                                             purpose=inp.get("purpose", "") or "",
                                             top_k=int(inp.get("top_k", 3)))
                self.final_items = res["data"]
                detailed = [{
                    "name": r["name"], "food_type": r.get("food_type"),
                    "rating": r.get("rating"), "review_count": r.get("review_count"),
                    "price_level": r.get("price_level"),
                    "price_label": tools.PRICE_LABEL.get(r.get("price_level"), ""),
                    "distance_m": round(r["distance_km"] * 1000) if r.get("distance_km") is not None else None,
                    "signature_menu": r.get("signature_menu"),
                    "description": r.get("description"),
                    "place_url": r.get("place_url", ""),
                } for r in self.final_items]
                return {"ok": True, "tool": "rank_and_finish",
                        "count": len(detailed), "recommendations": detailed}

            return {"ok": False, "tool": action, "error": f"알 수 없는 도구: {action}"}
        except Exception as e:
            return {"ok": False, "tool": action, "error": f"도구 실행 오류: {e}"}

    def _summary(self, tool, ok):
        names = [r["name"] for r in self.pool[:6]]
        return {"ok": ok, "tool": tool, "count": len(self.pool), "sample": names}

    # ------------------------------------------------------------------
    # OpenAI 호출 / JSON 파싱
    # ------------------------------------------------------------------
    def _client(self):
        from openai import OpenAI
        return OpenAI()

    def _chat(self, client, messages):
        resp = client.chat.completions.create(
            model=self.model, messages=messages,
            temperature=0.2, max_tokens=600,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content.strip()

    @staticmethod
    def _parse(raw: str):
        if not raw:
            return None
        txt = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        try:
            return json.loads(txt)
        except Exception:
            m = re.search(r"\{.*\}", txt, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    return None
            return None
