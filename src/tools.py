"""
tools.py
========
Agent가 호출하는 '도구(Tool)' 모음 — [Tool Use Pattern]

각 도구는 표준화된 결과 형태를 반환한다:
    {"ok": bool, "data": ..., "error": str|None, "tool": str}
Agent는 이 결과를 'Observation'으로 받아 다음 행동을 결정한다.
오류가 나도 예외를 던지지 않고 ok=False 형태의 Observation을 돌려준다.
(과제 요구사항: "Agent가 Observation으로 에러를 받은 뒤 대안을 제시"하도록)
"""

import json
import math
import os
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "restaurants.json"

# 음식 종류 동의어/모호어 매핑
FOOD_SYNONYMS = {
    "한식": ["한식", "한정식", "비빔밥", "국밥", "곱창", "고기", "구이", "삼겹살", "국수"],
    "일식": ["일식", "스시", "초밥", "라멘", "돈까스", "돈카츠", "오마카세", "우동"],
    "양식": ["양식", "파스타", "스파게티", "피자", "버거", "햄버거", "스테이크", "리조또"],
    "중식": ["중식", "중국집", "짜장", "짬뽕", "마라탕", "마라샹궈", "탕수육"],
    "카페": ["카페", "커피", "브런치"],
    "디저트": ["디저트", "케이크", "타르트", "베이커리", "빵"],
    "주점": ["주점", "술집", "한잔", "술한", "술 한", "소주", "안주", "막걸리",
             "포차", "이자카야", "맥주", "호프", "와인", "칵테일", "펍"],
}

# 너무 모호해서 '음식 종류'로 못 쓰는 막연한 표현들
# (주의: '맛집'처럼 거의 모든 요청에 들어가는 일반어는 제외)
AMBIGUOUS_FOOD_WORDS = {"맛있는", "아무거나", "뭔가", "먹을거", "먹을것", "암거나"}


