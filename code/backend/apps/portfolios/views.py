"""
QuantYield — Portfolio API Views
Portfolio CRUD, position management, analytics, scenarios, VaR/CVaR, P&L,
duration buckets.
"""

import asyncio
import logging
import math
from datetime import date

from apps.bonds.serializers import _bond_to_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from services import pricing as ps
from services import risk as rs
from services.data_feed import (
    compute_rolling_volatility,
    compute_yield_changes,
    fetch_yield_history,
)
from services.schemas import ScenarioShiftSchema

from .models import Portfolio, Position
from .serializers import (
    PortfolioCreateSerializer,
    PortfolioSerializer,
    PositionCreateSerializer,
    PositionSerializer,
    ScenarioShiftSerializer,
    VaRRequestSerializer,
)

logger = logging.getLogger("quantyield")


def _resolve_portfolio_bonds(portfolio, settle):
    """Build lists of bond schemas, ytms, face amounts, purchase prices/dates."""
    bonds_out, ytms_out, faces_out, pp_out, pd_out = [], [], [], [], []
    for pos in portfolio.positions.select_related("bond").prefetch_related(
        "bond__call_schedule"
    ):
        bond = pos.bond
        bond_schema = _bond_to_schema(bond)
        ytm = ps.ytm_from_clean_price(bond_schema, float(bond.face_value), settle)
        if math.isnan(ytm):
            ytm = float(bond.coupon_rate)
        bonds_out.append(bond_schema)
        ytms_out.append(ytm)
        faces_out.append(float(pos.face_amount))
        pp_out.append(float(pos.purchase_price) if pos.purchase_price else None)
        pd_out.append(pos.purchase_date)
    return bonds_out, ytms_out, faces_out, pp_out, pd_out


