"""Application-AI cost attribution and request-time budget guardrails.

The price catalog is deliberately local and versioned for this portfolio demo.
Production would sync provider-specific prices and receive usage through an SDK
or gateway, rather than trust a browser client to report usage.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.domain import Repository, utc_now


@dataclass(frozen=True)
class ModelPrice:
    provider: str
    model: str
    input_per_million: float
    output_per_million: float
    cached_input_per_million: float


CATALOG: dict[tuple[str, str], ModelPrice] = {
    ("openai", "gpt-4o-mini"): ModelPrice("openai", "gpt-4o-mini", 0.15, 0.60, 0.075),
    ("openai", "gpt-4o"): ModelPrice("openai", "gpt-4o", 2.50, 10.00, 1.25),
    ("anthropic", "claude-haiku"): ModelPrice("anthropic", "claude-haiku", 0.80, 4.00, 0.08),
    ("anthropic", "claude-sonnet"): ModelPrice("anthropic", "claude-sonnet", 3.00, 15.00, 0.30),
}


@dataclass(frozen=True)
class AIUsageInput:
    tenant_id: str
    app: str
    customer: str
    end_user: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0
    compute_cost: float = 0
    data_cost: float = 0
    request_id: str | None = None


class AICostService:
    """Owns deterministic pricing, attribution, and the application budget policy."""

    def __init__(self, repository: Repository) -> None:
        self.repository = repository
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self.repository.transaction() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS ai_budgets (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    app TEXT NOT NULL,
                    monthly_limit REAL NOT NULL,
                    warning_percent INTEGER NOT NULL DEFAULT 80,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(tenant_id, app)
                );
                CREATE TABLE IF NOT EXISTS ai_usage_events (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    app TEXT NOT NULL,
                    customer_name TEXT NOT NULL,
                    end_user TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    input_tokens INTEGER NOT NULL,
                    output_tokens INTEGER NOT NULL,
                    cached_input_tokens INTEGER NOT NULL,
                    inference_cost REAL NOT NULL,
                    compute_cost REAL NOT NULL,
                    data_cost REAL NOT NULL,
                    total_cost REAL NOT NULL,
                    request_id TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(tenant_id, request_id)
                );
                """
            )

    @staticmethod
    def _price_for(provider: str, model: str) -> ModelPrice:
        try:
            return CATALOG[(provider.lower(), model.lower())]
        except KeyError as error:
            supported = ", ".join(f"{item.provider}/{item.model}" for item in CATALOG.values())
            raise ValueError(f"Unknown model price. Supported demo models: {supported}.") from error

    def estimate(self, usage: AIUsageInput) -> dict[str, float]:
        price = self._price_for(usage.provider, usage.model)
        standard_input = max(usage.input_tokens - usage.cached_input_tokens, 0)
        inference_cost = (
            standard_input * price.input_per_million
            + usage.cached_input_tokens * price.cached_input_per_million
            + usage.output_tokens * price.output_per_million
        ) / 1_000_000
        total = inference_cost + usage.compute_cost + usage.data_cost
        return {
            "inference_cost": round(inference_cost, 6),
            "compute_cost": round(usage.compute_cost, 6),
            "data_cost": round(usage.data_cost, 6),
            "total_cost": round(total, 6),
        }

    def set_budget(self, tenant_id: str, app: str, monthly_limit: float, warning_percent: int = 80) -> dict[str, object]:
        now = utc_now()
        with self.repository.transaction() as conn:
            conn.execute(
                """INSERT INTO ai_budgets (id, tenant_id, app, monthly_limit, warning_percent, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(tenant_id, app) DO UPDATE SET monthly_limit = excluded.monthly_limit,
                   warning_percent = excluded.warning_percent, updated_at = excluded.updated_at""",
                (str(uuid.uuid4()), tenant_id, app, monthly_limit, warning_percent, now, now),
            )
        return self.get_budget(tenant_id, app) or {}

    def get_budget(self, tenant_id: str, app: str) -> dict[str, object] | None:
        row = self.repository._connection.execute(  # noqa: SLF001 - repository owns the local SQLite connection.
            "SELECT * FROM ai_budgets WHERE tenant_id = ? AND app = ?", (tenant_id, app)
        ).fetchone()
        return dict(row) if row else None

    def _month_spend(self, tenant_id: str, app: str) -> float:
        row = self.repository._connection.execute(  # noqa: SLF001
            """SELECT COALESCE(SUM(total_cost), 0) AS total FROM ai_usage_events
               WHERE tenant_id = ? AND app = ? AND date(created_at) >= date('now', 'start of month')""",
            (tenant_id, app),
        ).fetchone()
        return float(row["total"])

    def preflight(self, usage: AIUsageInput) -> dict[str, object]:
        estimate = self.estimate(usage)
        spent = self._month_spend(usage.tenant_id, usage.app)
        projected = round(spent + estimate["total_cost"], 6)
        budget = self.get_budget(usage.tenant_id, usage.app)
        if not budget:
            return {
                "decision": "WARN", "permitted": True, "reason": "No app budget is configured; request is allowed and flagged.",
                "estimate": estimate, "month_to_date_spend": spent, "projected_month_spend": projected, "budget": None,
            }
        limit = float(budget["monthly_limit"])
        warning_threshold = limit * (int(budget["warning_percent"]) / 100)
        if projected > limit:
            decision, permitted = "BLOCK", False
            reason = f"Projected app spend ${projected:,.2f} exceeds the ${limit:,.2f} monthly guardrail."
        elif projected >= warning_threshold:
            decision, permitted = "WARN", True
            reason = f"Projected app spend ${projected:,.2f} crosses the {budget['warning_percent']}% budget warning."
        else:
            decision, permitted = "ALLOW", True
            reason = "Projected spend remains within the app guardrail."
        return {
            "decision": decision, "permitted": permitted, "reason": reason, "estimate": estimate,
            "month_to_date_spend": round(spent, 6), "projected_month_spend": projected, "budget": budget,
        }

    def record_usage(self, usage: AIUsageInput) -> dict[str, object]:
        estimate = self.estimate(usage)
        event_id = str(uuid.uuid4())
        with self.repository.transaction() as conn:
            conn.execute(
                """INSERT INTO ai_usage_events (
                    id, tenant_id, app, customer_name, end_user, provider, model, input_tokens,
                    output_tokens, cached_input_tokens, inference_cost, compute_cost, data_cost,
                    total_cost, request_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (event_id, usage.tenant_id, usage.app, usage.customer, usage.end_user, usage.provider,
                 usage.model, usage.input_tokens, usage.output_tokens, usage.cached_input_tokens,
                 estimate["inference_cost"], estimate["compute_cost"], estimate["data_cost"],
                 estimate["total_cost"], usage.request_id, utc_now()),
            )
        return self.get_usage_event(event_id) or {}

    def get_usage_event(self, event_id: str) -> dict[str, object] | None:
        row = self.repository._connection.execute("SELECT * FROM ai_usage_events WHERE id = ?", (event_id,)).fetchone()  # noqa: SLF001
        return dict(row) if row else None

    def list_usage(self, tenant_id: str) -> list[dict[str, object]]:
        rows = self.repository._connection.execute(  # noqa: SLF001
            "SELECT * FROM ai_usage_events WHERE tenant_id = ? ORDER BY created_at DESC", (tenant_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def overview(self, tenant_id: str) -> dict[str, object]:
        rows = self.list_usage(tenant_id)
        total = round(sum(float(row["total_cost"]) for row in rows), 4)
        inference = round(sum(float(row["inference_cost"]) for row in rows), 4)
        compute = round(sum(float(row["compute_cost"]) for row in rows), 4)
        data = round(sum(float(row["data_cost"]) for row in rows), 4)
        by_app: dict[str, float] = {}
        by_model: dict[str, float] = {}
        by_customer: dict[str, float] = {}
        for row in rows:
            cost = float(row["total_cost"])
            by_app[str(row["app"])] = by_app.get(str(row["app"]), 0) + cost
            model = f"{row['provider']} / {row['model']}"
            by_model[model] = by_model.get(model, 0) + cost
            by_customer[str(row["customer_name"])] = by_customer.get(str(row["customer_name"]), 0) + cost
        budget_rows = self.repository._connection.execute(  # noqa: SLF001
            "SELECT * FROM ai_budgets WHERE tenant_id = ? ORDER BY app", (tenant_id,)
        ).fetchall()
        budgets = []
        for item in budget_rows:
            budget = dict(item)
            spend = self._month_spend(tenant_id, str(budget["app"]))
            budget["month_to_date_spend"] = round(spend, 4)
            budget["percent_used"] = round((spend / float(budget["monthly_limit"])) * 100, 1) if budget["monthly_limit"] else 0
            budgets.append(budget)
        return {
            "total_cost": total, "inference_cost": inference, "compute_cost": compute, "data_cost": data,
            "request_count": len(rows),
            "by_app": self._rank(by_app), "by_model": self._rank(by_model), "by_customer": self._rank(by_customer),
            "budgets": budgets,
        }

    @staticmethod
    def _rank(values: dict[str, float]) -> list[dict[str, object]]:
        return [{"name": name, "cost": round(cost, 4)} for name, cost in sorted(values.items(), key=lambda item: item[1], reverse=True)]

    def delete_tenant_data(self, tenant_id: str) -> None:
        with self.repository.transaction() as conn:
            conn.execute("DELETE FROM ai_usage_events WHERE tenant_id = ?", (tenant_id,))
            conn.execute("DELETE FROM ai_budgets WHERE tenant_id = ?", (tenant_id,))
