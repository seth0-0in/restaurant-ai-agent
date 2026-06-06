"""
agent.py
========
맛집 추천 ReAct Agent (실행 루프 본체)

적용한 Agentic Design Pattern
  1) ReAct          : Thought → Action → Observation 반복으로 도구를 호출하며 추론  (필수)
  2) Tool Use       : 검색/거리/평점/가격/랭킹 등 여러 도구를 Agent가 직접 호출
  3) Plan-and-Solve : 요청을 (지역검증→검색→거리→평점→가격→랭킹) 단계로 분해해 계획 수립
  4) Reflection     : 추천 결과가 조건/개수를 만족하는지 스스로 검토하고 조건을 완화해 보완
  5) Memory         : 사용자의 음식/가격/목적/지역 선호를 기억해 다음 요청의 부족 조건을 보완

예외 처리(모두 'Observation으로 에러를 받고 → 대안 제시' 방식)
  - 존재하지 않는 지역      → 지원 지역 안내 후 종료
  - 검색 결과 없음          → 음식종류/거리/가격/평점 순으로 조건 완화 재검색
  - 음식 종류가 모호함      → 전체 종류로 넓혀 검색하고 사용자에게 안내
  - API 호출 실패           → 샘플 데이터로 폴백 (tools.py에서 처리, Observation에 기록)
  - 사용자 조건 부족        → Memory로 보완, 그래도 지역이 없으면 되물음
"""

from . import tools
from .memory import UserMemory, parse_request
from .trace import Trace
from . import llm


