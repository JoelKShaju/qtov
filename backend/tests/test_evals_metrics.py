from __future__ import annotations

from evals.metrics import accuracy, confusion_matrix, macro_f1, per_class_metrics

LABELS = ["a", "b", "c"]


def test_accuracy():
    assert accuracy([("a", "a"), ("b", "b"), ("a", "b")]) == 2 / 3
    assert accuracy([]) == 0.0


def test_confusion_matrix_counts_gold_vs_pred():
    pairs = [("a", "a"), ("a", "b"), ("b", "b"), ("c", "a")]
    m = confusion_matrix(pairs, LABELS)
    assert m["a"]["a"] == 1 and m["a"]["b"] == 1  # one 'a' correct, one called 'b'
    assert m["b"]["b"] == 1
    assert m["c"]["a"] == 1  # a 'c' misclassified as 'a'
    assert m["c"]["c"] == 0


def test_per_class_precision_recall_f1():
    # class 'a': 2 gold; one predicted correctly, one missed; and one 'b' wrongly called 'a'.
    pairs = [("a", "a"), ("a", "b"), ("b", "a"), ("b", "b")]
    m = per_class_metrics(pairs, LABELS)["a"]
    assert m.support == 2
    assert m.precision == 0.5  # 1 TP / (1 TP + 1 FP)
    assert m.recall == 0.5  # 1 TP / (1 TP + 1 FN)
    assert m.f1 == 0.5


def test_metrics_handle_zero_division():
    # label 'c' has no gold and no predictions -> all zero, no crash.
    pairs = [("a", "a"), ("b", "b")]
    m = per_class_metrics(pairs, LABELS)["c"]
    assert m.precision == 0.0 and m.recall == 0.0 and m.f1 == 0.0 and m.support == 0


def test_macro_f1_averages_only_supported_classes():
    pairs = [("a", "a"), ("b", "b")]  # perfect on a and b; c has no support
    assert macro_f1(pairs, LABELS) == 1.0
