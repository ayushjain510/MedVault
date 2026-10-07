# MedVault — Model Evaluation Report

Dataset: synthetic-v1 (seed 42) · Trained: 2026-08-24T08:02:27.481964+00:00 · Model version 2.0 · Feature version 1.1

Reproducibility check (Review 3, 2026-10-06): the model binaries are not shipped
with the source archive, so they were regenerated with `features.py` → `train.py`
→ `explain.py`. The resulting `report.json` and `global_importance.json` are
identical to the originals apart from the training timestamp — same selected
model for every task and the same metrics as the tables below.

Patient-level split: 166 train / 32 val / 42 test patients (archetype-stratified, disjoint).
Four models compared per task: Logistic Regression, Random Forest, XGBoost, LightGBM.
Selection: 0.55·macro-recall + 0.45·macro-F1 on validation (never accuracy).

Labels derive from disjoint observable subsystems; recovery and antibiotic response
look forward 12 h, and right-censored rows (no observable outcome window) are excluded
from all splits — see `label_definitions.md`.

## Recovery

Classes: RT-0 Improving, RT-1 Stable, RT-2 Slow recovery, RT-3 Persistent concern, RT-4 Worsening, RT-5 Insufficient evidence

**Selected model: random_forest**

| Model | Split | Accuracy | Prec (macro) | Recall (macro) | F1 (macro) | F1 (wtd) | ROC-AUC | PR-AUC | Brier |
|---|---|---|---|---|---|---|---|---|---|
| logistic_regression | val | 0.596 | 0.559 | 0.636 | 0.589 | 0.591 | 0.881 | — | — |
| logistic_regression | test | 0.632 | 0.604 | 0.655 | 0.622 | 0.634 | 0.894 | — | — |
| random_forest | val | 0.689 | 0.630 | 0.682 | 0.637 | 0.666 | 0.909 | — | — |
| random_forest | test | 0.712 | 0.672 | 0.722 | 0.689 | 0.708 | 0.920 | — | — |
| xgboost | val | 0.667 | 0.616 | 0.659 | 0.632 | 0.659 | 0.911 | — | — |
| xgboost | test | 0.712 | 0.675 | 0.698 | 0.683 | 0.708 | 0.926 | — | — |
| lightgbm | val | 0.674 | 0.615 | 0.656 | 0.629 | 0.660 | 0.909 | — | — |
| lightgbm | test | 0.709 | 0.675 | 0.691 | 0.680 | 0.705 | 0.925 | — | — |

## Antibiotic Response

Classes: AR-0 Improving, AR-1 Stable / no clear change, AR-2 Uncertain, AR-3 Poor response, AR-4 Worsening

**Selected model: random_forest**

| Model | Split | Accuracy | Prec (macro) | Recall (macro) | F1 (macro) | F1 (wtd) | ROC-AUC | PR-AUC | Brier |
|---|---|---|---|---|---|---|---|---|---|
| logistic_regression | val | 0.904 | 0.768 | 0.827 | 0.791 | 0.910 | 0.982 | — | — |
| logistic_regression | test | 0.866 | 0.740 | 0.818 | 0.758 | 0.877 | 0.974 | — | — |
| random_forest | val | 0.929 | 0.827 | 0.850 | 0.836 | 0.931 | 0.988 | — | — |
| random_forest | test | 0.907 | 0.811 | 0.856 | 0.826 | 0.910 | 0.985 | — | — |
| xgboost | val | 0.934 | 0.835 | 0.841 | 0.837 | 0.935 | 0.989 | — | — |
| xgboost | test | 0.909 | 0.817 | 0.846 | 0.829 | 0.911 | 0.990 | — | — |
| lightgbm | val | 0.933 | 0.836 | 0.835 | 0.834 | 0.934 | 0.989 | — | — |
| lightgbm | test | 0.915 | 0.825 | 0.854 | 0.836 | 0.917 | 0.990 | — | — |

