from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import text

from app.db.base import Base


class ModelVersion(Base):
    __tablename__ = "model_versions"
    __table_args__ = (
        UniqueConstraint("model_name", "version_label", name="uq_model_versions_name_version"),
        CheckConstraint(
            "jsonb_typeof(parameters) = 'object'", name="ck_model_versions_parameters_object"
        ),
        CheckConstraint(
            "jsonb_typeof(feature_config) = 'object'",
            name="ck_model_versions_feature_config_object",
        ),
        CheckConstraint(
            "training_data_to IS NULL OR training_data_from IS NULL "
            "OR training_data_to >= training_data_from",
            name="ck_model_versions_training_dates",
        ),
        CheckConstraint(
            "status IN ('TRAINING', 'ACTIVE', 'INACTIVE', 'FAILED', 'ARCHIVED')",
            name="ck_model_versions_status",
        ),
    )

    model_version_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(100), nullable=False)
    version_label: Mapped[str] = mapped_column(String(40), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    feature_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    trained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    training_data_from: Mapped[date | None] = mapped_column(Date)
    training_data_to: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'INACTIVE'")
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.users.user_id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class ModelMetric(Base):
    __tablename__ = "model_metrics"
    __table_args__ = (
        UniqueConstraint(
            "model_version_id",
            "metric_name",
            "dataset_scope",
            name="uq_model_metrics_version_name_scope",
        ),
        CheckConstraint(
            "dataset_scope IN ('TRAIN', 'VALIDATION', 'TEST', 'PRODUCTION')",
            name="ck_model_metrics_scope",
        ),
    )

    metric_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    model_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("restaurant_ai.model_versions.model_version_id", ondelete="CASCADE"),
        nullable=False,
    )
    metric_name: Mapped[str] = mapped_column(String(40), nullable=False)
    metric_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    dataset_scope: Mapped[str] = mapped_column(String(20), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class ForecastRun(Base):
    __tablename__ = "forecast_runs"
    __table_args__ = (
        CheckConstraint("forecast_end_date >= forecast_start_date", name="ck_forecast_runs_dates"),
        CheckConstraint("horizon_days > 0", name="ck_forecast_runs_horizon"),
        CheckConstraint("trigger_type IN ('MANUAL', 'SCHEDULED')", name="ck_forecast_runs_trigger"),
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')",
            name="ck_forecast_runs_status",
        ),
        CheckConstraint(
            "status <> 'FAILED' OR error_message IS NOT NULL", name="ck_forecast_runs_error"
        ),
    )

    forecast_run_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    model_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("restaurant_ai.model_versions.model_version_id", ondelete="RESTRICT"),
        nullable=False,
    )
    forecast_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'PENDING'")
    )
    generated_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.users.user_id", ondelete="SET NULL")
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    error_message: Mapped[str | None] = mapped_column(Text)


class ForecastResult(Base):
    __tablename__ = "forecast_results"
    __table_args__ = (
        UniqueConstraint(
            "forecast_run_id", "dish_id", "forecast_date", name="uq_forecast_results_run_dish_date"
        ),
        CheckConstraint("predicted_qty >= 0", name="ck_forecast_results_predicted"),
        CheckConstraint(
            "lower_bound IS NULL OR lower_bound >= 0", name="ck_forecast_results_lower"
        ),
        CheckConstraint(
            "upper_bound IS NULL OR upper_bound >= predicted_qty", name="ck_forecast_results_upper"
        ),
        CheckConstraint(
            "lower_bound IS NULL OR lower_bound <= predicted_qty", name="ck_forecast_results_bounds"
        ),
        CheckConstraint("actual_qty IS NULL OR actual_qty >= 0", name="ck_forecast_results_actual"),
    )

    forecast_result_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    forecast_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("restaurant_ai.forecast_runs.forecast_run_id", ondelete="CASCADE"),
        nullable=False,
    )
    dish_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.dishes.dish_id", ondelete="RESTRICT"), nullable=False
    )
    forecast_date: Mapped[date] = mapped_column(Date, nullable=False)
    predicted_qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    lower_bound: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    upper_bound: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    actual_qty: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))


class ReplenishmentProposal(Base):
    __tablename__ = "replenishment_proposals"
    __table_args__ = (
        CheckConstraint(
            "planning_end_date >= planning_start_date", name="ck_replenishment_proposals_dates"
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'PENDING_REVIEW', 'APPROVED', 'REJECTED', 'ORDERED')",
            name="ck_replenishment_proposals_status",
        ),
        CheckConstraint(
            "status NOT IN ('APPROVED', 'REJECTED') "
            "OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="ck_replenishment_proposals_review",
        ),
    )

    proposal_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    proposal_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    forecast_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("restaurant_ai.forecast_runs.forecast_run_id", ondelete="RESTRICT"),
        nullable=False,
    )
    planning_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    planning_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'DRAFT'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    reviewed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.users.user_id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)


class ReplenishmentProposalItem(Base):
    __tablename__ = "replenishment_proposal_items"
    __table_args__ = (
        UniqueConstraint(
            "proposal_id", "ingredient_id", name="uq_replenishment_items_proposal_ingredient"
        ),
        CheckConstraint("forecast_demand_qty >= 0", name="ck_replenishment_items_demand"),
        CheckConstraint("available_stock_qty >= 0", name="ck_replenishment_items_available"),
        CheckConstraint("incoming_qty >= 0", name="ck_replenishment_items_incoming"),
        CheckConstraint("safety_stock_qty >= 0", name="ck_replenishment_items_safety"),
        CheckConstraint("lead_time_days_snapshot >= 0", name="ck_replenishment_items_lead_time"),
        CheckConstraint("suggested_qty >= 0", name="ck_replenishment_items_suggested"),
        CheckConstraint(
            "adjusted_qty IS NULL OR adjusted_qty >= 0", name="ck_replenishment_items_adjusted"
        ),
        CheckConstraint(
            "adjusted_qty IS NULL OR adjustment_reason IS NOT NULL",
            name="ck_replenishment_items_adjustment_reason",
        ),
    )

    proposal_item_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    proposal_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("restaurant_ai.replenishment_proposals.proposal_id", ondelete="CASCADE"),
        nullable=False,
    )
    ingredient_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("restaurant_ai.ingredients.ingredient_id", ondelete="RESTRICT"),
        nullable=False,
    )
    forecast_demand_qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    available_stock_qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    incoming_qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    safety_stock_qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    lead_time_days_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    suggested_qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    adjusted_qty: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    final_qty: Mapped[Decimal] = mapped_column(
        Numeric(14, 3), Computed("COALESCE(adjusted_qty, suggested_qty)", persisted=True)
    )
    preferred_supplier_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("restaurant_ai.suppliers.supplier_id", ondelete="SET NULL")
    )
    adjustment_reason: Mapped[str | None] = mapped_column(Text)
