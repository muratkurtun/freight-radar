from app.collectors.base import BaseCollector
from app.collectors.company_website_collector import CompanyWebsiteCollector
from app.collectors.job_board_collector import JobBoardCollector
from app.collectors.news_collector import NewsCollector
from app.core.errors import AppError
from app.domain.enums import SourceType

_REGISTRY: dict[str, type[BaseCollector]] = {
    SourceType.NEWS.value: NewsCollector,
    SourceType.JOB_BOARD.value: JobBoardCollector,
    SourceType.COMPANY_WEBSITE.value: CompanyWebsiteCollector,
}


def get_collector(source_type: str) -> BaseCollector:
    cls = _REGISTRY.get(source_type)
    if cls is None:
        raise AppError(f"No collector registered for source_type={source_type}")
    return cls()
