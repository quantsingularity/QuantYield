"""
QuantYield — Curves API Views
Treasury curve retrieval (Django-cached), custom curve CRUD,
interpolation, forward rates, par yields, regime detection, LSTM/AR(1) forecasting.
"""

import asyncio
import logging
from datetime import date, timedelta

import numpy as np
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from services import curve_builder as cb
from services.data_feed import fetch_treasury_curve, fetch_yield_history
from services.ml_forecaster import forecast_rates, train_lstm_forecaster
from services.schemas import CurvePointSchema

from .models import YieldCurve
from .serializers import (
    CurveForecastSerializer,
    CurveInterpolateSerializer,
    ForwardRateSerializer,
    YieldCurveSerializer,
)

logger = logging.getLogger("quantyield")

_STANDARD_TENORS = [0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 25, 30]

# In-process spline store (curve_id → CubicSpline)
_spline_store: dict = {}


def _fit_curve(curve: YieldCurve) -> tuple[dict, float, float]:
    points = [
        CurvePointSchema(tenor=p.tenor, rate=p.rate, instrument=p.instrument)
        for p in curve.points.all()
    ]
    model = curve.model

    if not points:
        return {}, 0.0, 0.0

    if model == "nelson_siegel":
        params, r2, rmse = cb.fit_nelson_siegel(points)
        return params.model_dump(), r2, rmse

    if model == "svensson":
        params, r2, rmse = cb.fit_svensson(points)
        return params.model_dump(), r2, rmse

    if model == "bootstrap":
        spot_rates = cb.bootstrap_spot_rates(points)
        return {"spot_rates": {str(k): v for k, v in spot_rates.items()}}, 1.0, 0.0

    if model == "cubic_spline":
        spline = cb.fit_cubic_spline(points)
        tenors = np.array([p.tenor for p in points])
        rates = np.array([p.rate for p in points])
        fitted = np.array([float(spline(t)) for t in tenors])
        residuals = rates - fitted
        ss_res = float(np.sum(residuals**2))
        ss_tot = float(np.sum((rates - np.mean(rates)) ** 2))
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 1.0
        rmse = float(np.sqrt(np.mean(residuals**2)))
        return {"model": "cubic_spline_fitted"}, r2, rmse

    return {}, 0.0, 0.0


