"""
trace.py
========
Agent의 판단 과정을 단계별로 기록/출력하는 Trace 로거.
과제 제출용 "도구 호출 Trace"를 생성한다.
"""

import json


class Trace:
    def __init__(self):
        self.steps = []

    def _add(self, kind, **kw):
        self.steps.append({"kind": kind, **kw})

    def plan(self, plan):           self._add("PLAN", plan=plan)
    def thought(self, text):        self._add("THOUGHT", text=text)
    def action(self, name, inp):    self._add("ACTION", name=name, input=inp)
    def observation(self, obs):     self._add("OBSERVATION", obs=obs)
    def reflection(self, text):     self._add("REFLECTION", text=text)
    def memory(self, text):         self._add("MEMORY", text=text)
    def final(self, text):          self._add("FINAL", text=text)
    def error(self, text):          self._add("ERROR", text=text)

    # 콘솔 출력용 렌더링
    def render(self):
        icons = {
            "PLAN": "🗂  [Plan-and-Solve] 계획",
            "THOUGHT": "💭 Thought",
            "ACTION": "🔧 Action",
            "OBSERVATION": "👀 Observation",
            "REFLECTION": "🔁 [Reflection] 자기검토",
            "MEMORY": "🧠 [Memory]",
            "FINAL": "✅ Final Answer",
            "ERROR": "⚠️  오류 감지",
        }
        lines = []
        for i, s in enumerate(self.steps, 1):
            head = icons.get(s["kind"], s["kind"])
            if s["kind"] == "PLAN":
                lines.append(f"{head}:")
                for j, p in enumerate(s["plan"], 1):
                    lines.append(f"     {j}) {p}")
            elif s["kind"] == "ACTION":
                lines.append(f"{head}: {s['name']}")
                lines.append(f"     input = {json.dumps(s['input'], ensure_ascii=False)}")
            elif s["kind"] == "OBSERVATION":
                obs = s["obs"]
                if isinstance(obs, dict):
                    summary = {k: obs[k] for k in ("ok", "tool", "error", "meta") if k in obs}
                    if isinstance(obs.get("data"), list):
                        n = len(obs["data"])
                    elif "count" in obs:
                        n = obs["count"]
                    else:
                        n = "-"
                    lines.append(f"{head}: ok={obs.get('ok')} tool={obs.get('tool')} "
                                 f"결과수={n}")
                    if obs.get("error"):
                        lines.append(f"     error: {obs['error']}")
                    if obs.get("note"):
                        lines.append(f"     note: {obs['note']}")
                    if obs.get("sample"):
                        lines.append(f"     sample: {', '.join(obs['sample'][:5])}")
                    if obs.get("meta"):
                        lines.append(f"     meta: {json.dumps(obs['meta'], ensure_ascii=False)}")
                else:
                    lines.append(f"{head}: {obs}")
            else:
                lines.append(f"{head}: {s.get('text','')}")
        return "\n".join(lines)

    def as_dict(self):
        return self.steps