def _load_data():
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _haversine_km(lat1, lng1, lat2, lng2):
    """두 좌표 사이 거리(km) — [거리 계산 도구]의 내부 계산식."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _kakao_geocode(query: str):
    """카카오로 임의의 지역/랜드마크의 대표 좌표를 조회(전국). 키 없거나 실패 시 None.

    '키워드로 장소 검색' 첫 결과의 좌표를 그 지역의 중심으로 사용한다.
    (예: '부산 해운대', '강남역', '제주 애월' 등 전국 어디든)
    """
    if not os.getenv("KAKAO_API_KEY") or not query.strip():
        return None
    try:
        import requests
        key = os.getenv("KAKAO_API_KEY")
        resp = requests.get(
            "https://dapi.kakao.com/v2/local/search/keyword.json",
            headers={"Authorization": f"KakaoAK {key}"},
            params={"query": query.strip(), "size": 1}, timeout=5)
        resp.raise_for_status()
        docs = resp.json().get("documents", [])
        if docs and docs[0].get("x") and docs[0].get("y"):
            return {"lat": float(docs[0]["y"]), "lng": float(docs[0]["x"])}
    except Exception as e:  # pragma: no cover - 네트워크 의존
        print(f"   [경고] 카카오 지오코딩 실패({e})")
    return None


# ---------------------------------------------------------------------------
# 도구 1) 지역/랜드마크 검증 도구
# ---------------------------------------------------------------------------
def validate_region(region: str, landmark: str = "") -> dict:
    """입력된 지역/랜드마크가 데이터에 존재하는지 검증한다.

    존재하지 않으면 ok=False + 비슷한 후보를 알려줘 Agent가 대안을 제시하게 한다.
    """
    tool = "validate_region"
    data = _load_data()["regions"]
    region = (region or "").strip()
    landmark = (landmark or "").strip()

    # 1) 먼저 샘플 데이터에서 찾는다 (오프라인/키 없는 환경 대응)
    matched_region = None
    for rname, rinfo in data.items():
        if any(a in region or region in a for a in rinfo["aliases"] if region):
            matched_region = rname
            break
        if rname == region:
            matched_region = rname
            break

    if matched_region:
        if landmark:
            for lname, linfo in data[matched_region]["landmarks"].items():
                if any(a in landmark or landmark in a for a in linfo["aliases"]):
                    return {"ok": True, "tool": tool, "error": None,
                            "data": {"region": matched_region, "landmark": lname,
                                     "coord": {"lat": linfo["lat"], "lng": linfo["lng"]},
                                     "source": "sample"}}
            # 지역은 샘플에 있으나 랜드마크가 없으면 → 아래 카카오 지오코딩으로 시도
        else:
            return {"ok": True, "tool": tool, "error": None,
                    "data": {"region": matched_region, "landmark": None, "coord": None,
                             "source": "sample"}}

    # 2) 샘플에 없으면(또는 랜드마크 미발견) 카카오로 전국 좌표 조회 (키 있을 때)
    geo_query = f"{region} {landmark}".strip()
    coord = _kakao_geocode(geo_query)
    if coord:
        return {"ok": True, "tool": tool, "error": None,
                "data": {"region": region or geo_query,
                         "landmark": landmark or region or geo_query,
                         "coord": coord, "source": "kakao_geocode"}}

    # 3) 끝내 못 찾음
    known = list(data.keys())
    if os.getenv("KAKAO_API_KEY"):
        msg = (f"'{geo_query}' 위치를 카카오에서 찾지 못했습니다. "
               f"지명을 더 정확히(시/구/동 또는 유명 랜드마크) 입력해 주세요.")
    else:
        msg = (f"'{region}'을(를) 찾을 수 없습니다. 샘플 데이터 지원 지역: {known}. "
               f"전국 검색을 원하면 KAKAO_API_KEY 를 설정하세요.")
    return {"ok": False, "tool": tool, "data": None, "error": msg}


# ---------------------------------------------------------------------------
# 도구 2) 맛집 검색 도구 (지역 + 음식 종류)
# ---------------------------------------------------------------------------
def search_restaurants(region: str, landmark: str = "", food_type: str = "",
                       dinner_only: bool = False, center: dict = None,
                       exclude_cafe_dessert: bool = False) -> dict:
    """지역/랜드마크/음식종류로 맛집 후보를 검색한다.

    - 외부 API(KAKAO_API_KEY)가 설정돼 있으면 그쪽을 시도하고, 실패 시 샘플 데이터로 폴백.
    - center(기준 좌표)가 주어지면 그 좌표 주변(전국 어디든)을 검색한다.
    - exclude_cafe_dessert=True 이면(식사 맥락) 카페/디저트 업종을 결과에서 제외한다.
    - 결과가 0건이면 ok=True지만 data=[] → Agent가 조건 완화 판단을 하도록.
    """
    tool = "search_restaurants"

    # (선택) 외부 API 경로 — 키가 있을 때만. 실패하면 Observation에 실패를 남기고 폴백.
    if os.getenv("KAKAO_API_KEY"):
        center = center or _landmark_coord(region, landmark)
        api_result = _try_kakao_search(region, landmark, food_type, center,
                                       exclude_cafe_dessert)
        if api_result is not None:
            return api_result
        # api_result is None -> API 실패, 아래 샘플 데이터로 폴백 (에러를 메모로 남김)

    items = _load_data()["restaurants"]
    region = (region or "").strip()
    food_type = (food_type or "").strip()

    results = []
    for r in items:
        if region and region not in r["region"] and r["region"] not in region:
            continue
        if landmark and landmark.strip() and landmark.strip() != r["area"]:
            # 랜드마크가 지정되면 같은 area만(거리 필터는 별도 도구가 처리)
            # 단, 같은 지역의 다른 area도 후보로 남기되 area 일치를 우선시하기 위해 표시만.
            pass
        if food_type and food_type not in AMBIGUOUS_FOOD_WORDS:
            if r["food_type"] != food_type:
                continue
        # 식사 맥락이면 카페/디저트 제외 (단, 그 종류를 직접 요청한 경우는 위 food_type 분기에서 통과)
        if exclude_cafe_dessert and r["food_type"] in ("카페", "디저트"):
            continue
        if dinner_only and not r.get("open_dinner", True):
            continue
        results.append(r)

    return {"ok": True, "tool": tool, "error": None,
            "data": results,
            "meta": {"count": len(results), "region": region,
                     "landmark": landmark, "food_type": food_type}}


def _landmark_coord(region, landmark):
    """샘플 데이터의 지역/랜드마크 사전에서 기준 좌표를 찾아 반환(없으면 None)."""
    data = _load_data()["regions"]
    region = (region or "").strip()
    landmark = (landmark or "").strip()
    for rname, rinfo in data.items():
        if region and not (region in rname or rname in region
                           or any(a in region or region in a for a in rinfo["aliases"])):
            continue
        for lname, linfo in rinfo["landmarks"].items():
            if landmark and (landmark == lname
                             or any(a in landmark or landmark in a for a in linfo["aliases"])):
                return {"lat": linfo["lat"], "lng": linfo["lng"]}
    return None


# 카카오 카테고리 그룹 코드 (음식점 FD6 / 카페 CE7)
_KAKAO_CATEGORY = {"카페": "CE7", "디저트": "CE7"}

# 식당이 아닌데 FD6/검색결과에 섞여 들어오는 곳들 — 추천에서 제외
_NON_RESTAURANT = ("마트", "편의점", "식자재", "직판장", "도매", "무인", "슈퍼마켓",
                   "정육점", "농수산물", "푸드코트 매장")

# 카카오 category_name 문자열 → 우리 음식종류로 역매핑(추천 표시용)
def _infer_food_type(category_name: str) -> str:
    c = category_name or ""
    if "카페" in c or "디저트" in c or "베이커리" in c:
        return "카페" if "카페" in c else "디저트"
    if "일식" in c or "초밥" in c or "돈까스" in c or "라멘" in c:
        return "일식"
    if "중식" in c or "중국" in c:
        return "중식"
    if "양식" in c or "파스타" in c or "피자" in c or "햄버거" in c or "스테이크" in c:
        return "양식"
    if "한식" in c or "국밥" in c or "고기" in c or "찌개" in c:
        return "한식"
    if "술집" in c or "주점" in c or "호프" in c or "이자카야" in c:
        return "주점"
    return "기타"


def _try_kakao_search(region, landmark, food_type, center=None,
                      exclude_cafe_dessert=False):
    """카카오 로컬 '키워드로 장소 검색' API.
    문서: https://developers.kakao.com/docs/ko/local/dev-guide#search-by-keyword

    - 헤더 Authorization: KakaoAK {REST_API_KEY}
    - 좌표(center)가 있으면 x,y,radius,sort=distance 로 '랜드마크 주변' 검색
    - category_group_code 로 음식점(FD6)/카페(CE7) 한정
    - 주의: 카카오는 평점/리뷰를 제공하지 않으므로 rating/review_count=None 으로 둔다.
      (이후 filter_by_rating 은 None 항목을 통과시키도록 구현돼 있어 자연스럽게 무시됨)
    실패 시 None 반환 → 호출부가 샘플 데이터로 폴백.
    """
    try:
        import requests  # noqa
        key = os.getenv("KAKAO_API_KEY")

        ft = (food_type or "").strip()
        if ft in AMBIGUOUS_FOOD_WORDS:
            ft = ""
        # 음식 종류별 검색 키워드 (주점은 '술집'으로 검색해야 술집이 나온다)
        if ft == "주점":
            kw = "술집"
        elif ft in ("카페", "디저트"):
            kw = ft
        elif ft:
            kw = f"{ft} 맛집"
        else:
            kw = "맛집"
        # 중심 좌표가 있으면 위치는 좌표로 처리하므로 키워드만, 없으면 지역명을 앞에 붙임
        query = kw if center else f"{landmark or region} {kw}".strip()

        params = {"query": query, "size": 15,
                  "category_group_code": _KAKAO_CATEGORY.get(ft, "FD6")}
        if center:
            params.update({"x": center["lng"], "y": center["lat"],
                           "radius": 2000, "sort": "distance"})

        resp = requests.get(
            "https://dapi.kakao.com/v2/local/search/keyword.json",
            headers={"Authorization": f"KakaoAK {key}"},
            params=params, timeout=5)
        resp.raise_for_status()
        body = resp.json()
        docs = body.get("documents", [])

        results = []
        dropped = 0
        for d in docs:
            name = d.get("place_name", "") or ""
            cat = d.get("category_name", "") or ""
            # 식당이 아닌 곳(마트/편의점/도매 등) 제외 → 추천 품질 향상
            if any(b in name or b in cat for b in _NON_RESTAURANT):
                dropped += 1
                continue
            inferred = ft or _infer_food_type(cat)
            # 식사 맥락이면 카페/디저트(베이커리/제과/빙수 등) 제외
            if exclude_cafe_dessert and (
                    inferred in ("카페", "디저트")
                    or any(k in cat for k in ("카페", "디저트", "베이커리", "제과",
                                              "빙수", "아이스크림", "도넛", "빵"))):
                dropped += 1
                continue
            dist_m = d.get("distance")
            results.append({
                "id": d.get("id"),
                "name": d.get("place_name"),
                "region": region, "area": landmark or "",
                "food_type": inferred,
                "rating": None, "review_count": None, "price_level": None,
                "lat": float(d.get("y")) if d.get("y") else None,
                "lng": float(d.get("x")) if d.get("x") else None,
                "distance_km": round(int(dist_m) / 1000, 3) if dist_m else None,
                "good_for": [],
                "signature_menu": "",
                "open_dinner": True,
                "phone": d.get("phone", ""),
                "place_url": d.get("place_url", ""),
                "description": d.get("road_address_name") or d.get("address_name") or "",
            })
        return {"ok": True, "tool": "search_restaurants(kakao)", "error": None,
                "data": results,
                "meta": {"count": len(results), "source": "kakao_api",
                         "query": query, "filtered_out": dropped,
                         "total_count": body.get("meta", {}).get("total_count")}}
    except Exception as e:  # pragma: no cover - 네트워크 의존
        # API 실패는 예외로 던지지 않고 None → 호출부가 샘플 데이터로 폴백
        print(f"   [경고] 카카오 API 호출 실패({e}) → 샘플 데이터로 폴백합니다.")
        return None


# ---------------------------------------------------------------------------
# 도구 3) 거리 필터 도구
# ---------------------------------------------------------------------------
def filter_by_distance(candidates: list, center: dict, max_km: float = 1.0) -> dict:
    """기준 좌표(center)에서 max_km 이내 맛집만 남기고 거리를 부여한다."""
    tool = "filter_by_distance"
    if not center:
        return {"ok": True, "tool": tool, "error": None, "data": candidates,
                "meta": {"note": "기준 좌표 없음 → 거리 필터 건너뜀"}}
    out = []
    for r in candidates:
        if r.get("lat") is None or r.get("lng") is None:
            continue
        dist = _haversine_km(center["lat"], center["lng"], r["lat"], r["lng"])
        if dist <= max_km:
            rr = dict(r)
            rr["distance_km"] = round(dist, 3)
            out.append(rr)
    out.sort(key=lambda x: x["distance_km"])
    return {"ok": True, "tool": tool, "error": None, "data": out,
            "meta": {"count": len(out), "max_km": max_km}}


# ---------------------------------------------------------------------------
# 도구 4) 평점/리뷰 필터 도구
# ---------------------------------------------------------------------------
def filter_by_rating(candidates: list, min_rating: float = 4.0,
                     min_reviews: int = 300) -> dict:
    """평점·리뷰수 기준으로 거른다. 평점 정보가 없는 항목(API 결과 등)은 통과시킨다."""
    tool = "filter_by_rating"
    out = []
    for r in candidates:
        rating = r.get("rating")
        reviews = r.get("review_count")
        if rating is None:
            out.append(r)
            continue
        if rating >= min_rating and (reviews is None or reviews >= min_reviews):
            out.append(r)
    return {"ok": True, "tool": tool, "error": None, "data": out,
            "meta": {"count": len(out), "min_rating": min_rating, "min_reviews": min_reviews}}


# ---------------------------------------------------------------------------
# 도구 5) 가격 필터 도구
# ---------------------------------------------------------------------------
PRICE_LABEL = {1: "저렴(~1만원)", 2: "보통(1~2만원)", 3: "다소높음(2~4만원)", 4: "높음(4만원+)"}


def filter_by_price(candidates: list, max_price_level: int = 4) -> dict:
    """가격대(price_level) 기준 필터. 가격 정보 없는 항목은 통과."""
    tool = "filter_by_price"
    out = []
    for r in candidates:
        pl = r.get("price_level")
        if pl is None or pl <= max_price_level:
            out.append(r)
    return {"ok": True, "tool": tool, "error": None, "data": out,
            "meta": {"count": len(out), "max_price_level": max_price_level,
                     "max_price_label": PRICE_LABEL.get(max_price_level, "")}}


# ---------------------------------------------------------------------------
# 도구 6) 추천 점수화 / 랭킹 도구
# ---------------------------------------------------------------------------
def rank_restaurants(candidates: list, purpose: str = "", top_k: int = 3) -> dict:
    """평점·리뷰·거리·목적 적합도를 합산해 점수를 매기고 상위 top_k를 반환한다."""
    tool = "rank_restaurants"
    scored = []
    for r in candidates:
        rating = r.get("rating") or 4.0
        reviews = r.get("review_count") or 0
        dist = r.get("distance_km")
        score = rating * 10  # 평점 비중
        score += min(reviews, 3000) / 600.0  # 리뷰 신뢰도(최대 +5)
        if dist is not None:
            score += max(0.0, (1.0 - dist)) * 3  # 가까울수록 가점
        if purpose and purpose in (r.get("good_for") or []):
            score += 4  # 방문 목적 적합 가점
        rr = dict(r)
        rr["_score"] = round(score, 2)
        scored.append(rr)
    scored.sort(key=lambda x: x["_score"], reverse=True)
    return {"ok": True, "tool": tool, "error": None, "data": scored[:top_k],
            "meta": {"ranked": len(scored), "top_k": top_k, "purpose": purpose}}


# 도구 레지스트리 — Agent/LLM가 참조하는 도구 카탈로그
TOOL_REGISTRY = {
    "validate_region": validate_region,
    "search_restaurants": search_restaurants,
    "filter_by_distance": filter_by_distance,
    "filter_by_rating": filter_by_rating,
    "filter_by_price": filter_by_price,
    "rank_restaurants": rank_restaurants,
}

TOOL_DESCRIPTIONS = {
    "validate_region": "지역/랜드마크가 실제 존재하는지 확인하고 기준 좌표를 반환",
    "search_restaurants": "지역+음식종류로 맛집 후보 목록 검색",
    "filter_by_distance": "기준 좌표에서 max_km 이내만 필터(거리 부여)",
    "filter_by_rating": "min_rating/min_reviews 이상만 필터",
    "filter_by_price": "max_price_level 이하 가격대만 필터",
    "rank_restaurants": "평점/리뷰/거리/목적으로 점수화 후 상위 top_k 반환",
}
