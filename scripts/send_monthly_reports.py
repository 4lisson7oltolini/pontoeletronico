"""Run the idempotent monthly-report delivery check."""

import logging

from database.connection import session_scope
from services.monthly_report_delivery_service import dispatch_monthly_reports

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    with session_scope() as session:
        result = dispatch_monthly_reports(session)
    logger.info(
        "Relatórios mensais: novos=%s enviados=%s aguardando marcação final=%s",
        result.queued,
        result.sent,
        result.deferred,
    )


if __name__ == "__main__":
    main()
