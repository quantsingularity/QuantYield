"""
QuantYield Backend - ML Forecaster Bridge
Delegates to code/ml_services for all forecasting logic.
The backend imports this thin wrapper so Django views remain unchanged.

Bug fixes applied:
- sys.path was inserting ml_services/ itself (so ml_services.forecaster resolved
  to ml_services/ml_services/forecaster.py, which does not exist).  Fixed to
  insert the *parent* of ml_services (i.e. code/) so the import resolves
  correctly whether running locally or inside Docker.
- The bridge now normalises the return type of forecast_rates() to a plain dict
  so views can use ["point"] / ["lower"] / ["upper"] subscript access regardless
  of which backend is active.  ml_services.forecaster returns a ForecastResult
  dataclass; the fallback already returns a dict.
"""

import os
import sys

# Insert the directory that *contains* the ml_services package.
# __file__ lives at  .../code/backend/services/ml_forecaster.py
# Two levels up      .../code/backend/services/../../  ==  .../code/
# In Docker (WORKDIR /code/backend):
#   __file__  = /code/backend/services/ml_forecaster.py
#   two up    = /code/  which is where ml_services/ lives after COPY
_ml_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ml_path not in sys.path:
    sys.path.insert(0, _ml_path)

try:
    from ml_services.forecaster import available_backend, clear_model_cache
    from ml_services.forecaster import forecast_rates as _ml_forecast_rates
    from ml_services.forecaster import train_forecaster as train_lstm_forecaster

    def forecast_rates(model_state, rate_series, horizon_days=30, **kwargs):
        """Normalise ForecastResult dataclass -> plain dict for view compatibility."""
        result = _ml_forecast_rates(model_state, rate_series, horizon_days, **kwargs)
        if isinstance(result, dict):
            return result
        # ForecastResult dataclass - convert to the dict shape views expect
        return {
            "point": result.point,
            "lower": result.lower,
            "upper": result.upper,
            "backend": result.backend,
        }

except ImportError:
    # Fallback: self-contained AR(1) implementation - always available
    import numpy as np

    _MODEL_CACHE: dict = {}

    def train_lstm_forecaster(
        rate_series,
        seq_len=20,
        hidden_size=64,
        epochs=50,
        lr=0.001,
        force_retrain=False,
    ):
        cache_key = (seq_len, hidden_size, epochs)
        if not force_retrain and cache_key in _MODEL_CACHE:
            return _MODEL_CACHE[cache_key]
        diffs = np.diff(rate_series)
        phi = float(np.corrcoef(diffs[:-1], diffs[1:])[0, 1]) if len(diffs) > 1 else 0.0
        phi = float(np.clip(phi, -0.99, 0.99))
        sigma = float(np.std(diffs)) if len(diffs) > 0 else 0.001
        state = {
            "model": None,
            "mean": float(np.mean(rate_series)),
            "std": float(np.std(rate_series)) or 1.0,
            "seq_len": seq_len,
            "backend": "arima",
            "last_value": float(rate_series[-1]),
            "phi": phi,
            "sigma": sigma,
        }
        _MODEL_CACHE[cache_key] = state
        return state

    def forecast_rates(
        model_state, rate_series, horizon_days=30, n_simulations=300, **kwargs
    ):
        phi = model_state.get("phi", 0.0)
        sigma = model_state.get("sigma", 0.001)
        last = model_state.get("last_value", float(rate_series[-1]))
        diffs = np.diff(rate_series)
        last_diff = float(diffs[-1]) if len(diffs) > 0 else 0.0
        point, cur_val, cur_diff = [], last, last_diff
        for _ in range(horizon_days):
            nxt_diff = phi * cur_diff
            cur_val = max(cur_val + nxt_diff, 0.0001)
            point.append(cur_val)
            cur_diff = nxt_diff
        rng = np.random.default_rng(42)
        sims = []
        for _ in range(n_simulations):
            sv, sd = last, last_diff
            path = []
            for _ in range(horizon_days):
                nd = phi * sd + rng.normal(0, sigma)
                sv = max(sv + nd, 0.0001)
                path.append(sv)
                sd = nd
            sims.append(path)
        sims_arr = np.array(sims)
        lower = np.percentile(sims_arr, 5, axis=0).tolist()
        upper = np.percentile(sims_arr, 95, axis=0).tolist()
        return {"point": point, "lower": lower, "upper": upper, "backend": "arima"}

    def clear_model_cache():
        _MODEL_CACHE.clear()

    def available_backend():
        return "arima"
