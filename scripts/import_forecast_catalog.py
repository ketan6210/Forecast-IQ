"""Import trusted local batch checkpoints into the application database and artifact store."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import settings  # noqa: E402
from backend.app.db.session import build_session_factory  # noqa: E402
from backend.app.errors import AppError  # noqa: E402
from backend.app.services.catalog_import import import_catalog  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, required=True, help="Trusted local catalog directory"
    )
    parser.add_argument("--dataset-id", required=True, help="Existing uploaded application dataset")
    parser.add_argument("--storage-dir", type=Path, default=settings.storage_dir)
    parser.add_argument("--database-url", default=settings.database_url)
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate without writing runs or artifacts"
    )
    args = parser.parse_args()
    factory = build_session_factory(args.database_url)
    try:
        with factory() as session:
            summary = import_catalog(
                session, args.storage_dir, args.source, args.dataset_id, dry_run=args.dry_run
            )
        print(json.dumps(summary, indent=2))
    except AppError as exc:
        parser.exit(1, f"{exc.message}\n")
    finally:
        factory.kw["bind"].dispose()


if __name__ == "__main__":
    main()
