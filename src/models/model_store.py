"""
MODEL STORE
=============
Save/load ML model artifacts to/from PostgreSQL.
Survives Render ephemeral filesystem restarts.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timezone
from loguru import logger

from config import settings
from src.data.storage.db_manager import DatabaseManager

# Map of files produced by EnsembleModel.save() + RegimeDetector.save()
ARTIFACT_FILES = {
    "base_xgboost.pkl": "base_xgboost",
    "base_lightgbm.pkl": "base_lightgbm",
    "base_catboost.pkl": "base_catboost",
    "meta_learner.pkl": "meta_learner",
    "regime_detector.pkl": "regime_detector",
    "ensemble_metadata.json": "ensemble_metadata",
    "feature_names.json": "feature_names",
    "training_metrics.json": "training_metrics",
    "best_params.json": "best_params",
}


class ModelStore:
    """Persist V4 ensemble model artifacts in PostgreSQL."""

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager(settings.get_database_url())

    def save_ensemble(self, version: int, model_dir: str, metrics: Optional[Dict] = None) -> bool:
        """
        Read all model files from model_dir, serialize to BYTEA, INSERT into model_artifacts.

        Args:
            version: Model version number
            model_dir: Directory containing .pkl/.json model files
            metrics: Optional training metrics dict
        """
        model_path = Path(model_dir)
        if not model_path.exists():
            logger.error(f"Model directory not found: {model_dir}")
            return False

        saved_count = 0
        for filename, model_type in ARTIFACT_FILES.items():
            filepath = model_path / filename
            if not filepath.exists():
                logger.debug(f"Skipping missing file: {filename}")
                continue

            with open(filepath, "rb") as f:
                data = f.read()

            metadata = {"filename": filename, "size_bytes": len(data)}

            self.db.execute_command(
                """
                INSERT INTO model_artifacts (version, model_type, artifact_data, metadata, training_metrics, is_active)
                VALUES (:version, :model_type, :artifact_data, :metadata, :training_metrics, FALSE)
                """,
                {
                    "version": version,
                    "model_type": model_type,
                    "artifact_data": data,
                    "metadata": json.dumps(metadata),
                    "training_metrics": json.dumps(metrics or {}),
                },
            )
            saved_count += 1

        logger.info(f"Saved {saved_count} artifacts for version {version} to DB")
        return saved_count > 0

    def load_active_ensemble(self, target_dir: str) -> Optional[int]:
        """
        Load the active model version from DB, write files to target_dir.

        Returns:
            Active version number, or None if no active model found
        """
        rows = self.db.execute_query(
            "SELECT version, model_type, artifact_data, metadata FROM model_artifacts WHERE is_active = TRUE"
        )

        if len(rows) == 0:
            logger.warning("No active model found in DB")
            return None

        target_path = Path(target_dir)
        target_path.mkdir(parents=True, exist_ok=True)

        version = int(rows.iloc[0]["version"])

        for _, row in rows.iterrows():
            model_type = row["model_type"]
            data = row["artifact_data"]

            # Parse metadata to get original filename
            meta = row["metadata"]
            if isinstance(meta, str):
                meta = json.loads(meta)
            filename = meta.get("filename", f"{model_type}.pkl")

            filepath = target_path / filename
            # artifact_data comes as memoryview from psycopg2
            raw = bytes(data) if data is not None else b""
            with open(filepath, "wb") as f:
                f.write(raw)

        logger.info(f"Loaded active model v{version} ({len(rows)} artifacts) to {target_dir}")
        return version

    def promote_version(self, version: int):
        """Set the given version as active (deactivate all others)."""
        self.db.execute_command(
            "UPDATE model_artifacts SET is_active = FALSE WHERE is_active = TRUE"
        )
        self.db.execute_command(
            "UPDATE model_artifacts SET is_active = TRUE WHERE version = :version",
            {"version": version},
        )
        logger.info(f"Promoted model version {version} to active")

    def get_latest_version(self) -> int:
        """Get the highest version number in DB, or 0 if none."""
        result = self.db.execute_query(
            "SELECT COALESCE(MAX(version), 0) as max_version FROM model_artifacts"
        )
        return int(result.iloc[0]["max_version"])

    def has_active_model(self) -> bool:
        """Check if there's an active model in DB."""
        result = self.db.execute_query(
            "SELECT COUNT(*) as cnt FROM model_artifacts WHERE is_active = TRUE"
        )
        return int(result.iloc[0]["cnt"]) > 0

    def get_active_metrics(self) -> Dict:
        """Get training metrics for the active model version."""
        result = self.db.execute_query(
            """
            SELECT training_metrics FROM model_artifacts
            WHERE is_active = TRUE AND model_type = 'training_metrics'
            LIMIT 1
            """
        )
        if len(result) == 0:
            return {}

        metrics = result.iloc[0]["training_metrics"]
        if isinstance(metrics, str):
            return json.loads(metrics)
        return metrics if isinstance(metrics, dict) else {}

    # ============================================
    # Training Runs
    # ============================================

    def save_training_run(
        self,
        version: int,
        status: str = "running",
        mode: str = "quick",
        metrics: Optional[Dict] = None,
        comparison: Optional[Dict] = None,
        error_message: Optional[str] = None,
        promoted: bool = False,
    ) -> int:
        """Insert a training run record. Returns the run id."""
        result = self.db.execute_query(
            """
            INSERT INTO training_runs (version, status, mode, metrics, comparison, error_message, promoted)
            VALUES (:version, :status, :mode, :metrics, :comparison, :error_message, :promoted)
            RETURNING id
            """,
            {
                "version": version,
                "status": status,
                "mode": mode,
                "metrics": json.dumps(metrics or {}),
                "comparison": json.dumps(comparison or {}),
                "error_message": error_message,
                "promoted": promoted,
            },
        )
        # execute_query returns a DataFrame; for INSERT RETURNING we need execute_command approach
        # Fall back to a simpler approach
        return int(result.iloc[0]["id"]) if len(result) > 0 else 0

    def update_training_run(
        self,
        version: int,
        status: str,
        metrics: Optional[Dict] = None,
        comparison: Optional[Dict] = None,
        error_message: Optional[str] = None,
        promoted: bool = False,
    ):
        """Update the latest training run for a version."""
        self.db.execute_command(
            """
            UPDATE training_runs
            SET status = :status,
                completed_at = NOW(),
                metrics = :metrics,
                comparison = :comparison,
                error_message = :error_message,
                promoted = :promoted
            WHERE version = :version AND id = (
                SELECT MAX(id) FROM training_runs WHERE version = :version
            )
            """,
            {
                "version": version,
                "status": status,
                "metrics": json.dumps(metrics or {}),
                "comparison": json.dumps(comparison or {}),
                "error_message": error_message,
                "promoted": promoted,
            },
        )

    def get_training_history(self, limit: int = 10) -> List[Dict]:
        """Get recent training runs."""
        result = self.db.execute_query(
            """
            SELECT id, version, status, mode, started_at, completed_at,
                   metrics, comparison, error_message, promoted
            FROM training_runs
            ORDER BY id DESC
            LIMIT :limit
            """,
            {"limit": limit},
        )
        rows = []
        for _, row in result.iterrows():
            entry = row.to_dict()
            # Parse JSON fields
            for field in ("metrics", "comparison"):
                if isinstance(entry[field], str):
                    try:
                        entry[field] = json.loads(entry[field])
                    except (json.JSONDecodeError, TypeError):
                        entry[field] = {}
            # Convert timestamps to ISO strings
            for ts_field in ("started_at", "completed_at"):
                if entry[ts_field] is not None and hasattr(entry[ts_field], "isoformat"):
                    entry[ts_field] = entry[ts_field].isoformat()
            rows.append(entry)
        return rows