## Fluid Status

Classes: FS-0 Stable fluid trajectory, FS-1 Monitor closely, FS-2 Increasing positive balance, FS-3 Significant accumulation concern, FS-4 Possible inadequate hemodynamic response, FS-5 Insufficient data

**Selected model: lightgbm**

| Model | Split | Accuracy | Prec (macro) | Recall (macro) | F1 (macro) | F1 (wtd) | ROC-AUC | PR-AUC | Brier |
|---|---|---|---|---|---|---|---|---|---|
| logistic_regression | val | 0.851 | 0.757 | 0.828 | 0.781 | 0.854 | 0.984 | — | — |
| logistic_regression | test | 0.853 | 0.801 | 0.852 | 0.822 | 0.856 | 0.984 | — | — |
| random_forest | val | 0.951 | 0.925 | 0.930 | 0.924 | 0.951 | 0.996 | — | — |
| random_forest | test | 0.942 | 0.922 | 0.931 | 0.923 | 0.942 | 0.996 | — | — |
| xgboost | val | 0.973 | 0.961 | 0.972 | 0.966 | 0.973 | 1.000 | — | — |
| xgboost | test | 0.969 | 0.959 | 0.965 | 0.962 | 0.969 | 0.999 | — | — |
| lightgbm | val | 0.976 | 0.962 | 0.974 | 0.968 | 0.976 | 1.000 | — | — |
| lightgbm | test | 0.970 | 0.960 | 0.963 | 0.961 | 0.970 | 0.999 | — | — |

## Sepsis State

Classes: Stable, At Risk, Active Sepsis, Severe/Deteriorating, Treatment Response, Recovery, Non-responding, Escalation

**Selected model: xgboost**

| Model | Split | Accuracy | Prec (macro) | Recall (macro) | F1 (macro) | F1 (wtd) | ROC-AUC | PR-AUC | Brier |
|---|---|---|---|---|---|---|---|---|---|
| logistic_regression | val | 0.863 | 0.740 | 0.752 | 0.733 | 0.863 | 0.981 | — | — |
| logistic_regression | test | 0.810 | 0.713 | 0.726 | 0.712 | 0.812 | 0.972 | — | — |
| random_forest | val | 0.887 | 0.777 | 0.762 | 0.756 | 0.882 | 0.987 | — | — |
| random_forest | test | 0.857 | 0.781 | 0.769 | 0.767 | 0.854 | 0.981 | — | — |
| xgboost | val | 0.899 | 0.804 | 0.779 | 0.778 | 0.894 | 0.988 | — | — |
| xgboost | test | 0.864 | 0.789 | 0.775 | 0.773 | 0.861 | 0.982 | — | — |
| lightgbm | val | 0.896 | 0.799 | 0.769 | 0.770 | 0.890 | 0.988 | — | — |
| lightgbm | test | 0.863 | 0.781 | 0.768 | 0.765 | 0.858 | 0.982 | — | — |

## Deterioration 6H

Classes: No deterioration, Deterioration ≤6h

**Selected model: random_forest**

| Model | Split | Accuracy | Prec (macro) | Recall (macro) | F1 (macro) | F1 (wtd) | ROC-AUC | PR-AUC | Brier |
|---|---|---|---|---|---|---|---|---|---|
| logistic_regression | val | 0.802 | 0.737 | 0.796 | 0.754 | 0.813 | 0.882 | 0.666 | 0.140 |
| logistic_regression | test | 0.799 | 0.750 | 0.810 | 0.764 | 0.810 | 0.889 | 0.709 | 0.142 |
| random_forest | val | 0.853 | 0.790 | 0.834 | 0.807 | 0.858 | 0.913 | 0.742 | 0.104 |
| random_forest | test | 0.841 | 0.787 | 0.827 | 0.802 | 0.846 | 0.914 | 0.752 | 0.107 |
| xgboost | val | 0.855 | 0.792 | 0.820 | 0.804 | 0.859 | 0.914 | 0.737 | 0.105 |
| xgboost | test | 0.835 | 0.779 | 0.779 | 0.779 | 0.835 | 0.915 | 0.763 | 0.109 |
| lightgbm | val | 0.851 | 0.787 | 0.810 | 0.797 | 0.854 | 0.912 | 0.719 | 0.108 |
| lightgbm | test | 0.830 | 0.773 | 0.778 | 0.775 | 0.831 | 0.914 | 0.762 | 0.111 |

