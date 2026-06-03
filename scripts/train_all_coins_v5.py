#!/usr/bin/env python3
"""
TRAIN ALL COINS V5
==================
Trains per-coin EnsembleV5 models for all configured tickers.
Saves results to PRODUCTION_SYSTEM/models/v5/{ticker}/

Usage:
    python scripts/train_all_coins_v5.py
    python scripts/train_all_coins_v5.py --tickers BTCUSDT ETHUSDT SOLUSDT
    python scripts/train_all_coins_v5.py --resume
    python scripts/train_all_coins_v5.py --global-model
    python scripts/train_all_coins_v5.py --dry-run
"""

import argparse
import sys
import time
from datetime import date
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from config import settings
from src.models.auto_trainer_v5 import AutoTrainerV5
from src.models.per_coin_model_store import PerCoinModelStore


# ============================================================
# CLI
# ============================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train per-coin EnsembleV5 models for Cryptonita.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/train_all_coins_v5.py
  python scripts/train_all_coins_v5.py --tickers BTCUSDT ETHUSDT SOLUSDT
  python scripts/train_all_coins_v5.py --resume
  python scripts/train_all_coins_v5.py --global-model
  python scripts/train_all_coins_v5.py --dry-run
        """,
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        metavar="TICKER",
        default=None,
        help="Train specific tickers (default: all from settings.TICKERS)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip tickers that already have a trained model (today's date check)",
    )
    parser.add_argument(
        "--global-model",
        action="store_true",
        dest="global_model",
        help="Also train a global model on all coins combined after per-coin training",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Show what would be trained but don't actually train",
    )
    return parser.parse_args()


# ============================================================
# OUTPUT FORMATTING
# ============================================================

def _fmt(value, decimals: int = 3) -> str:
    """Format a float or return 'N/A' for missing values."""
    if value is None:
        return "  N/A "
    return f"{float(value):.{decimals}f}"


def print_summary_table(results: dict, tickers: list) -> None:
    """Print the boxed summary table to stdout."""
    col_ticker  = 13
    col_metric  = 8

    header = (
        f"{'Ticker':<{col_ticker}} "
        f"{'OOS Acc':^{col_metric}} "
        f"{'Long F1':^{col_metric}} "
        f"{'Short F1':^{col_metric}} "
        f"{'Status':^8}"
    )
    sep_inner = (
        f"{'─' * col_ticker}─"
        f"{'─' * col_metric}─"
        f"{'─' * col_metric}─"
        f"{'─' * col_metric}─"
        f"{'─' * 8}"
    )
    total_width = len(header)

    print()
    print("╔" + "═" * total_width + "╗")
    print("║" + " CRYPTONITA V5 TRAINING COMPLETE".center(total_width) + "║")
    print("╚" + "═" * total_width + "╝")
    print()

    trained_count = sum(1 for t in tickers if results.get(t) is not None)
    print(f"Trained: {trained_count}/{len(tickers)} tickers")
    print()

    print("┌" + sep_inner.replace("─", "─") + "┐")
    print("│ " + header + " │")
    print("├" + sep_inner + "┤")

    for ticker in tickers:
        m = results.get(ticker)
        if m is None:
            status = "FAILED"
            row = (
                f"{ticker:<{col_ticker}} "
                f"{'  N/A ':^{col_metric}} "
                f"{'  N/A ':^{col_metric}} "
                f"{'  N/A ':^{col_metric}} "
                f"{status:^8}"
            )
        else:
            status = "OK"
            row = (
                f"{ticker:<{col_ticker}} "
                f"{_fmt(m.get('oos_accuracy')):^{col_metric}} "
                f"{_fmt(m.get('long_f1')):^{col_metric}} "
                f"{_fmt(m.get('short_f1')):^{col_metric}} "
                f"{status:^8}"
            )
        print("│ " + row + " │")

    print("└" + sep_inner + "┘")


def print_statistics(results: dict, tickers: list, store: PerCoinModelStore) -> None:
    """Print aggregate statistics after the table."""
    summary = store.get_training_summary()

    valid_acc = [
        float(results[t]["oos_accuracy"])
        for t in tickers
        if results.get(t) and results[t].get("oos_accuracy") is not None
    ]
    avg_acc = sum(valid_acc) / len(valid_acc) if valid_acc else 0.0

    print()
    print(f"Average OOS Accuracy : {avg_acc:.3f}")

    best_long  = summary.get("best_long")
    best_short = summary.get("best_short")

    if best_long:
        long_m = results.get(best_long) or {}
        print(f"Best LONG  : {best_long} (F1={_fmt(long_m.get('long_f1')).strip()})")
    if best_short:
        short_m = results.get(best_short) or {}
        print(f"Best SHORT : {best_short} (F1={_fmt(short_m.get('short_f1')).strip()})")

    print()


# ============================================================
# REPORT GENERATION
# ============================================================

def _find_previous_report(docs_dir: Path) -> Path | None:
    """Return the most recent TRAINING_V5_*.md file, excluding today's."""
    today_str = date.today().strftime("%Y-%m-%d")
    candidates = sorted(docs_dir.glob("TRAINING_V5_*.md"), reverse=True)
    for p in candidates:
        if today_str not in p.name:
            return p
    return None


