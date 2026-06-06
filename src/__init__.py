"""맛집 추천 ReAct Agent 패키지.

이 패키지를 import 하는 시점에 두 가지 초기화를 수행한다.
  1) Windows 한글 콘솔(cp949)에서도 이모지/특수문자가 깨지거나 죽지 않도록
     표준 출력 인코딩을 UTF-8로 재설정한다. (`> file` 리다이렉트 포함)
  2) 프로젝트 루트의 .env 파일을 읽어 환경변수로 설정한다.
     (python-dotenv 등 외부 의존성 없이 직접 파싱 — 키 없으면 그냥 넘어감)
"""

import os
import sys
from pathlib import Path


def _fix_stdout_encoding():
    # Python 3.7+ : 표준 출력/에러를 UTF-8 로. cp949 환경의 UnicodeEncodeError 방지.
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _load_dotenv():
    candidates = [
        Path(__file__).resolve().parent.parent / ".env",  # 프로젝트 루트
        Path.cwd() / ".env",                               # 현재 작업 폴더
    ]
    seen = set()
    for env_path in candidates:
        if env_path in seen or not env_path.exists():
            continue
        seen.add(env_path)
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ and val:  # 셸 지정값 우선
                    os.environ[key] = val
        except Exception:
            pass


_fix_stdout_encoding()
_load_dotenv()
