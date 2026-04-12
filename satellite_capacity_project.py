from __future__ import annotations

import json
import os
import pickle
import tarfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
os.environ.setdefault("MPLCONFIGDIR", str((BASE_DIR / ".mpl-cache").resolve()))
os.environ.setdefault("XDG_CACHE_HOME", str((BASE_DIR / ".cache").resolve()))

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

DATASETS_DIR = BASE_DIR / "datasets"
RESULTS_DIR = BASE_DIR / "results"
MODELS_DIR = BASE_DIR / "models"

SAMPLE_ARCHIVE = DATASETS_DIR / "ip_addresses_sample.tar"
TIMES_ARCHIVE = DATASETS_DIR / "times.tar"
HOLIDAYS_CSV = DATASETS_DIR / "weekends_and_holidays.csv"

TOP_K_SERIES = 5
MIN_COVERAGE = 0.9
TEST_SIZE = 0.2


class OrdinaryLeastSquaresRegressor:
    def __init__(self, alpha: float = 1.0) -> None:
        self.alpha = alpha
        self.coefficients: np.ndarray | None = None
        self.x_mean: np.ndarray | None = None
        self.x_std: np.ndarray | None = None

    def fit(self, x: pd.DataFrame, y: pd.Series) -> None:
        x_values = x.to_numpy(dtype=float)
        self.x_mean = x_values.mean(axis=0)
        self.x_std = x_values.std(axis=0)
        self.x_std[self.x_std == 0] = 1.0
        x_scaled = (x_values - self.x_mean) / self.x_std
        x_matrix = np.column_stack([np.ones(len(x)), x_scaled])
        y_vector = y.to_numpy(dtype=float)
        identity = np.eye(x_matrix.shape[1])
        identity[0, 0] = 0.0
        xtx = x_matrix.T @ x_matrix
        xty = x_matrix.T @ y_vector
        self.coefficients = np.linalg.solve(xtx + self.alpha * identity, xty)

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        if self.coefficients is None or self.x_mean is None or self.x_std is None:
            raise RuntimeError("Модель OLS ещё не обучена.")
        x_scaled = (x.to_numpy(dtype=float) - self.x_mean) / self.x_std
        x_matrix = np.column_stack([np.ones(len(x)), x_scaled])
        return x_matrix @ self.coefficients


def ensure_directories() -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    MODELS_DIR.mkdir(exist_ok=True)
    (BASE_DIR / ".mpl-cache").mkdir(exist_ok=True)
    (BASE_DIR / ".cache").mkdir(exist_ok=True)


def validate_input_files() -> None:
    missing = []
    for path in [SAMPLE_ARCHIVE, TIMES_ARCHIVE, HOLIDAYS_CSV]:
        if not path.exists():
            missing.append(path.name)
    if missing:
        joined = ", ".join(missing)
        raise FileNotFoundError(
            "Не найдены входные файлы: "
            f"{joined}. Поместите их в каталог datasets/. "
            "Большой архив ip_addresses_sample.tar нужно скачать отдельно, см. README.md."
        )


def load_timescale(scale: str = "1_hour") -> pd.DataFrame:
    member_name = f"times/times_{scale}.csv"
    with tarfile.open(TIMES_ARCHIVE) as tar:
        with tar.extractfile(member_name) as handle:
            times_df = pd.read_csv(handle)
    times_df["time"] = pd.to_datetime(times_df["time"], utc=True)
    return times_df


def select_top_series(scale: str = "1_hour", top_k: int = TOP_K_SERIES) -> list[str]:
    prefix = f"ip_addresses_sample/agg_{scale}/"
    stats: list[tuple[str, int, float]] = []

    with tarfile.open(SAMPLE_ARCHIVE) as tar:
        members = [m for m in tar.getmembers() if m.name.startswith(prefix) and m.name.endswith(".csv")]
        max_points = 0

        for member in members:
            with tar.extractfile(member) as handle:
                df = pd.read_csv(handle, usecols=["id_time", "n_bytes"])

            series_id = Path(member.name).stem
            length = len(df)
            total_bytes = float(df["n_bytes"].sum())
            max_points = max(max_points, length)
            stats.append((series_id, length, total_bytes))

    min_points = int(max_points * MIN_COVERAGE)
    eligible = [row for row in stats if row[1] >= min_points]
    eligible.sort(key=lambda row: row[2], reverse=True)
    selected_ids = [series_id for series_id, _, _ in eligible[:top_k]]

    if len(selected_ids) < top_k:
        raise RuntimeError("Недостаточно рядов с нужным покрытием для построения агрегированного канала.")

    return selected_ids


