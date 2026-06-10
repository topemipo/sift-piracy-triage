"""Triage model: predict probability a takedown candidate will be actioned.
(PRD FR-5.x)

Two approaches for comparison:
  - baseline: interpretable logistic regression (statistical modelling)
  - challenger: gradient-boosted trees (XGBoost)
Output probabilities must be calibrated, and per-prediction feature contributions
exposed so the dashboard can explain WHY a candidate ranks highly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ModelType = Literal["logistic_regression", "xgboost"]


@dataclass
class TriageModel:
    """Wraps a fitted estimator + the feature columns it expects."""

    estimator: object
    feature_cols: list[str]
    model_type: ModelType
    explanation_estimator: object | None = None
    calibrated: bool = False

    def predict_proba(self, X: pd.DataFrame) -> pd.Series:
        """Return calibrated probability of action for each row."""
        X_model = _select_features(X, self.feature_cols)
        probabilities = self.estimator.predict_proba(X_model)[:, 1]
        return pd.Series(probabilities, index=X.index, name="action_probability")

    def explain(self, X: pd.DataFrame) -> pd.DataFrame:
        """Return top feature contributions per row for the dashboard.

        The dashboard needs compact per-row reasons, not a full model-debugging
        object. For the logistic baseline we use signed coefficient
        contributions after the fitted preprocessing pipeline. For XGBoost we
        use feature importances multiplied by each row's value as a lightweight
        approximation; SHAP can be added later if the project needs deeper tree
        explanations.
        """
        X_model = _select_features(X, self.feature_cols)
        if self.explanation_estimator is None:
            raise ValueError("No explanation estimator was stored with this model")

        if self.model_type == "logistic_regression":
            contributions = _linear_contributions(
                self.explanation_estimator, X_model, self.feature_cols
            )
        else:
            contributions = _importance_contributions(
                self.explanation_estimator, X_model, self.feature_cols
            )

        rows: list[dict[str, object]] = []
        for idx, row in contributions.iterrows():
            ordered = row.reindex(row.abs().sort_values(ascending=False).index).head(3)
            rows.append(
                {
                    "index": idx,
                    "top_features": [
                        {
                            "feature": feature,
                            "contribution": float(value),
                            "direction": "up" if value >= 0 else "down",
                        }
                        for feature, value in ordered.items()
                    ],
                }
            )
        return pd.DataFrame(rows).set_index("index")


def train_baseline(X: pd.DataFrame, y: pd.Series) -> TriageModel:
    """Fit calibrated logistic regression baseline."""
    feature_cols = list(X.columns)
    X_model = _select_features(X, feature_cols)
    y_model = _validate_target(y)

    base = _logistic_pipeline()
    estimator, calibrated = _fit_calibrated(base, X_model, y_model)

    explanation_estimator = _logistic_pipeline()
    explanation_estimator.fit(X_model, y_model)

    return TriageModel(
        estimator=estimator,
        feature_cols=feature_cols,
        model_type="logistic_regression",
        explanation_estimator=explanation_estimator,
        calibrated=calibrated,
    )


def train_challenger(X: pd.DataFrame, y: pd.Series) -> TriageModel:
    """Fit calibrated XGBoost challenger."""
    try:
        from xgboost import XGBClassifier
    except Exception as exc:  # pragma: no cover - environment-specific
        raise RuntimeError(
            "XGBoost could not be imported. On macOS this usually means the "
            "OpenMP runtime is missing; install libomp before training the "
            "challenger model."
        ) from exc

    feature_cols = list(X.columns)
    X_model = _select_features(X, feature_cols)
    y_model = _validate_target(y)

    base = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            (
                "model",
                XGBClassifier(
                    objective="binary:logistic",
                    eval_metric="logloss",
                    n_estimators=250,
                    max_depth=4,
                    learning_rate=0.05,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    random_state=42,
                    n_jobs=2,
                ),
            ),
        ]
    )
    estimator, calibrated = _fit_calibrated(base, X_model, y_model)

    explanation_estimator = base
    explanation_estimator.fit(X_model, y_model)

    return TriageModel(
        estimator=estimator,
        feature_cols=feature_cols,
        model_type="xgboost",
        explanation_estimator=explanation_estimator,
        calibrated=calibrated,
    )


def _select_features(X: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    """Select model columns and coerce them to numeric values."""
    missing = [col for col in feature_cols if col not in X.columns]
    if missing:
        raise ValueError(f"Missing model feature columns: {missing}")
    return X.loc[:, feature_cols].apply(pd.to_numeric, errors="coerce")


def _validate_target(y: pd.Series) -> pd.Series:
    """Return a clean binary target, raising if a classifier cannot be fitted."""
    y_model = y.astype("int8")
    if y_model.nunique() != 2:
        raise ValueError("Triage training requires both positive and negative labels")
    return y_model


def _logistic_pipeline() -> Pipeline:
    """Baseline estimator with preprocessing for numeric features."""
    return Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    max_iter=1000,
                    class_weight="balanced",
                    random_state=42,
                ),
            ),
        ]
    )


def _fit_calibrated(
    base_estimator: object, X: pd.DataFrame, y: pd.Series
) -> tuple[object, bool]:
    """Fit sigmoid-calibrated classifier when the label counts allow it."""
    min_class_count = int(y.value_counts().min())
    cv = min(3, min_class_count)
    if cv < 2:
        base_estimator.fit(X, y)
        return base_estimator, False

    calibrated = CalibratedClassifierCV(
        estimator=base_estimator,
        method="sigmoid",
        cv=cv,
    )
    calibrated.fit(X, y)
    return calibrated, True


def _linear_contributions(
    estimator: Pipeline, X: pd.DataFrame, feature_cols: list[str]
) -> pd.DataFrame:
    """Signed per-feature contributions for the logistic baseline."""
    imputed = estimator.named_steps["imputer"].transform(X)
    scaled = estimator.named_steps["scaler"].transform(imputed)
    coefficients = estimator.named_steps["model"].coef_[0]
    values = scaled * coefficients
    return pd.DataFrame(values, index=X.index, columns=feature_cols)


def _importance_contributions(
    estimator: Pipeline, X: pd.DataFrame, feature_cols: list[str]
) -> pd.DataFrame:
    """Approximate per-row XGBoost reasons from feature importances."""
    imputed = estimator.named_steps["imputer"].transform(X)
    model = estimator.named_steps["model"]
    importances = getattr(model, "feature_importances_", np.ones(len(feature_cols)))
    values = imputed * importances
    return pd.DataFrame(values, index=X.index, columns=feature_cols)
