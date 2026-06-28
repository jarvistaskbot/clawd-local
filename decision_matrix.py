"""
Weighted decision matrix — objective multi-criteria option ranking.

Usage:
    from decision_matrix import DecisionMatrix

    dm = DecisionMatrix("Which cloud provider?")
    dm.add_criterion("Cost", weight=9)
    dm.add_criterion("Performance", weight=7)
    dm.add_criterion("Ease of use", weight=5)

    dm.add_option("AWS",    scores={"Cost": 6, "Performance": 9, "Ease of use": 7})
    dm.add_option("GCP",    scores={"Cost": 7, "Performance": 8, "Ease of use": 6})
    dm.add_option("Hetzner",scores={"Cost": 9, "Performance": 7, "Ease of use": 8})

    print(dm.render())
    winner = dm.winner()
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Criterion:
    name: str
    weight: float  # 1–10


@dataclass
class Option:
    name: str
    scores: Dict[str, float]  # criterion name → score 1–10


class DecisionMatrix:
    def __init__(self, question: str):
        self.question = question
        self.criteria: List[Criterion] = []
        self.options: List[Option] = []

    def add_criterion(self, name: str, weight: float) -> "DecisionMatrix":
        self.criteria.append(Criterion(name=name, weight=weight))
        return self

    def add_option(self, name: str, scores: Dict[str, float]) -> "DecisionMatrix":
        self.options.append(Option(name=name, scores=scores))
        return self

    def _weighted_score(self, option: Option) -> float:
        total_weight = sum(c.weight for c in self.criteria)
        if total_weight == 0:
            return 0.0
        return sum(
            c.weight * option.scores.get(c.name, 0)
            for c in self.criteria
        ) / total_weight

    def results(self) -> List[Dict]:
        rows = []
        for opt in self.options:
            score = self._weighted_score(opt)
            rows.append({
                "name": opt.name,
                "weighted_score": round(score, 2),
                "scores": opt.scores,
            })
        rows.sort(key=lambda r: r["weighted_score"], reverse=True)
        return rows

    def winner(self) -> Dict:
        r = self.results()
        return r[0] if r else {}

    def _fmt_num(self, n: float) -> str:
        return str(int(n)) if n == int(n) else str(n)

    def _build_table(self) -> str:
        """
        Criteria-as-rows, options-as-columns table:

        ┌──────────────┬──────┬──────────┬──────────┐
        │ Criterion    │  Wt. │  AWS     │  GCP     │
        ├──────────────┼──────┼──────────┼──────────┤
        │ Cost         │   9  │    6     │    7     │
        │ Performance  │   7  │    9     │    8     │
        ├──────────────┼──────┼──────────┼──────────┤
        │ SCORE        │      │  7.55    │  7.36 ★  │
        └──────────────┴──────┴──────────┴──────────┘
        """
        results = self.results()
        if not results:
            return "No options."

        results_map = {r["name"]: r for r in results}
        top_score = results[0]["weighted_score"]

        # Column widths
        crit_w = max((len(c.name) for c in self.criteria), default=9)
        crit_w = max(crit_w, 9)  # min "Criterion"

        wt_w = max(4, max((len(self._fmt_num(c.weight)) for c in self.criteria), default=4))
        wt_w = max(wt_w, 4)  # min "Wt."

        score_max_len = max(
            len(f"{r['weighted_score']:.2f} ★") for r in results
        )
        opt_w = max(
            max((len(o.name) for o in self.options), default=7),
            score_max_len,
            7,
        )

        def sep(l, m, r, f="─"):
            parts = [f * (crit_w + 2), f * (wt_w + 2)]
            parts += [f * (opt_w + 2) for _ in self.options]
            return l + m.join(parts) + r

        def row(label, wt_str, cells):
            parts = [f" {label:<{crit_w}} ", f" {wt_str:^{wt_w}} "]
            parts += [f" {v:^{opt_w}} " for v in cells]
            return "│" + "│".join(parts) + "│"

        lines = []
        lines.append(sep("┌", "┬", "┐"))

        # Header
        opt_headers = [f"{o.name:^{opt_w}}" for o in self.options]
        lines.append(row(f"{'Criterion':<{crit_w}}", "Wt.", opt_headers))
        lines.append(sep("├", "┼", "┤"))

        # Criteria rows
        for c in self.criteria:
            vals = [
                f"{self._fmt_num(o.scores.get(c.name, 0)):^{opt_w}}"
                for o in self.options
            ]
            lines.append(row(c.name, self._fmt_num(c.weight), vals))

        lines.append(sep("├", "┼", "┤"))

        # Score row
        score_vals = []
        for opt in self.options:
            r = results_map.get(opt.name)
            sc = r["weighted_score"] if r else 0.0
            marker = " ★" if sc == top_score else ""
            score_vals.append(f"{sc:.2f}{marker}")
        lines.append(row("SCORE", "", score_vals))

        lines.append(sep("└", "┴", "┘"))
        return "\n".join(lines)

    def render(self) -> str:
        results = self.results()
        if not results:
            return "No options to evaluate."

        lines = [f"Decision: {self.question}", ""]
        lines.append(self._build_table())
        lines.append("")
        lines.append(f"Winner: {results[0]['name']}  ({results[0]['weighted_score']:.2f}/10)")
        if len(results) > 1:
            gap = round(results[0]["weighted_score"] - results[1]["weighted_score"], 2)
            lines.append(f"Margin: +{gap} over {results[1]['name']}")
        return "\n".join(lines)

    def render_telegram(self) -> str:
        """Telegram-friendly output with monospace table in code block."""
        results = self.results()
        if not results:
            return "No options."

        lines = [f"*{self.question}*", ""]
        lines.append("```")
        lines.append(self._build_table())
        lines.append("```")
        lines.append("")

        medals = ["🥇", "🥈", "🥉"]
        for i, r in enumerate(results):
            medal = medals[i] if i < 3 else f"{i + 1}."
            lines.append(f"{medal} *{r['name']}* — {r['weighted_score']:.2f}/10")

        lines.append("")
        winner = results[0]
        lines.append(f"Recommendation: *{winner['name']}*")
        if len(results) > 1:
            gap = round(winner["weighted_score"] - results[1]["weighted_score"], 2)
            lines.append(f"Wins by {gap} pts over {results[1]['name']}.")

        return "\n".join(lines)


def from_dict(data: dict) -> DecisionMatrix:
    """
    Build from a plain dict. Expected shape:
    {
        "question": "...",
        "criteria": [{"name": "Cost", "weight": 9}, ...],
        "options": [
            {"name": "AWS", "scores": {"Cost": 6, "Performance": 9}},
            ...
        ]
    }
    """
    dm = DecisionMatrix(data["question"])
    for c in data.get("criteria", []):
        dm.add_criterion(c["name"], c["weight"])
    for o in data.get("options", []):
        dm.add_option(o["name"], o["scores"])
    return dm