## Deterioration 12H

Classes: No deterioration, Deterioration ≤12h

**Selected model: random_forest**

| Model | Split | Accuracy | Prec (macro) | Recall (macro) | F1 (macro) | F1 (wtd) | ROC-AUC | PR-AUC | Brier |
|---|---|---|---|---|---|---|---|---|---|
| logistic_regression | val | 0.765 | 0.724 | 0.767 | 0.734 | 0.775 | 0.847 | 0.605 | 0.162 |
| logistic_regression | test | 0.806 | 0.780 | 0.821 | 0.789 | 0.813 | 0.885 | 0.729 | 0.142 |
| random_forest | val | 0.866 | 0.827 | 0.871 | 0.843 | 0.870 | 0.929 | 0.777 | 0.101 |
| random_forest | test | 0.847 | 0.817 | 0.835 | 0.824 | 0.849 | 0.924 | 0.808 | 0.104 |
| xgboost | val | 0.863 | 0.823 | 0.854 | 0.836 | 0.866 | 0.933 | 0.792 | 0.099 |
| xgboost | test | 0.847 | 0.821 | 0.816 | 0.818 | 0.847 | 0.925 | 0.814 | 0.107 |
| lightgbm | val | 0.859 | 0.819 | 0.842 | 0.829 | 0.861 | 0.936 | 0.795 | 0.097 |
| lightgbm | test | 0.842 | 0.814 | 0.810 | 0.812 | 0.841 | 0.926 | 0.818 | 0.108 |

## Deterioration 24H

Classes: No deterioration, Deterioration ≤24h

**Selected model: random_forest**

| Model | Split | Accuracy | Prec (macro) | Recall (macro) | F1 (macro) | F1 (wtd) | ROC-AUC | PR-AUC | Brier |
|---|---|---|---|---|---|---|---|---|---|
| logistic_regression | val | 0.779 | 0.750 | 0.785 | 0.758 | 0.786 | 0.853 | 0.623 | 0.160 |
| logistic_regression | test | 0.800 | 0.778 | 0.820 | 0.785 | 0.807 | 0.886 | 0.734 | 0.143 |
| random_forest | val | 0.888 | 0.862 | 0.888 | 0.872 | 0.890 | 0.943 | 0.850 | 0.092 |
| random_forest | test | 0.834 | 0.803 | 0.816 | 0.809 | 0.835 | 0.917 | 0.800 | 0.110 |
| xgboost | val | 0.875 | 0.848 | 0.868 | 0.857 | 0.877 | 0.941 | 0.854 | 0.092 |
| xgboost | test | 0.842 | 0.815 | 0.811 | 0.813 | 0.841 | 0.917 | 0.806 | 0.115 |
| lightgbm | val | 0.877 | 0.850 | 0.869 | 0.858 | 0.879 | 0.946 | 0.864 | 0.089 |
| lightgbm | test | 0.838 | 0.811 | 0.808 | 0.809 | 0.838 | 0.915 | 0.798 | 0.118 |

## Calibration

Binary deterioration tasks include 10-bin quantile calibration curves in `ml/models/report.json`
(`calibration.mean_predicted` vs `calibration.fraction_positive`) alongside Brier scores.

## Notes

- See `error_analysis.md` for false-positive/false-negative analysis.
- All metrics reflect SYNTHETIC data; see `limitations.md`.