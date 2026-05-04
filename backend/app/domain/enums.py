from enum import StrEnum


class SourceType(StrEnum):
    NEWS = "news"
    JOB_BOARD = "job_board"
    COMPANY_WEBSITE = "company_website"


class SignalType(StrEnum):
    """Logistics sales lead categories.

    Migration 0005 replaced the pre-pivot trio
    (warehouse_opening / supplier_change / hiring_supply_chain_role) with
    these thirteen logistics-lead categories. Legacy rows still carry the
    old strings; the SignalType enum is the *write* authority — the read
    path tolerates unknown values and surfaces them as-is so historical
    data stays visible.
    """

    EXPORT_EXPANSION = "export_expansion"
    IMPORT_NEED = "import_need"
    NEW_FACTORY = "new_factory"
    NEW_WAREHOUSE = "new_warehouse"
    CAPACITY_INCREASE = "capacity_increase"
    NEW_MARKET_ENTRY = "new_market_entry"
    DISTRIBUTORSHIP = "distributorship"
    ECOMMERCE_GROWTH = "ecommerce_growth"
    HIRING_LOGISTICS_ROLE = "hiring_logistics_role"
    HIRING_EXPORT_ROLE = "hiring_export_role"
    INVESTMENT_INCENTIVE = "investment_incentive"
    SUPPLY_CHAIN_PROBLEM = "supply_chain_problem"
    TENDER_OR_CONTRACT = "tender_or_contract"


class UrgencyLevel(StrEnum):
    """How time-sensitive the lead is. Drives sales triage ordering.
    Stored as text in `detected_signals.urgency` so legacy rows (NULL)
    keep working."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FeedbackAction(StrEnum):
    """Sales-team feedback lifecycle actions on a detected signal.

    Distinct from `ReviewAction` (admin approve/reject) — feedback is a
    sales-side, append-only history. The first six are positive /
    lifecycle actions; the last three are corrective negatives that
    overlap with `FeedbackReason` so the UI can surface a granular
    reason directly as an action when that's clearer for the user.
    """

    RELEVANT = "relevant"
    NOT_RELEVANT = "not_relevant"
    QUALIFIED = "qualified"
    CONTACTED = "contacted"
    CONVERTED = "converted"
    DISMISSED = "dismissed"
    WRONG_COMPANY = "wrong_company"
    WRONG_SECTOR = "wrong_sector"
    NOT_A_LOGISTICS_LEAD = "not_a_logistics_lead"


class FeedbackReason(StrEnum):
    """Structured 'why' attached to a negative / corrective feedback.

    Optional in general — the UI only requires it for negative actions
    (NOT_RELEVANT, DISMISSED, WRONG_*, NOT_A_LOGISTICS_LEAD)."""

    WRONG_COMPANY = "wrong_company"
    WRONG_SECTOR = "wrong_sector"
    NOT_A_LOGISTICS_LEAD = "not_a_logistics_lead"
    DUPLICATE = "duplicate"
    LOW_CONFIDENCE = "low_confidence"


# Actions that require a structured reason at the API layer. Must stay
# in sync with the frontend's REASON_REQUIRED_ACTIONS set.
NEGATIVE_FEEDBACK_ACTIONS: frozenset[FeedbackAction] = frozenset(
    {
        FeedbackAction.NOT_RELEVANT,
        FeedbackAction.DISMISSED,
        FeedbackAction.WRONG_COMPANY,
        FeedbackAction.WRONG_SECTOR,
        FeedbackAction.NOT_A_LOGISTICS_LEAD,
    }
)


class RecommendedService(StrEnum):
    """Controlled vocabulary for `detected_signals.recommended_services`.
    The LLM is constrained to this set; out-of-vocabulary values are
    dropped during normalization (no hallucinated services)."""

    ROAD_FREIGHT = "road_freight"
    SEA_FREIGHT = "sea_freight"
    AIR_FREIGHT = "air_freight"
    RAIL_FREIGHT = "rail_freight"
    INTERMODAL = "intermodal"
    CUSTOMS_BROKERAGE = "customs_brokerage"
    WAREHOUSING = "warehousing"
    FULFILLMENT = "fulfillment"
    LAST_MILE = "last_mile"
    PROJECT_CARGO = "project_cargo"
    DANGEROUS_GOODS = "dangerous_goods"
    COLD_CHAIN = "cold_chain"


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