def build_channel_dataset(scale: str = "1_hour", top_k: int = TOP_K_SERIES) -> tuple[pd.DataFrame, list[str]]:
    selected_ids = select_top_series(scale=scale, top_k=top_k)
    times_df = load_timescale(scale=scale)
    prefix = f"ip_addresses_sample/agg_{scale}/"
    frames = []

    with tarfile.open(SAMPLE_ARCHIVE) as tar:
        for series_id in selected_ids:
            member_name = f"{prefix}{series_id}.csv"
            with tar.extractfile(member_name) as handle:
                series_df = pd.read_csv(
                    handle,
                    usecols=["id_time", "n_bytes", "n_packets", "n_flows", "avg_duration", "avg_ttl"],
                )
            series_df["series_id"] = series_id
            frames.append(series_df)

    raw_df = pd.concat(frames, ignore_index=True)
    grouped = (
        raw_df.groupby("id_time", as_index=False)
        .agg(
            total_n_bytes=("n_bytes", "sum"),
            total_n_packets=("n_packets", "sum"),
            total_n_flows=("n_flows", "sum"),
            avg_duration=("avg_duration", "mean"),
            avg_ttl=("avg_ttl", "mean"),
        )
        .sort_values("id_time")
    )

    dataset = grouped.merge(times_df, on="id_time", how="left").sort_values("time").reset_index(drop=True)
    dataset.rename(columns={"time": "timestamp"}, inplace=True)

    if HOLIDAYS_CSV.exists():
        holidays = pd.read_csv(HOLIDAYS_CSV)
        holidays.columns = [col.strip().lower() for col in holidays.columns]
        holidays["date"] = pd.to_datetime(holidays["date"], utc=True)
        holidays["is_holiday"] = 1
        dataset["date"] = dataset["timestamp"].dt.floor("D")
        dataset = dataset.merge(holidays[["date", "is_holiday"]], on="date", how="left")
        dataset["is_holiday"] = dataset["is_holiday"].fillna(0).astype(int)
        dataset.drop(columns=["date"], inplace=True)
    else:
        dataset["is_holiday"] = 0

    dataset["hour"] = dataset["timestamp"].dt.hour
    dataset["day_of_week"] = dataset["timestamp"].dt.dayofweek
    dataset["month"] = dataset["timestamp"].dt.month
    dataset["is_weekend"] = (dataset["day_of_week"] >= 5).astype(int)
    dataset["hour_sin"] = np.sin(2 * np.pi * dataset["hour"] / 24)
    dataset["hour_cos"] = np.cos(2 * np.pi * dataset["hour"] / 24)
    dataset["dow_sin"] = np.sin(2 * np.pi * dataset["day_of_week"] / 7)
    dataset["dow_cos"] = np.cos(2 * np.pi * dataset["day_of_week"] / 7)

    return dataset, selected_ids


def create_features(dataset: pd.DataFrame) -> pd.DataFrame:
    df = dataset.copy()
    target_col = "total_n_bytes"

    for lag in [1, 2, 3, 6, 12, 24, 48, 72]:
        df[f"lag_{lag}"] = df[target_col].shift(lag)

    for window in [3, 6, 12, 24]:
        shifted = df[target_col].shift(1)
        df[f"rolling_mean_{window}"] = shifted.rolling(window=window).mean()
        df[f"rolling_std_{window}"] = shifted.rolling(window=window).std()

    df["packet_size_avg"] = df["total_n_bytes"] / df["total_n_packets"].replace(0, np.nan)
    df["bytes_per_flow"] = df["total_n_bytes"] / df["total_n_flows"].replace(0, np.nan)
    df["packet_size_avg"] = df["packet_size_avg"].shift(1)
    df["bytes_per_flow"] = df["bytes_per_flow"].shift(1)
    df["flow_change"] = df["total_n_flows"].shift(1).pct_change()
    df["packet_change"] = df["total_n_packets"].shift(1).pct_change()

    df = df.replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)
    return df


def train_test_split_time(df: pd.DataFrame, test_size: float = TEST_SIZE) -> tuple[pd.DataFrame, pd.DataFrame]:
    split_index = int(len(df) * (1 - test_size))
    return df.iloc[:split_index].copy(), df.iloc[split_index:].copy()


