"""
memory.py
=========
[Memory Pattern] 사용자 선호(음식 종류, 가격대, 방문 목적, 지역)를 세션 동안 기억하고,
다음 요청에서 조건이 부족할 때 기억한 값을 기본값으로 채워 넣는다.

parse.py 역할도 겸함: 자연어 요청에서 조건(slot)을 추출한다.
"""

import re
from .tools import FOOD_SYNONYMS, AMBIGUOUS_FOOD_WORDS


class UserMemory:
    """대화 세션 동안 사용자 선호를 누적 저장."""

    def __init__(self):
        self.prefs = {
            "region": None,
            "landmark": None,
            "food_type": None,
            "max_price_level": None,
            "purpose": None,
        }
        self.history = []  # 과거 추천 기록

    def update(self, parsed: dict):
        """이번 요청에서 새로 파악된 값만 갱신(None이면 기존 값 유지)."""
        for k in self.prefs:
            v = parsed.get(k)
            if v is not None:
                self.prefs[k] = v

    def fill_defaults(self, parsed: dict) -> dict:
        """이번 요청에 빠진 조건을 기억한 선호로 보완."""
        filled = dict(parsed)
        used = []
        for k, v in self.prefs.items():
            if filled.get(k) is None and v is not None:
                filled[k] = v
                used.append(f"{k}={v}")
        filled["_memory_filled"] = used
        return filled

    def remember_result(self, query, names):
        self.history.append({"query": query, "recommended": names})

    def snapshot(self):
        return {k: v for k, v in self.prefs.items() if v is not None}


# 방문 목적 키워드
PURPOSE_MAP = {
    "친구": ["친구", "친구랑", "친구들", "동기", "지인"],
    "데이트": ["데이트", "여자친구", "남자친구", "애인", "썸", "소개팅"],
    "가족": ["가족", "부모님", "엄마", "아빠", "아이", "어른"],
    "회식": ["회식", "팀", "직장", "동료"],
    "혼밥": ["혼밥", "혼자", "1인"],
    "기념일": ["기념일", "생일", "프로포즈", "결혼"],
}

# 가격 표현 → max_price_level
def _parse_price(text: str):
    cheap = ["저렴", "싼", "싸게", "가성비", "비싸지 않", "안 비싼", "부담 없", "부담없"]
    mid = ["적당한 가격", "보통", "무난"]
    high = ["비싼", "고급", "분위기 좋은 고급", "파인다이닝", "프리미엄"]
    if any(w in text for w in cheap):
        return 2  # 너무 비싸지 않게 → 2 이하
    if any(w in text for w in high):
        return 4
    if any(w in text for w in mid):
        return 2
    return None


def _parse_count(text: str, default=3):
    m = re.search(r"(\d+)\s*(곳|개|군데)", text)
    if m:
        return int(m.group(1))
    return default


def _parse_food(text: str):
    """음식 종류 추출. 모호어만 있으면 'ambiguous' 플래그를 함께 반환."""
    for ftype, words in FOOD_SYNONYMS.items():
        if any(w in text for w in words):
            return ftype, False
    # 음식 관련 모호어만 있는지 확인
    if any(w in text for w in AMBIGUOUS_FOOD_WORDS):
        return None, True
    return None, False


# 지역/랜드마크 사전(파서용) — tools의 데이터와 일치시킴
REGION_HINTS = {
    "전주": ["전주"],
    "서울": ["서울"],
}
LANDMARK_HINTS = {
    "객사": ["객사", "객리단길"],
    "한옥마을": ["한옥마을"],
    "전북대": ["전북대"],
    "홍대": ["홍대", "합정"],
}


def parse_request(text: str) -> dict:
    """자연어 요청 → 조건(slot) 딕셔너리.

    반환 키: region, landmark, food_type, max_price_level, purpose,
            count, food_ambiguous, raw
    """
    text = text.strip()

    region = None
    for r, hints in REGION_HINTS.items():
        if any(h in text for h in hints):
            region = r
            break

    landmark = None
    for lm, hints in LANDMARK_HINTS.items():
        if any(h in text for h in hints):
            landmark = lm
            # 랜드마크로 지역 보강
            if region is None:
                if lm in ("객사", "한옥마을", "전북대"):
                    region = "전주"
                elif lm == "홍대":
                    region = "서울"
            break

    # 알려진 지역/랜드마크가 없으면, '○○ 근처/에서/주변' 패턴에서 후보 지역명을 추출.
    # (전국 지원: 카카오 키가 있으면 validate_region이 좌표를 찾아주고,
    #  없으면 'region_not_found' 대안을 안내함)
    if region is None:
        # 트리거 단어(근처/주변/에서/맛집/쪽/일대) 앞의 1~3어절을 위치로 본다.
        m = re.search(r"([가-힣A-Za-z0-9]+(?:\s+[가-힣A-Za-z0-9]+){0,2})\s*"
                      r"(?:근처|주변|에서|일대|쪽|맛집)", text)
        if m:
            cand = m.group(1).strip()
            # 끝에 붙은 트리거 단어 제거 (예: '부산 해운대 근처' → '부산 해운대')
            cand = re.sub(r"\s*(근처|주변|에서|일대|쪽)$", "", cand).strip()
            # 위치가 아닌 흔한 앞말 제거
            for junk in ("친구랑", "친구", "혼자", "가족이랑", "가족", "데이트", "오늘", "내일", "저녁", "점심"):
                cand = cand.replace(junk, "").strip()
            cand = re.sub(r"\s{2,}", " ", cand).strip()
            if cand:
                region = cand

    # 트리거가 없는 경우(예: '제주 애월 카페 2곳') 문장 앞부분에서 위치 추출:
    # 음식/목적/개수/필러 단어가 나오기 전까지의 앞쪽 어절을 위치로 본다.
    if region is None:
        _food_words = {w for ws in FOOD_SYNONYMS.values() for w in ws}
        _purpose_words = {w for ws in PURPOSE_MAP.values() for w in ws}
        _stop = _food_words | _purpose_words | {
            "맛집", "추천", "추천해줘", "해줘", "먹을", "먹고", "먹기", "곳", "가고",
            "싶어", "좀", "알려줘", "찾아줘", "근처", "주변", "저녁", "점심", "아침",
        }
        loc_tokens = []
        for tok in text.split():
            t = re.sub(r"\d+(곳|개|군데)?", "", tok).strip()
            if not t:
                continue
            if any(s in tok for s in _stop):
                break
            loc_tokens.append(t)
            if len(loc_tokens) >= 3:
                break
        cand = " ".join(loc_tokens).strip()
        if cand:
            region = cand

    food_type, food_ambiguous = _parse_food(text)
    max_price = _parse_price(text)

    purpose = None
    for p, words in PURPOSE_MAP.items():
        if any(w in text for w in words):
            purpose = p
            break

    # 식사(밥) 맥락인지: 저녁/점심/아침/식사/밥 등이 들어가면 True
    meal_context = any(w in text for w in
                       ("저녁", "점심", "아침", "식사", "끼니", "밥", "디너", "런치", "한끼"))

    return {
        "region": region,
        "landmark": landmark,
        "food_type": food_type,
        "max_price_level": max_price,
        "purpose": purpose,
        "count": _parse_count(text),
        "food_ambiguous": food_ambiguous,
        "meal_context": meal_context,
        "raw": text,
    }
