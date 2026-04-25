"""Run the pipeline once for a single source (debug / ops helper).

Usage:
    python -m scripts.run_pipeline_once --tenant-id <uuid> --source-id <uuid>
"""
import argparse
from uuid import UUID

from app.db.session import SessionLocal
from app.services.pipeline_service import PipelineService


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--source-id", required=True)
    args = parser.parse_args()

    tenant_id = UUID(args.tenant_id)
    source_id = UUID(args.source_id)

    with SessionLocal() as db:
        summary = PipelineService(db, tenant_id).run_for_source(source_id)
        print(
            f"PipelineRun {summary.run_id}: status={summary.status.value} "
            f"collected={summary.collected_item_count} "
            f"signals={summary.inserted_signal_count} "
            f"failed_items={summary.failed_item_count}"
        )


if __name__ == "__main__":
    main()
