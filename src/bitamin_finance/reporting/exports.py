from __future__ import annotations

from pathlib import Path

import pandas as pd

from bitamin_finance.validation.event_study import decile_summary, fit_event_regression


def export_validation_report(
    validation_frame: pd.DataFrame,
    output_dir: str | Path,
    prefix: str,
) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    validation_csv = output_path / f"{prefix}_validation_rows.csv"
    regression_csv = output_path / f"{prefix}_regression.csv"
    decile_csv = output_path / f"{prefix}_deciles.csv"
    validation_frame.to_csv(validation_csv, index=False)
    fit_event_regression(validation_frame).to_csv(regression_csv, index=False)
    decile_summary(validation_frame).to_csv(decile_csv, index=False)
    return {
        "validation": validation_csv,
        "regression": regression_csv,
        "deciles": decile_csv,
    }

