"""
Machine Learning Prediction Engine for SatQuery AI.
Uses scikit-learn to forecast future vegetation health (NDVI) and flood risk scores
based on historical and real-time EnvironmentalData.
"""

from typing import Dict, Any, List
import numpy as np
from datetime import datetime, timedelta
import logging

try:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

logger = logging.getLogger(__name__)

def predict_future_metrics(historical_data: List[Dict[str, Any]], current_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Train a machine learning model on historical data to predict future metrics.
    Currently forecasts NDVI and Flood Risk Score for the next 7 days.
    
    Args:
        historical_data: List of dicts containing past environmental metrics.
        current_data: Dict containing current real-time metrics.
        
    Returns:
        Dict containing predictions for the next 7 days.
    """
    if not SKLEARN_AVAILABLE:
        return {
            "status": "error",
            "message": "scikit-learn is not installed. Run `pip install scikit-learn`"
        }
        
    if len(historical_data) < 5:
        # Not enough historical data to train a meaningful ML model.
        # Use a heuristic fallback for demonstration based on current data.
        return _heuristic_prediction(current_data)
        
    try:
        # Prepare data for training
        # Features: day_of_year, temperature, rainfall
        # Targets: NDVI, flood_risk_score (derived)
        X = []
        y_ndvi = []
        y_flood = []
        
        for entry in historical_data:
            dt = entry.get("timestamp", datetime.utcnow())
            day_of_year = dt.timetuple().tm_yday
            temp = entry.get("temperature") or 25.0
            rain = entry.get("rainfall") or 0.0
            ndvi = entry.get("ndvi") or 0.3
            
            # Simple derived flood risk for training proxy if not directly stored
            flood_risk = min(100.0, (rain * 2.5) + (temp * 0.5))
            
            X.append([day_of_year, temp, rain])
            y_ndvi.append(ndvi)
            y_flood.append(flood_risk)
            
        X = np.array(X)
        
        # Train models
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        rf_ndvi = RandomForestRegressor(n_estimators=50, random_state=42)
        rf_ndvi.fit(X_scaled, y_ndvi)
        
        rf_flood = RandomForestRegressor(n_estimators=50, random_state=42)
        rf_flood.fit(X_scaled, y_flood)
        
        # Predict next 7 days
        predictions = []
        base_dt = datetime.utcnow()
        
        base_temp = current_data.get("temperature") or 25.0
        base_rain = current_data.get("rainfall") or 0.0
        
        for i in range(1, 8):
            target_dt = base_dt + timedelta(days=i)
            day_of_year = target_dt.timetuple().tm_yday
            
            # Simulate slight weather variations for future features
            sim_temp = base_temp + np.random.uniform(-2, 2)
            sim_rain = max(0, base_rain + np.random.uniform(-5, 5))
            
            X_future = scaler.transform([[day_of_year, sim_temp, sim_rain]])
            
            pred_ndvi = rf_ndvi.predict(X_future)[0]
            pred_flood = rf_flood.predict(X_future)[0]
            
            predictions.append({
                "date": target_dt.strftime("%Y-%m-%d"),
                "predicted_ndvi": round(float(pred_ndvi), 3),
                "predicted_flood_risk": round(float(pred_flood), 1),
                "simulated_temperature": round(float(sim_temp), 1),
                "simulated_rainfall": round(float(sim_rain), 1)
            })
            
        return {
            "status": "success",
            "model_used": "RandomForestRegressor",
            "training_samples": len(historical_data),
            "forecast": predictions
        }
        
    except Exception as e:
        logger.error(f"Prediction error: {str(e)}")
        return {
            "status": "error",
            "message": f"ML prediction failed: {str(e)}"
        }


def _heuristic_prediction(current_data: Dict[str, Any]) -> Dict[str, Any]:
    """Fallback prediction when there's insufficient historical data."""
    predictions = []
    base_dt = datetime.utcnow()
    
    base_temp = current_data.get("temperature") or 25.0
    base_rain = current_data.get("rainfall") or 0.0
    base_ndvi = current_data.get("ndvi") or 0.35
    
    for i in range(1, 8):
        target_dt = base_dt + timedelta(days=i)
        
        # Simple heuristic drift
        sim_temp = base_temp + np.random.uniform(-1, 1) * i
        sim_rain = max(0, base_rain + np.random.uniform(-2, 2) * i)
        
        # NDVI generally changes very slowly
        pred_ndvi = base_ndvi + np.random.uniform(-0.01, 0.01) * i
        pred_ndvi = max(0.0, min(1.0, pred_ndvi))
        
        # Flood risk heuristic
        pred_flood = min(100.0, (sim_rain * 2.0) + 10.0)
        
        predictions.append({
            "date": target_dt.strftime("%Y-%m-%d"),
            "predicted_ndvi": round(float(pred_ndvi), 3),
            "predicted_flood_risk": round(float(pred_flood), 1),
            "simulated_temperature": round(float(sim_temp), 1),
            "simulated_rainfall": round(float(sim_rain), 1)
        })
        
    return {
        "status": "success",
        "model_used": "Heuristic Baseline (Insufficient Data)",
        "forecast": predictions
    }