def _parse_previous_results(report_path: Path) -> dict:
    """
    Naively extract per-ticker metrics from a previous report.
    Returns {ticker: {"oos_accuracy": float, "long_f1": float, "short_f1": float}}.
    """
    parsed = {}
    if report_path is None or not report_path.exists():
        return parsed
    try:
        lines = report_path.read_text().splitlines()
        for line in lines:
            # Match table rows: | BTCUSDT | 0.612 | 0.543 | 0.498 | OK |
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 4 and parts[0].isupper() and parts[0].endswith("USDT"):
                try:
                    ticker = parts[0]
                    parsed[ticker] = {
                        "oos_accuracy": float(parts[1]),
                        "long_f1": float(parts[2]),
                        "short_f1": float(parts[3]),
                    }
                except (ValueError, IndexError):
                    pass
    except OSError:
        pass
    return parsed


def save_markdown_report(
    results: dict,
    tickers: list,
    store: PerCoinModelStore,
    docs_dir: Path,
    global_metrics: dict | None = None,
) -> Path:
    """
    Save a Markdown training report to docs/TRAINING_V5_{YYYY-MM-DD}.md.
    Includes comparison with the previous run if one exists.
    """
    today = date.today().strftime("%Y-%m-%d")
    report_path = docs_dir / f"TRAINING_V5_{today}.md"
    docs_dir.mkdir(parents=True, exist_ok=True)

    summary = store.get_training_summary()
    trained_count = sum(1 for t in tickers if results.get(t) is not None)
    failed = [t for t in tickers if results.get(t) is None]

    valid_acc = [
        float(results[t]["oos_accuracy"])
        for t in tickers
        if results.get(t) and results[t].get("oos_accuracy") is not None
    ]
    avg_acc  = sum(valid_acc) / len(valid_acc) if valid_acc else 0.0
    avg_long  = summary.get("avg_long_f1", 0.0)
    avg_short = summary.get("avg_short_f1", 0.0)

    prev_report = _find_previous_report(docs_dir)
    prev_results = _parse_previous_results(prev_report)

    lines = [
        f"# CRYPTONITA V5 Training Report — {today}",
        "",
        "## Training Parameters",
        "",
        f"| Parameter         | Value |",
        f"|-------------------|-------|",
        f"| Date              | {today} |",
        f"| N Tickers         | {len(tickers)} |",
        f"| Trained OK        | {trained_count} |",
        f"| CV Splits         | 3 (PurgedWalkForwardCV) |",
        f"| Min Train Days    | 180 |",
        f"| Test Days         | 60 |",
        f"| Lookback Days     | 730 (2 years) |",
        f"| Min Samples       | 100 |",
        "",
        "## Per-Ticker Results",
        "",
        "| Ticker | OOS Acc | Long F1 | Short F1 | Status | Samples |",
        "|--------|---------|---------|----------|--------|---------|",
    ]

    for ticker in tickers:
        m = results.get(ticker)
        if m is None:
            lines.append(f"| {ticker} | N/A | N/A | N/A | FAILED | — |")
        else:
            n = m.get("n_samples", "—")
            lines.append(
                f"| {ticker} "
                f"| {_fmt(m.get('oos_accuracy')).strip()} "
                f"| {_fmt(m.get('long_f1')).strip()} "
                f"| {_fmt(m.get('short_f1')).strip()} "
                f"| OK "
                f"| {n} |"
            )

    lines += [
        "",
        "## Overall Statistics",
        "",
        f"| Metric            | Value |",
        f"|-------------------|-------|",
        f"| Avg OOS Accuracy  | {avg_acc:.4f} |",
        f"| Avg Long F1       | {avg_long:.4f} |",
        f"| Avg Short F1      | {avg_short:.4f} |",
        f"| Best LONG ticker  | {summary.get('best_long', 'N/A')} |",
        f"| Best SHORT ticker | {summary.get('best_short', 'N/A')} |",
        f"| Failed tickers    | {', '.join(failed) if failed else 'None'} |",
        "",
    ]

    # Global model section
    if global_metrics is not None:
        lines += [
            "## Global Model",
            "",
            f"| Metric        | Value |",
            f"|---------------|-------|",
            f"| OOS Accuracy  | {_fmt(global_metrics.get('oos_accuracy')).strip()} |",
            f"| Long F1       | {_fmt(global_metrics.get('long_f1')).strip()} |",
            f"| Short F1      | {_fmt(global_metrics.get('short_f1')).strip()} |",
            f"| N Tickers     | {global_metrics.get('n_tickers', '—')} |",
            f"| N Samples     | {global_metrics.get('n_samples', '—')} |",
            f"| Training time | {global_metrics.get('training_seconds', '—')}s |",
            "",
        ]

    # Comparison with previous run
    if prev_results and prev_report is not None:
        lines += [
            f"## Comparison vs Previous Run ({prev_report.stem})",
            "",
            "| Ticker | OOS Acc Delta | Long F1 Delta | Short F1 Delta |",
            "|--------|---------------|---------------|----------------|",
        ]
        for ticker in tickers:
            curr = results.get(ticker)
            prev = prev_results.get(ticker)
            if curr is None or prev is None:
                continue
            d_acc   = (curr.get("oos_accuracy") or 0) - prev["oos_accuracy"]
            d_long  = (curr.get("long_f1") or 0)      - prev["long_f1"]
            d_short = (curr.get("short_f1") or 0)     - prev["short_f1"]
            lines.append(
                f"| {ticker} "
                f"| {d_acc:+.4f} "
                f"| {d_long:+.4f} "
                f"| {d_short:+.4f} |"
            )
        lines.append("")
    else:
        lines += ["## Comparison vs Previous Run", "", "_No previous report found._", ""]

    report_path.write_text("\n".join(lines))
    return report_path