def evaluate_regression(y_true: pd.Series, y_pred: np.ndarray) -> dict[str, float]:
    y_true_arr = y_true.to_numpy(dtype=float)
    y_pred_arr = y_pred.astype(float)
    mse = np.mean((y_true_arr - y_pred_arr) ** 2)
    mae = np.mean(np.abs(y_true_arr - y_pred_arr))
    safe_denominator = np.clip(np.abs(y_true_arr), a_min=1.0, a_max=None)
    mape = np.mean(np.abs((y_true_arr - y_pred_arr) / safe_denominator)) * 100
    ss_res = np.sum((y_true_arr - y_pred_arr) ** 2)
    ss_tot = np.sum((y_true_arr - y_true_arr.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    return {
        "MAE": float(mae),
        "RMSE": float(np.sqrt(mse)),
        "MAPE": float(mape),
        "R2": float(r2),
    }


def train_models(train_df: pd.DataFrame, test_df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, np.ndarray], dict[str, object], list[str]]:
    feature_cols = [
        col
        for col in train_df.columns
        if col not in {
            "timestamp",
            "id_time",
            "total_n_bytes",
            "total_n_packets",
            "total_n_flows",
            "avg_duration",
            "avg_ttl",
        }
    ]

    x_train = train_df[feature_cols]
    x_test = test_df[feature_cols]
    y_train = train_df["total_n_bytes"]
    y_test = test_df["total_n_bytes"]

    metrics_rows = []
    predictions = {}
    fitted_models = {}

    baseline_predictions = {
        "NaiveLastValue": test_df["lag_1"].to_numpy(dtype=float),
        "SeasonalNaive24": test_df["lag_24"].to_numpy(dtype=float),
    }
    for model_name, pred in baseline_predictions.items():
        predictions[model_name] = pred
        fitted_models[model_name] = {"type": "baseline", "name": model_name}
        metrics_rows.append({"model": model_name, **evaluate_regression(y_test, pred)})

    ols_model = OrdinaryLeastSquaresRegressor()
    ols_model.fit(x_train, y_train)
    ols_pred = ols_model.predict(x_test)
    predictions["OLSRegression"] = ols_pred
    fitted_models["OLSRegression"] = ols_model
    metrics_rows.append({"model": "OLSRegression", **evaluate_regression(y_test, ols_pred)})

    metrics_df = pd.DataFrame(metrics_rows).sort_values("RMSE").reset_index(drop=True)
    return metrics_df, predictions, fitted_models, feature_cols


def evaluate_policy(actual: pd.Series, allocated: np.ndarray) -> dict[str, float]:
    actual_values = actual.to_numpy(dtype=float)
    allocated_values = allocated.astype(float)
    overload = np.clip(actual_values - allocated_values, a_min=0, a_max=None)
    unused = np.clip(allocated_values - actual_values, a_min=0, a_max=None)

    served_ratio = np.minimum(actual_values, allocated_values).sum() / actual_values.sum()
    return {
        "mean_allocated": float(np.mean(allocated_values)),
        "overload_rate": float(np.mean(actual_values > allocated_values) * 100),
        "total_overload_bytes": float(overload.sum()),
        "mean_overload_bytes": float(overload.mean()),
        "total_unused_bytes": float(unused.sum()),
        "mean_unused_bytes": float(unused.mean()),
        "served_traffic_ratio": float(served_ratio * 100),
    }


def build_control_policy(train_df: pd.DataFrame, test_df: pd.DataFrame, forecast: np.ndarray) -> pd.DataFrame:
    train_target = train_df["total_n_bytes"]
    test_target = test_df["total_n_bytes"]

    min_capacity = float(train_target.quantile(0.45))
    max_capacity = float(train_target.quantile(0.98))
    reserve_margin = float(train_target.quantile(0.10))
    baseline_capacity = np.full(len(test_df), float(train_target.quantile(0.75)))

    dynamic_capacity = np.clip(forecast * 1.12 + reserve_margin, min_capacity, max_capacity)

    control_df = test_df[["timestamp", "total_n_bytes"]].copy()
    control_df["forecast_n_bytes"] = forecast
    control_df["baseline_capacity"] = baseline_capacity
    control_df["dynamic_capacity"] = dynamic_capacity

    policy_metrics = pd.DataFrame(
        [
            {"policy": "BaselineFixedCapacity", **evaluate_policy(test_target, baseline_capacity)},
            {"policy": "ForecastDrivenCapacity", **evaluate_policy(test_target, dynamic_capacity)},
        ]
    )
    return control_df, policy_metrics


def save_artifacts(
    channel_df: pd.DataFrame,
    featured_df: pd.DataFrame,
    model_metrics: pd.DataFrame,
    control_df: pd.DataFrame,
    policy_metrics: pd.DataFrame,
    best_model_name: str,
    best_model: object,
    feature_cols: list[str],
    selected_ids: list[str],
) -> None:
    channel_df.to_csv(RESULTS_DIR / "channel_dataset.csv", index=False)
    featured_df.to_csv(RESULTS_DIR / "channel_dataset_featured.csv", index=False)
    model_metrics.to_csv(RESULTS_DIR / "model_metrics.csv", index=False)
    control_df.to_csv(RESULTS_DIR / "capacity_control_results.csv", index=False)
    policy_metrics.to_csv(RESULTS_DIR / "policy_metrics.csv", index=False)

    with open(MODELS_DIR / "best_satellite_capacity_model.pkl", "wb") as handle:
        pickle.dump(best_model, handle)
    with open(MODELS_DIR / "feature_columns.pkl", "wb") as handle:
        pickle.dump(feature_cols, handle)

    summary = {
        "selected_series_ids": selected_ids,
        "best_model": best_model_name,
        "records_after_feature_engineering": int(len(featured_df)),
    }
    (RESULTS_DIR / "run_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))


def make_plots(control_df: pd.DataFrame, model_metrics: pd.DataFrame) -> None:
    plot_df = control_df.tail(240).copy()

    fig, ax = plt.subplots(figsize=(16, 6))
    ax.plot(plot_df["timestamp"], plot_df["total_n_bytes"], label="Фактическая нагрузка", linewidth=2)
    ax.plot(plot_df["timestamp"], plot_df["forecast_n_bytes"], label="Прогноз", linewidth=2, linestyle="--")
    ax.plot(plot_df["timestamp"], plot_df["baseline_capacity"], label="Фиксированная ёмкость", linewidth=1.5)
    ax.plot(plot_df["timestamp"], plot_df["dynamic_capacity"], label="Адаптивная ёмкость", linewidth=1.5)
    ax.set_title("Прогноз нагрузки и управление пропускной способностью")
    ax.set_xlabel("Время")
    ax.set_ylabel("Объём трафика, bytes/hour")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "capacity_control_plot.png", dpi=200)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5))
    colors = ["steelblue", "seagreen", "darkorange"][: len(model_metrics)]
    ax.bar(model_metrics["model"], model_metrics["RMSE"], color=colors)
    ax.set_title("Сравнение моделей по RMSE")
    ax.set_ylabel("RMSE")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "model_rmse_comparison.png", dpi=200)
    plt.close(fig)


