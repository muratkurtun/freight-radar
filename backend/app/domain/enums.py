from enum import StrEnum


class SourceType(StrEnum):
    NEWS = "news"
    JOB_BOARD = "job_board"
    COMPANY_WEBSITE = "company_website"


class SignalType(StrEnum):
    WAREHOUSE_OPENING = "warehouse_opening"
    SUPPLIER_CHANGE = "supplier_change"
    HIRING_SUPPLY_CHAIN_ROLE = "hiring_supply_chain_role"


class ReviewStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class PipelineRunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class UserRole(StrEnum):
    PLATFORM_ADMIN = "platform_admin"
    TENANT_ADMIN = "tenant_admin"
    TENANT_USER = "tenant_user"


class SubscriptionStatus(StrEnum):
    """Effective subscription state.

    DB stores only TRIAL / ACTIVE (see ck_tenants_subscription_status).
    EXPIRED is a derived/reported value — a row with status='trial' and
    trial_ends_at in the past effectively becomes EXPIRED at read time."""

    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRED = "expired"