# ============================================================
# MAIN
# ============================================================

def main() -> int:
    args = parse_args()

    # Configure loguru: clean, colourful, no extra noise
    logger.remove()
    logger.add(
        lambda msg: print(msg, end=""),
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | <level>{message}</level>",
        level="INFO",
        colorize=True,
    )

    tickers: list = list(args.tickers or settings.TICKERS)

    store   = PerCoinModelStore()
    trainer = AutoTrainerV5(model_store=store)

    # ── DRY RUN ─────────────────────────────────────────────
    if args.dry_run:
        already_trained = store.list_trained_coins()
        print()
        print(f"DRY RUN — would train {len(tickers)} ticker(s):")
        print()
        for t in tickers:
            status = "(already trained)" if t in already_trained else "(new)"
            will_skip = args.resume and t in already_trained
            marker = "SKIP" if will_skip else "TRAIN"
            print(f"  [{marker}] {t} {status}")
        print()
        if args.global_model:
            print(f"  [TRAIN] global model on {len(settings.TICKERS)} tickers")
            print()
        return 0

    # ── RESUME FILTERING ────────────────────────────────────
    if args.resume:
        already_trained = store.list_trained_coins()
        today_str = time.strftime("%Y-%m-%d")
        skip = []
        keep = []
        for t in tickers:
            if t in already_trained:
                latest = store.get_latest_metrics(t)
                trained_at = (latest or {}).get("timestamp", "")
                if trained_at.startswith(today_str):
                    skip.append(t)
                    continue
            keep.append(t)
        if skip:
            logger.info(f"--resume: skipping {len(skip)} already-trained-today ticker(s): {', '.join(skip)}")
        tickers = keep
        if not tickers and not args.global_model:
            logger.success("All tickers already trained today. Nothing to do.")
            return 0

    # ── PER-COIN TRAINING ───────────────────────────────────
    results: dict = {}
    if tickers:
        logger.info(f"Starting V5 training for {len(tickers)} ticker(s)...")
        results = trainer.train_all_coins(tickers=tickers, resume=False)
    else:
        logger.info("No per-coin tickers to train (all skipped by --resume).")

    # ── GLOBAL MODEL ────────────────────────────────────────
    global_metrics = None
    if args.global_model:
        logger.info("Training global model...")
        global_metrics = trainer.train_global_model(tickers=list(settings.TICKERS))

    # ── SUMMARY TABLE ───────────────────────────────────────
    all_tickers = list(args.tickers or settings.TICKERS)
    # Fill skipped tickers from store so they appear in the table
    for t in all_tickers:
        if t not in results:
            results[t] = store.get_latest_metrics(t)

    print_summary_table(results, all_tickers)
    print_statistics(results, all_tickers, store)

    if global_metrics:
        print(
            f"Global model: "
            f"acc={_fmt(global_metrics.get('oos_accuracy')).strip()} "
            f"long_f1={_fmt(global_metrics.get('long_f1')).strip()} "
            f"short_f1={_fmt(global_metrics.get('short_f1')).strip()}"
        )
        print()

    # ── MARKDOWN REPORT ─────────────────────────────────────
    project_root = Path(__file__).parent.parent
    docs_dir     = project_root / "docs"
    report_path  = save_markdown_report(
        results=results,
        tickers=all_tickers,
        store=store,
        docs_dir=docs_dir,
        global_metrics=global_metrics,
    )
    print(f"Report saved to: {report_path}")
    print()

    # ── EXIT CODE ───────────────────────────────────────────
    trained_ok = sum(1 for t in all_tickers if results.get(t) is not None)
    return 0 if trained_ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