class YieldCurveViewSet(viewsets.ModelViewSet):
    """CRUD + analytics for yield curves."""

    queryset = YieldCurve.objects.prefetch_related("points").all()
    serializer_class = YieldCurveSerializer
    search_fields = ["name", "currency"]
    ordering_fields = ["as_of_date", "name", "created_at"]
    ordering = ["-as_of_date"]

    def create(self, request, *args, **kwargs):
        ser = YieldCurveSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        curve = ser.save()

        # Fit model and persist parameters
        params, r2, rmse = _fit_curve(curve)
        curve.parameters = params
        curve.r_squared = r2
        curve.rmse = rmse
        curve.save(update_fields=["parameters", "r_squared", "rmse"])

        if curve.model == "cubic_spline" and curve.points.count() >= 3:
            pts = [
                CurvePointSchema(tenor=p.tenor, rate=p.rate) for p in curve.points.all()
            ]
            _spline_store[str(curve.id)] = cb.fit_cubic_spline(pts)

        return Response(
            YieldCurveSerializer(curve).data, status=status.HTTP_201_CREATED
        )

    def destroy(self, request, *args, **kwargs):
        curve = self.get_object()
        _spline_store.pop(str(curve.id), None)
        curve.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ── Treasury Curve (live, cached) ─────────────────────────────────────────

    @action(detail=False, methods=["get"], url_path="treasury")
    def treasury(self, request):
        """Live US Treasury curve with NS fit, spline, spot rates, forwards, regime."""
        as_of_str = request.query_params.get("as_of_date")
        as_of_date = date.fromisoformat(as_of_str) if as_of_str else None

        points = asyncio.run(fetch_treasury_curve(as_of_date))
        curve_pts = [CurvePointSchema(**p) for p in points]

        ns_params, r2, rmse = cb.fit_nelson_siegel(curve_pts)
        spot_rates = cb.bootstrap_spot_rates(curve_pts)
        spline = cb.fit_cubic_spline(curve_pts)

        ns_rates = {
            str(t): round(
                cb.nelson_siegel_rate(
                    t,
                    ns_params.beta0,
                    ns_params.beta1,
                    ns_params.beta2,
                    ns_params.lambda1,
                ),
                6,
            )
            for t in _STANDARD_TENORS
        }
        spline_rates = {str(t): round(float(spline(t)), 6) for t in _STANDARD_TENORS}
        par_yields = {
            str(t): round(cb.par_yield(spot_rates, t), 6) for t in _STANDARD_TENORS
        }
        spot_out = {str(k): round(v, 6) for k, v in spot_rates.items()}

        forward_rates = {}
        for t1, t2 in [(1, 2), (2, 5), (5, 10), (10, 30)]:
            r1 = cb._interpolate_spot(spot_rates, float(t1))
            r2_ = cb._interpolate_spot(spot_rates, float(t2))
            fwd = cb.forward_rate(r1, r2_, float(t1), float(t2))
            forward_rates[f"{t1}x{t2}"] = round(fwd, 6)

        regime_info = cb.detect_regime(spot_rates)

        return Response(
            {
                "as_of_date": (as_of_date or date.today()).isoformat(),
                "market_points": points,
                "nelson_siegel_params": ns_params.model_dump(),
                "fit_r_squared": round(r2, 6),
                "fit_rmse": round(rmse, 6),
                "interpolated_rates": ns_rates,
                "spline_rates": spline_rates,
                "par_yields": par_yields,
                "forward_rates": forward_rates,
                "spot_rates": spot_out,
                "regime": regime_info,
            }
        )

    @action(detail=False, methods=["get"], url_path="treasury/regime")
    def treasury_regime(self, request):
        """Current yield curve regime classification."""
        points = asyncio.run(fetch_treasury_curve())
        curve_pts = [CurvePointSchema(**p) for p in points]
        spot_rates = cb.bootstrap_spot_rates(curve_pts)
        regime = cb.detect_regime(spot_rates)
        return Response({"as_of_date": date.today().isoformat(), **regime})

    # ── Interpolation ──────────────────────────────────────────────────────────

    @action(detail=True, methods=["post"], url_path="interpolate")
    def interpolate(self, request, pk=None):
        curve = self.get_object()
        ser = CurveInterpolateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        model = curve.model
        params = curve.parameters or {}
        spline = _spline_store.get(str(curve.id))

        if model == "cubic_spline" and spline is None:
            pts = [
                CurvePointSchema(tenor=p.tenor, rate=p.rate) for p in curve.points.all()
            ]
            if len(pts) >= 3:
                spline = cb.fit_cubic_spline(pts)
                _spline_store[str(curve.id)] = spline

        spot_rates = None
        if model == "bootstrap":
            raw_sr = params.get("spot_rates", {})
            spot_rates = {float(k): v for k, v in raw_sr.items()}

        results = {}
        for tenor in ser.validated_data["tenors"]:
            rate = cb.interpolate_rate(
                model, params, tenor, spline=spline, spot_rates=spot_rates
            )
            results[str(tenor)] = round(rate, 6)

        return Response({"curve_id": str(curve.id), "model": model, "rates": results})

    # ── Forward Rate ───────────────────────────────────────────────────────────

    @action(detail=True, methods=["post"], url_path="forward-rate")
    def forward_rate_endpoint(self, request, pk=None):
        curve = self.get_object()
        ser = ForwardRateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        model = curve.model
        params = curve.parameters or {}
        spline = _spline_store.get(str(curve.id))
        spot_rates = None

        if model == "bootstrap":
            raw_sr = params.get("spot_rates", {})
            spot_rates = {float(k): v for k, v in raw_sr.items()}

        r1 = cb.interpolate_rate(
            model, params, data["start_tenor"], spline=spline, spot_rates=spot_rates
        )
        r2 = cb.interpolate_rate(
            model, params, data["end_tenor"], spline=spline, spot_rates=spot_rates
        )

        try:
            fwd = cb.forward_rate(r1, r2, data["start_tenor"], data["end_tenor"])
        except ValueError as exc:
            raise ValidationError(str(exc))

        return Response(
            {
                "curve_id": str(curve.id),
                "start_tenor": data["start_tenor"],
                "end_tenor": data["end_tenor"],
                "spot_rate_t1": round(r1, 6),
                "spot_rate_t2": round(r2, 6),
                "forward_rate": round(fwd, 6),
            }
        )

    # ── LSTM / AR(1) Forecast ──────────────────────────────────────────────────

    @action(detail=True, methods=["post"], url_path="forecast")
    def forecast(self, request, pk=None):
        curve = self.get_object()  # validate exists and cache for response
        ser = CurveForecastSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        hist_df = asyncio.run(fetch_yield_history())
        rate_series = hist_df["rate"].values

        model_state = train_lstm_forecaster(rate_series, epochs=50)
        forecast_data = forecast_rates(model_state, rate_series, data["horizon_days"])

        tenors = ["2Y", "5Y", "10Y", "30Y"]
        base_spreads = {"2Y": -0.001, "5Y": 0.0, "10Y": 0.002, "30Y": 0.001}
        horizon_days = data["horizon_days"]

        forecast_dates = [
            (date.today() + timedelta(days=i + 1)).isoformat()
            for i in range(horizon_days)
        ]

        forecast_by_tenor: dict = {}
        lower_by_tenor: dict = {}
        upper_by_tenor: dict = {}

        for t in tenors:
            spread = base_spreads.get(t, 0.0)
            forecast_by_tenor[t] = [
                round(v + spread, 6) for v in forecast_data["point"]
            ]
            lower_by_tenor[t] = [round(v + spread, 6) for v in forecast_data["lower"]]
            upper_by_tenor[t] = [round(v + spread, 6) for v in forecast_data["upper"]]

        return Response(
            {
                "curve_id": str(curve.id),
                "horizon_days": horizon_days,
                "forecast_dates": forecast_dates,
                "forecast_rates": forecast_by_tenor,
                "lower_bound": lower_by_tenor if data["confidence_intervals"] else None,
                "upper_bound": upper_by_tenor if data["confidence_intervals"] else None,
                "model_used": model_state.get("backend", "arima"),
            }
        )