class PortfolioViewSet(viewsets.ModelViewSet):
    """
    CRUD + full analytics for bond portfolios.
    """

    queryset = Portfolio.objects.prefetch_related(
        "positions", "positions__bond", "positions__bond__call_schedule"
    ).all()

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return PortfolioCreateSerializer
        return PortfolioSerializer

    search_fields = ["name", "description", "currency"]
    ordering_fields = ["name", "currency", "created_at"]
    ordering = ["-created_at"]

    def create(self, request, *args, **kwargs):
        ser = PortfolioCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        portfolio = ser.save()
        out = PortfolioSerializer(portfolio)
        return Response(out.data, status=status.HTTP_201_CREATED)

    # ── Position Management ────────────────────────────────────────────────────

    @action(detail=True, methods=["post"], url_path="positions")
    def add_position(self, request, pk=None):
        """Add or update a position in the portfolio."""
        portfolio = self.get_object()
        ser = PositionCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        bond = data["bond"]
        pos, created = Position.objects.update_or_create(
            portfolio=portfolio,
            bond=bond,
            defaults={
                "face_amount": data["face_amount"],
                "purchase_price": data.get("purchase_price"),
                "purchase_date": data.get("purchase_date"),
                "notes": data.get("notes"),
            },
        )
        out = PositionSerializer(pos)
        return Response(
            out.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=True, methods=["delete"], url_path="positions/(?P<bond_id>[^/.]+)")
    def remove_position(self, request, pk=None, bond_id=None):
        """Remove a bond position from the portfolio."""
        portfolio = self.get_object()
        deleted, _ = Position.objects.filter(
            portfolio=portfolio, bond_id=bond_id
        ).delete()
        if not deleted:
            raise ValidationError("Position not found")
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ── Analytics ──────────────────────────────────────────────────────────────

    @action(detail=True, methods=["get"], url_path="analytics")
    def analytics(self, request, pk=None):
        """Full portfolio risk metrics: duration, convexity, DV01, KRD, allocations."""
        portfolio = self.get_object()
        settle_str = request.query_params.get("settlement")
        settle = date.fromisoformat(settle_str) if settle_str else date.today()

        bonds, ytms, faces, _, _ = _resolve_portfolio_bonds(portfolio, settle)
        if not bonds:
            raise ValidationError("Portfolio has no valid bonds")

        metrics = rs.portfolio_risk_metrics(bonds, ytms, faces, settle)
        mv_list = metrics.get("market_values", [])
        total_mv = metrics["total_market_value"]

        # Aggregate KRD
        krd_agg: dict = {}
        for bond_s, ytm, mv in zip(bonds, ytms, mv_list):
            weight = mv / total_mv
            krd = ps.key_rate_durations(bond_s, ytm, settle)
            for tenor, dur in krd.items():
                krd_agg[str(tenor)] = krd_agg.get(str(tenor), 0.0) + dur * weight

        # Sector / rating / maturity allocations
        # Use the already-resolved bonds list (same order as mv_list) to avoid
        # a second DB round-trip on every bond and prevent ordering mismatches
        # that would cause mv_list[mv_idx] to pick the wrong market value.
        sector_alloc: dict = {}
        rating_alloc: dict = {}
        maturity_dist: dict = {}

        for bond_schema, mv in zip(bonds, mv_list):
            w = mv / total_mv if total_mv else 0.0

            sector = bond_schema.sector or "Unknown"
            rating = bond_schema.credit_rating or "NR"
            sector_alloc[sector] = sector_alloc.get(sector, 0.0) + w
            rating_alloc[rating] = rating_alloc.get(rating, 0.0) + w

            yrs = (bond_schema.maturity_date - settle).days / 365.0
            bucket = (
                "0-1Y"
                if yrs <= 1
                else (
                    "1-3Y"
                    if yrs <= 3
                    else "3-5Y" if yrs <= 5 else "5-10Y" if yrs <= 10 else "10Y+"
                )
            )
            maturity_dist[bucket] = maturity_dist.get(bucket, 0.0) + w

        return Response(
            {
                "portfolio_id": str(portfolio.id),
                "portfolio_name": portfolio.name,
                "settlement_date": settle.isoformat(),
                "total_market_value": round(total_mv, 4),
                "total_face_value": round(sum(faces), 4),
                "portfolio_duration": round(metrics["portfolio_duration"], 6),
                "portfolio_modified_duration": round(
                    metrics["portfolio_modified_duration"], 6
                ),
                "portfolio_convexity": round(metrics["portfolio_convexity"], 6),
                "portfolio_ytm": round(metrics["portfolio_ytm"], 6),
                "portfolio_ytm_pct": round(metrics["portfolio_ytm"] * 100, 4),
                "portfolio_dv01": round(metrics["portfolio_dv01"], 4),
                "portfolio_spread_duration": round(
                    metrics.get("portfolio_spread_duration", 0), 6
                ),
                "key_rate_durations": {k: round(v, 6) for k, v in krd_agg.items()},
                "sector_allocation": {k: round(v, 6) for k, v in sector_alloc.items()},
                "rating_allocation": {k: round(v, 6) for k, v in rating_alloc.items()},
                "currency_allocation": {portfolio.currency: 1.0},
                "maturity_distribution": {
                    k: round(v, 6) for k, v in maturity_dist.items()
                },
            }
        )

    # ── P&L ───────────────────────────────────────────────────────────────────

    @action(detail=True, methods=["get"], url_path="pnl")
    def pnl(self, request, pk=None):
        """Unrealised P&L versus purchase price for each position."""
        portfolio = self.get_object()
        settle_str = request.query_params.get("settlement")
        settle = date.fromisoformat(settle_str) if settle_str else date.today()

        bonds, ytms, faces, pp, pd_ = _resolve_portfolio_bonds(portfolio, settle)
        if not bonds:
            raise ValidationError("Portfolio has no valid bonds")

        result = rs.portfolio_pnl(bonds, ytms, faces, pp, pd_, settle)
        return Response({"portfolio_id": str(portfolio.id), **result})

    # ── Duration Buckets ──────────────────────────────────────────────────────

    @action(detail=True, methods=["get"], url_path="duration-buckets")
    def duration_buckets(self, request, pk=None):
        """Break portfolio duration into maturity buckets."""
        portfolio = self.get_object()
        settle_str = request.query_params.get("settlement")
        settle = date.fromisoformat(settle_str) if settle_str else date.today()

        bonds, ytms, faces, *_ = _resolve_portfolio_bonds(portfolio, settle)
        if not bonds:
            raise ValidationError("Portfolio has no valid bonds")

        report = rs.duration_bucket_report(bonds, ytms, faces, settle)
        return Response({"portfolio_id": str(portfolio.id), **report})

    # ── Standard Scenarios ────────────────────────────────────────────────────

    @action(detail=True, methods=["post"], url_path="scenarios")
    def scenarios(self, request, pk=None):
        """Run the standard set of 10 rate scenarios."""
        portfolio = self.get_object()
        settle_str = request.query_params.get("settlement")
        settle = date.fromisoformat(settle_str) if settle_str else date.today()

        bonds, ytms, faces, *_ = _resolve_portfolio_bonds(portfolio, settle)
        if not bonds:
            raise ValidationError("Portfolio has no valid bonds")

        results = rs.run_standard_scenarios(bonds, ytms, faces, settle)
        return Response(
            {
                "portfolio_id": str(portfolio.id),
                "settlement_date": settle.isoformat(),
                "scenarios": [r.model_dump() for r in results],
            }
        )

    # ── Custom Scenario ───────────────────────────────────────────────────────

    @action(detail=True, methods=["post"], url_path="custom-scenario")
    def custom_scenario(self, request, pk=None):
        """Run a user-defined scenario with arbitrary rate shifts."""
        portfolio = self.get_object()
        ser = ScenarioShiftSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        settle_str = request.query_params.get("settlement")
        settle = date.fromisoformat(settle_str) if settle_str else date.today()

        bonds, ytms, faces, *_ = _resolve_portfolio_bonds(portfolio, settle)
        if not bonds:
            raise ValidationError("Portfolio has no valid bonds")

        shift = ScenarioShiftSchema(**data)
        result = rs.scenario_pnl(bonds, ytms, faces, settle, shift, "custom")
        return Response(result.model_dump())

    # ── VaR ───────────────────────────────────────────────────────────────────

    @action(detail=True, methods=["post"], url_path="var")
    def var(self, request, pk=None):
        """Historical and parametric VaR / CVaR."""
        portfolio = self.get_object()
        ser = VaRRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        settle = date.today()
        bonds, ytms, faces, *_ = _resolve_portfolio_bonds(portfolio, settle)
        if not bonds:
            raise ValidationError("Portfolio has no valid bonds")

        metrics = rs.portfolio_risk_metrics(bonds, ytms, faces, settle)
        dv01_total = metrics["portfolio_dv01"]

        hist_df = asyncio.run(fetch_yield_history(lookback_days=data["lookback_days"]))
        yield_changes = compute_yield_changes(hist_df)
        yield_vol = float(yield_changes.std()) if len(yield_changes) > 1 else 0.001

        hist_result = rs.historical_var(
            yield_changes,
            dv01_total,
            data["confidence_level"],
            data["holding_period_days"],
        )
        param_result = rs.parametric_var(
            dv01_total,
            yield_vol,
            data["confidence_level"],
            data["holding_period_days"],
        )

        rolling_vol = compute_rolling_volatility(hist_df)
        clean_vol = rolling_vol.dropna()
        current_vol = float(clean_vol.iloc[-1]) if not clean_vol.empty else yield_vol

        return Response(
            {
                "portfolio_id": str(portfolio.id),
                "historical": hist_result,
                "parametric": param_result,
                "current_annualised_vol_pct": round(current_vol * 100, 4),
                "portfolio_dv01": round(dv01_total, 4),
                "total_market_value": round(metrics["total_market_value"], 2),
            }
        )

    # ── Credit Spread Sensitivity (CS01) ──────────────────────────────────────

    @action(detail=True, methods=["get"], url_path="cs01")
    def cs01(self, request, pk=None):
        """Credit spread sensitivity (CS01) for each position."""
        portfolio = self.get_object()
        settle = date.today()
        spread_bump = float(request.query_params.get("spread_bump_bps", 1.0))

        bonds, ytms, faces, *_ = _resolve_portfolio_bonds(portfolio, settle)
        if not bonds:
            raise ValidationError("Portfolio has no valid bonds")

        result = rs.credit_spread_sensitivity(bonds, ytms, faces, settle, spread_bump)
        return Response({"portfolio_id": str(portfolio.id), **result})
