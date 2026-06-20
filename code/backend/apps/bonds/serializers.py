"""
QuantYield — Bond Serializers
Handles serialization, nested call schedules, and computed analytics fields.
"""

import math
import re
from datetime import date

from rest_framework import serializers
from services import pricing as ps
from services.schemas import BondSchema, CallDateSchema

from .models import Bond, CallSchedule


class CallScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = CallSchedule
        fields = ["id", "call_date", "call_price"]
        read_only_fields = ["id"]


class BondSerializer(serializers.ModelSerializer):
    """Full bond serializer with nested call schedule."""

    call_schedule = CallScheduleSerializer(many=True, required=False, default=list)

    class Meta:
        model = Bond
        fields = [
            "id",
            "isin",
            "name",
            "issuer",
            "face_value",
            "coupon_rate",
            "maturity_date",
            "issue_date",
            "settlement_date",
            "coupon_frequency",
            "bond_type",
            "day_count",
            "currency",
            "credit_rating",
            "sector",
            "description",
            "call_schedule",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_isin(self, value):
        if value is None:
            return value
        v = value.upper().strip()
        if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", v):
            raise serializers.ValidationError(
                "ISIN must be 12 characters: 2-letter country code, "
                "9 alphanumeric, and 1 numeric check digit."
            )
        return v

    def validate(self, data):
        maturity = data.get("maturity_date") or (
            self.instance.maturity_date if self.instance else None
        )
        issue = data.get("issue_date") or (
            self.instance.issue_date if self.instance else None
        )
        if maturity and issue and maturity <= issue:
            raise serializers.ValidationError(
                "maturity_date must be strictly after issue_date"
            )
        return data

    def create(self, validated_data):
        call_schedule_data = validated_data.pop("call_schedule", [])
        bond = Bond.objects.create(**validated_data)
        for cs in call_schedule_data:
            CallSchedule.objects.create(bond=bond, **cs)
        return bond

    def update(self, instance, validated_data):
        call_schedule_data = validated_data.pop("call_schedule", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if call_schedule_data is not None:
            instance.call_schedule.all().delete()
            for cs in call_schedule_data:
                CallSchedule.objects.create(bond=instance, **cs)
        return instance


class BondUpdateSerializer(serializers.ModelSerializer):
    """Partial-update serializer — only editable metadata fields."""

    class Meta:
        model = Bond
        fields = ["name", "issuer", "credit_rating", "sector", "description"]

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class BondAnalyticsSerializer(serializers.ModelSerializer):
    """
    Read-only serializer that includes live computed analytics.
    The settlement_date is injected externally before serialization.
    """

    call_schedule = CallScheduleSerializer(many=True, read_only=True)

    # Computed analytics (populated via to_representation)
    dirty_price = serializers.FloatField(read_only=True, allow_null=True)
    clean_price = serializers.FloatField(read_only=True, allow_null=True)
    ytm = serializers.FloatField(read_only=True, allow_null=True)
    duration = serializers.FloatField(read_only=True, allow_null=True)
    modified_duration = serializers.FloatField(read_only=True, allow_null=True)
    convexity = serializers.FloatField(read_only=True, allow_null=True)
    dv01 = serializers.FloatField(read_only=True, allow_null=True)
    accrued_interest = serializers.FloatField(read_only=True, allow_null=True)
    years_to_maturity = serializers.FloatField(read_only=True, allow_null=True)

    class Meta:
        model = Bond
        fields = [
            "id",
            "isin",
            "name",
            "issuer",
            "face_value",
            "coupon_rate",
            "maturity_date",
            "issue_date",
            "settlement_date",
            "coupon_frequency",
            "bond_type",
            "day_count",
            "currency",
            "credit_rating",
            "sector",
            "description",
            "call_schedule",
            "created_at",
            "updated_at",
            # analytics
            "dirty_price",
            "clean_price",
            "ytm",
            "duration",
            "modified_duration",
            "convexity",
            "dv01",
            "accrued_interest",
            "years_to_maturity",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        settlement = self.context.get("settlement") or date.today()
        try:
            bond_schema = _bond_to_schema(instance)
            ai = ps.accrued_interest(bond_schema, settlement)
            coupon_dates = ps.generate_coupon_dates(bond_schema, settlement)
            if not coupon_dates:
                ytm = float(instance.coupon_rate)
            else:
                ytm = ps.ytm_from_clean_price(
                    bond_schema, float(instance.face_value), settlement
                )
                if math.isnan(ytm):
                    ytm = float(instance.coupon_rate)
            dp = ps.dirty_price_from_yield(bond_schema, ytm, settlement)
            cp = dp - ai
            t_mat = (instance.maturity_date - settlement).days / 365.0
            data.update(
                {
                    "dirty_price": round(dp, 6),
                    "clean_price": round(cp, 6),
                    "ytm": round(ytm, 8),
                    "duration": round(
                        ps.macaulay_duration(bond_schema, ytm, settlement), 6
                    ),
                    "modified_duration": round(
                        ps.modified_duration(bond_schema, ytm, settlement), 6
                    ),
                    "convexity": round(ps.convexity(bond_schema, ytm, settlement), 6),
                    "dv01": round(ps.dv01(bond_schema, ytm, settlement), 6),
                    "accrued_interest": round(ai, 6),
                    "years_to_maturity": round(t_mat, 4),
                }
            )
        except Exception:
            pass
        return data


# ── Helper: ORM Bond → service schema ────────────────────────────────────────


def _bond_to_schema(bond: Bond) -> BondSchema:
    cs = [
        CallDateSchema(call_date=c.call_date, call_price=float(c.call_price))
        for c in bond.call_schedule.all()
    ]
    return BondSchema(
        name=bond.name,
        issuer=bond.issuer,
        face_value=float(bond.face_value),
        coupon_rate=float(bond.coupon_rate),
        maturity_date=bond.maturity_date,
        issue_date=bond.issue_date,
        settlement_date=bond.settlement_date,
        coupon_frequency=bond.coupon_frequency,
        bond_type=bond.bond_type,
        day_count=bond.day_count,
        currency=bond.currency,
        credit_rating=bond.credit_rating,
        sector=bond.sector,
        call_schedule=cs or None,
    )


# ── Request serializers (for analytics endpoints) ─────────────────────────────


class PriceRequestSerializer(serializers.Serializer):
    yield_rate = serializers.FloatField(required=False, allow_null=True)
    market_price = serializers.FloatField(
        required=False, allow_null=True, min_value=0.000001
    )
    settlement_date = serializers.DateField(required=False, allow_null=True)

    def validate(self, data):
        if data.get("yield_rate") is None and data.get("market_price") is None:
            raise serializers.ValidationError(
                "Provide either yield_rate or market_price"
            )
        return data


class YieldRequestSerializer(serializers.Serializer):
    clean_price = serializers.FloatField(min_value=0.000001)
    settlement_date = serializers.DateField(required=False, allow_null=True)


class SpreadRequestSerializer(serializers.Serializer):
    clean_price = serializers.FloatField(min_value=0.000001)
    spread_type = serializers.CharField(default="z_spread")
    settlement_date = serializers.DateField(required=False, allow_null=True)


class TotalReturnRequestSerializer(serializers.Serializer):
    purchase_clean_price = serializers.FloatField(min_value=0.000001)
    horizon_years = serializers.FloatField(min_value=0.001, max_value=30)
    reinvestment_rate = serializers.FloatField(default=0.04, min_value=0)
    settlement_date = serializers.DateField(required=False, allow_null=True)


class BondCompareRequestSerializer(serializers.Serializer):
    bond_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=2,
        max_length=10,
    )
    settlement_date = serializers.DateField(required=False, allow_null=True)
