"""Pure classification metrics (no LLM / IO), so the eval's reported numbers are themselves tested.

Operates on (gold, predicted) label pairs and a fixed label ordering.
"""

from __future__ import annotations

from dataclasses import dataclass

Pair = tuple[str, str]  # (gold_label, predicted_label)


def accuracy(pairs: list[Pair]) -> float:
    if not pairs:
        return 0.0
    return sum(1 for gold, pred in pairs if gold == pred) / len(pairs)


def confusion_matrix(pairs: list[Pair], labels: list[str]) -> dict[str, dict[str, int]]:
    """matrix[gold][predicted] = count. Rows are the true label, columns the prediction."""
    matrix = {g: {p: 0 for p in labels} for g in labels}
    for gold, pred in pairs:
        if gold in matrix and pred in matrix[gold]:
            matrix[gold][pred] += 1
    return matrix


@dataclass
class ClassMetrics:
    precision: float
    recall: float
    f1: float
    support: int  # number of gold examples of this class


def _safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


def per_class_metrics(pairs: list[Pair], labels: list[str]) -> dict[str, ClassMetrics]:
    out: dict[str, ClassMetrics] = {}
    for label in labels:
        tp = sum(1 for g, p in pairs if g == label and p == label)
        fp = sum(1 for g, p in pairs if g != label and p == label)
        fn = sum(1 for g, p in pairs if g == label and p != label)
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        f1 = _safe_div(2 * precision * recall, precision + recall)
        out[label] = ClassMetrics(precision, recall, f1, support=tp + fn)
    return out


def macro_f1(pairs: list[Pair], labels: list[str]) -> float:
    """Unweighted mean F1 across classes that have at least one gold example."""
    metrics = [m for m in per_class_metrics(pairs, labels).values() if m.support]
    return _safe_div(sum(m.f1 for m in metrics), len(metrics))