class MatjipAgent:
    def __init__(self, memory: UserMemory = None, verbose: bool = True):
        self.memory = memory or UserMemory()
        self.verbose = verbose

    # ------------------------------------------------------------------
    # 공개 진입점
    # ------------------------------------------------------------------
    def run(self, query: str) -> dict:
        trace = Trace()

        # --- [Memory] 요청 파싱 + 기억된 선호로 부족 조건 보완 ---
        parsed = parse_request(query)
        filled = self.memory.fill_defaults(parsed)
        if filled.get("_memory_filled"):
            trace.memory(f"이전 선호로 보완: {', '.join(filled['_memory_filled'])}")
        self.memory.update(filled)

        dinner_only = ("저녁" in query) or ("디너" in query)
        good_review = ("리뷰" in query) or ("평점" in query) or ("맛있" in query)
        top_k = filled.get("count") or 3

        # --- 조건 부족 처리: 지역 자체가 없으면 되물음 ---
        if not filled.get("region"):
            trace.thought("요청에 지역 정보가 없고, 기억된 선호에도 지역이 없다. "
                          "검색 기준을 잡을 수 없으므로 사용자에게 지역을 되물어야 한다.")
            msg = ("어느 지역에서 찾아드릴까요? (예: '전주 객사 근처', '서울 홍대') "
                   "지역을 알려주시면 조건에 맞춰 추천하겠습니다.")
            trace.final(msg)
            return self._result(msg, [], trace, status="need_more_info")

        # --- [Plan-and-Solve] 계획 수립 ---
        plan = [
            f"지역/랜드마크 검증: region={filled.get('region')}, landmark={filled.get('landmark')}",
            f"맛집 검색: food_type={filled.get('food_type') or '전체'}, "
            f"{'저녁영업만' if dinner_only else '영업시간 무관'}",
            "거리 필터(랜드마크 기준 반경 내)",
            f"평점/리뷰 필터({'엄격' if good_review else '기본'})",
            f"가격 필터(max_price_level={filled.get('max_price_level') or '제한없음'})",
            f"점수화 후 상위 {top_k}곳 추천",
        ]
        trace.plan(plan)

        # 음식 종류 모호 안내
        if filled.get("food_ambiguous") and not filled.get("food_type"):
            trace.thought("음식 종류 표현이 모호하다('맛있는 거' 등). 특정 종류로 좁히지 않고 "
                          "전체 종류를 대상으로 검색한 뒤, 점수가 높은 곳을 추천하겠다.")

        # ===================== ReAct 루프 시작 =====================

        # [Step 1] 지역 검증
        trace.thought(llm.narrate_thought(
            f"사용자가 '{filled.get('region')} {filled.get('landmark') or ''}' 맛집을 원한다. "
            f"먼저 지역이 실제 존재하는지 검증한다.",
            f"먼저 '{filled.get('region')} {filled.get('landmark') or ''}'가 실제 지원되는 "
            f"지역/랜드마크인지 validate_region으로 확인한다."))
        trace.action("validate_region",
                     {"region": filled["region"], "landmark": filled.get("landmark") or ""})
        obs = tools.validate_region(filled["region"], filled.get("landmark") or "")
        trace.observation(obs)

        if not obs["ok"]:
            # 존재하지 않는 지역/랜드마크 → 대안 제시 후 종료
            trace.thought("지역 검증에 실패했다. 임의로 검색하지 않고, Observation에 담긴 "
                          "지원 가능 후보를 사용자에게 안내하겠다.")
            msg = f"입력하신 위치를 찾지 못했어요. {obs['error']}\n다시 지역을 알려주시면 추천해 드릴게요."
            trace.final(msg)
            return self._result(msg, [], trace, status="region_not_found")

        center = obs["data"].get("coord")
        canonical_region = obs["data"]["region"]
        canonical_landmark = obs["data"].get("landmark")

        # [Step 2] 맛집 검색
        trace.thought(llm.narrate_thought(
            f"지역 검증 통과. 이제 {canonical_region} {canonical_landmark or ''}의 "
            f"{filled.get('food_type') or '전체'} 맛집을 검색한다.",
            "지역이 확인됐으니 search_restaurants로 후보 맛집을 가져온다."))
        # 식사 맥락(저녁/점심/밥 등)인데 디저트·카페를 콕 집어 요청한 게 아니면 제외
        exclude_cd = bool(filled.get("meal_context")) and \
            filled.get("food_type") not in ("카페", "디저트")
        search_args = {"region": canonical_region,
                       "landmark": canonical_landmark or "",
                       "food_type": filled.get("food_type") or "",
                       "dinner_only": dinner_only,
                       "center": center,
                       "exclude_cafe_dessert": exclude_cd}
        trace.action("search_restaurants", search_args)
        obs = tools.search_restaurants(**search_args)
        trace.observation(obs)
        candidates = obs["data"]

        # 검색 결과 0건 → [Reflection] 조건 완화 (음식종류 먼저 해제)
        if not candidates:
            trace.reflection("검색 결과가 0건이다. 음식 종류 조건이 너무 좁았을 수 있으니 "
                             "음식 종류 제한을 풀고 다시 검색한다.")
            search_args2 = dict(search_args, food_type="")
            trace.action("search_restaurants", search_args2)
            obs = tools.search_restaurants(**search_args2)
            trace.observation(obs)
            candidates = obs["data"]

        if not candidates:
            trace.reflection("음식 종류를 풀어도 결과가 없다. 저녁영업 조건까지 해제해 본다.")
            search_args3 = dict(search_args, food_type="", dinner_only=False)
            trace.action("search_restaurants", search_args3)
            obs = tools.search_restaurants(**search_args3)
            trace.observation(obs)
            candidates = obs["data"]

        if not candidates:
            trace.thought("모든 완화에도 후보가 없다. 더 진행할 수 없어 솔직히 안내한다.")
            msg = (f"'{canonical_region} {canonical_landmark or ''}' 주변에서 조건에 맞는 곳을 "
                   "찾지 못했어요. 지역이나 음식 종류를 바꿔 다시 시도해 주세요.")
            trace.final(msg)
            return self._result(msg, [], trace, status="no_result")

        # [Step 3] 거리 필터 (랜드마크 좌표 기준)
        max_km = 1.0
        trace.thought(f"후보 {len(candidates)}곳 확보. '{canonical_landmark}' 기준 반경 "
                      f"{max_km}km 이내로 좁힌다.")
        trace.action("filter_by_distance",
                     {"center": center, "max_km": max_km})
        obs = tools.filter_by_distance(candidates, center, max_km=max_km)
        trace.observation(obs)
        near = obs["data"] if obs["data"] else candidates  # 좌표 없으면 원본 유지

        # [Step 4] 평점/리뷰 필터
        min_rating = 4.0 if good_review else 3.5
        min_reviews = 500 if good_review else 100
        trace.thought(f"높은 품질 기준을 적용해 평점 {min_rating}+ / 리뷰 {min_reviews}+ 인 곳만 거른다."
                      if good_review else "기본 품질 기준으로 거른다.")
        trace.action("filter_by_rating", {"min_rating": min_rating, "min_reviews": min_reviews})
        obs = tools.filter_by_rating(near, min_rating=min_rating, min_reviews=min_reviews)
        trace.observation(obs)
        rated = obs["data"]

        # [Step 5] 가격 필터
        max_price = filled.get("max_price_level") or 4
        trace.thought(f"가격 조건 적용: price_level {max_price} 이하만 남긴다."
                      if filled.get("max_price_level") else "가격 제한이 없어 전체 가격대를 유지한다.")
        trace.action("filter_by_price", {"max_price_level": max_price})
        obs = tools.filter_by_price(rated, max_price_level=max_price)
        trace.observation(obs)
        priced = obs["data"]

        # [Reflection] 결과 개수 검토 후 조건 완화
        priced = self._reflect_and_relax(
            priced, near, trace,
            want=top_k, min_rating=min_rating, min_reviews=min_reviews, max_price=max_price)

        # [Step 6] 랭킹/추천
        trace.thought(f"조건을 만족하는 {len(priced)}곳을 평점·리뷰·거리·방문목적으로 점수화해 "
                      f"상위 {top_k}곳을 고른다.")
        trace.action("rank_restaurants", {"purpose": filled.get("purpose") or "", "top_k": top_k})
        obs = tools.rank_restaurants(priced, purpose=filled.get("purpose") or "", top_k=top_k)
        trace.observation(obs)
        final_list = obs["data"]

        # 최종 답변 작성
        answer = self._compose(final_list, filled, canonical_region, canonical_landmark, trace)
        self.memory.remember_result(query, [r["name"] for r in final_list])
        trace.memory(f"현재 기억된 선호: {self.memory.snapshot()}")
        return self._result(answer, final_list, trace, status="ok")

    # ------------------------------------------------------------------
    # [Reflection] 결과가 부족하면 조건을 단계적으로 완화
    # ------------------------------------------------------------------
    def _reflect_and_relax(self, current, pool, trace, want, min_rating, min_reviews, max_price):
        if len(current) >= want:
            trace.reflection(f"추천 후보가 {len(current)}곳으로 요청 개수({want})를 충족한다. "
                             "조건 완화 없이 진행한다.")
            return current

        trace.reflection(f"조건을 만족하는 후보가 {len(current)}곳뿐이라 요청 {want}곳에 부족하다. "
                         "가격 → 평점 순으로 조건을 완화해 재검토한다.")

        # 1) 가격 한 단계 완화
        if max_price < 4:
            relaxed_price = max_price + 1
            trace.action("filter_by_price", {"max_price_level": relaxed_price})
            obs = tools.filter_by_price(pool, max_price_level=relaxed_price)
            trace.observation(obs)
            obs2 = tools.filter_by_rating(obs["data"], min_rating=min_rating, min_reviews=min_reviews)
            trace.observation(obs2)
            if len(obs2["data"]) >= want:
                trace.reflection(f"가격을 price_level {relaxed_price}까지 허용하니 {len(obs2['data'])}곳 확보.")
                return obs2["data"]
            current = obs2["data"] or current

        # 2) 평점 기준 완화
        relaxed_rating = round(min_rating - 0.4, 1)
        trace.action("filter_by_rating", {"min_rating": relaxed_rating, "min_reviews": 50})
        obs = tools.filter_by_rating(pool, min_rating=relaxed_rating, min_reviews=50)
        trace.observation(obs)
        obs2 = tools.filter_by_price(obs["data"], max_price_level=min(max_price + 1, 4))
        trace.observation(obs2)
        if len(obs2["data"]) >= len(current):
            trace.reflection(f"평점 기준을 {relaxed_rating}로 낮춰 {len(obs2['data'])}곳 확보. "
                             "그래도 가능한 한 좋은 곳을 우선 추천한다.")
            return obs2["data"]
        return current

    # ------------------------------------------------------------------
    # 최종 답변 작성 (LLM 있으면 LLM, 없으면 규칙기반)
    # ------------------------------------------------------------------
    def _compose(self, items, filled, region, landmark, trace):
        if not items:
            msg = "조건에 맞는 곳을 찾지 못했어요. 조건을 조금 완화해 다시 시도해 주세요."
            trace.final(msg)
            return msg

        lines = [f"'{region} {landmark or ''}' 근처 추천 맛집 {len(items)}곳입니다 👇\n"]
        payload_items = []
        for i, r in enumerate(items, 1):
            price = tools.PRICE_LABEL.get(r.get("price_level"), "가격정보 없음")
            dist = f"{r['distance_km']*1000:.0f}m" if r.get("distance_km") is not None else "거리정보 없음"
            rating = r.get("rating")
            reviews = r.get("review_count")
            rinfo = f"평점 {rating}/리뷰 {reviews}개" if rating else "평점정보 없음(카카오)"
            extra = f"\n   - 카카오: {r['place_url']}" if r.get("place_url") else ""
            lines.append(
                f"{i}. {r['name']}  ({r.get('food_type','')})\n"
                f"   - {rinfo} | {price} | {landmark}에서 {dist}\n"
                f"   - 대표메뉴: {r.get('signature_menu','-')}\n"
                f"   - {r.get('description','')}{extra}")
            payload_items.append({
                "name": r["name"], "food_type": r.get("food_type"),
                "rating": rating, "review_count": reviews,
                "price": price, "distance": dist,
                "signature_menu": r.get("signature_menu"),
                "description": r.get("description"),
            })
        rule_based = "\n".join(lines)

        # LLM이 있으면 자연어 추천문 보강
        answer = llm.compose_answer(
            {"user_conditions": {
                "region": region, "landmark": landmark,
                "food_type": filled.get("food_type") or "전체",
                "purpose": filled.get("purpose"),
                "max_price_level": filled.get("max_price_level")},
             "recommendations": payload_items},
            fallback=rule_based)
        trace.final(answer)
        return answer

    @staticmethod
    def _result(answer, items, trace, status):
        return {"answer": answer, "items": items, "status": status, "trace": trace}