def main() -> None:
    ensure_directories()
    validate_input_files()

    channel_df, selected_ids = build_channel_dataset(scale="1_hour", top_k=TOP_K_SERIES)
    featured_df = create_features(channel_df)
    train_df, test_df = train_test_split_time(featured_df)

    model_metrics, predictions, fitted_models, feature_cols = train_models(train_df, test_df)
    best_model_name = model_metrics.iloc[0]["model"]
    best_prediction = predictions[best_model_name]
    best_model = fitted_models[best_model_name]

    control_df, policy_metrics = build_control_policy(train_df, test_df, best_prediction)
    save_artifacts(
        channel_df=channel_df,
        featured_df=featured_df,
        model_metrics=model_metrics,
        control_df=control_df,
        policy_metrics=policy_metrics,
        best_model_name=best_model_name,
        best_model=best_model,
        feature_cols=feature_cols,
        selected_ids=selected_ids,
    )
    make_plots(control_df, model_metrics)

    print("Выбранные ряды:", ", ".join(selected_ids))
    print("\nМетрики моделей:")
    print(model_metrics.to_string(index=False))
    print("\nМетрики политик управления:")
    print(policy_metrics.to_string(index=False))
    print(f"\nЛучшая модель сохранена: {MODELS_DIR / 'best_satellite_capacity_model.pkl'}")


if __name__ == "__main__":
    main()
