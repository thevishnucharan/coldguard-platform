import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
import joblib
import os

def generate_synthetic_data(num_samples=10000):
    """
    Generates synthetic temperature data simulating a cold-chain storage unit.
    Normal data oscillates between 2 and 8 degrees C.
    Anomalous data includes spikes, rapid drifts, and random noise.
    """
    print("Generating synthetic data...")
    timestamps = pd.date_range(start="2026-01-01", periods=num_samples, freq="min")
    
    # Base normal temperature (sine wave + noise)
    base_temp = 5.0 + 2.5 * np.sin(np.linspace(0, 50, num_samples))
    noise = np.random.normal(0, 0.2, num_samples)
    temps = base_temp + noise
    
    # Inject anomalies (~5% of data)
    num_anomalies = int(num_samples * 0.05)
    anomaly_indices = np.random.choice(num_samples, num_anomalies, replace=False)
    
    for idx in anomaly_indices:
        anomaly_type = np.random.choice(['spike', 'drop', 'drift_up'])
        if anomaly_type == 'spike':
            temps[idx] += np.random.uniform(5, 15)
        elif anomaly_type == 'drop':
            temps[idx] -= np.random.uniform(5, 10)
        elif anomaly_type == 'drift_up':
            # Create a localized rapid drift over 5 readings
            end_idx = min(idx + 5, num_samples)
            temps[idx:end_idx] += np.linspace(2, 10, end_idx - idx)
            
    df = pd.DataFrame({
        'timestamp': timestamps,
        'temperature': temps
    })
    
    return df

def extract_features(df):
    """
    Extracts features for the Isolation Forest model.
    These features represent the behavior of the time series.
    """
    print("Extracting features...")
    df_features = pd.DataFrame()
    df_features['current_temp'] = df['temperature']
    
    # Rolling features (using past 10 readings)
    rolling = df['temperature'].rolling(window=10, min_periods=1)
    df_features['rolling_mean'] = rolling.mean()
    df_features['rolling_std'] = rolling.std().fillna(0)
    
    # Deviations
    df_features['deviation_from_mean'] = df['temperature'] - df_features['rolling_mean']
    
    # Rate of change (derivative)
    df_features['rate_of_change'] = df['temperature'].diff().fillna(0)
    
    # Temp range in the rolling window
    df_features['temp_range'] = rolling.max() - rolling.min()
    
    return df_features

def train_model():
    """
    Trains the Isolation Forest prototype and saves the model.
    """
    df = generate_synthetic_data(10000)
    X = extract_features(df)
    
    print("Training Isolation Forest prototype...")
    # contamination is the expected proportion of outliers
    clf = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
    clf.fit(X)
    
    # Ensure the models directory exists
    os.makedirs(os.path.join(os.path.dirname(__file__), "models"), exist_ok=True)
    
    model_path = os.path.join(os.path.dirname(__file__), "models", "isolation_forest.joblib")
    joblib.dump(clf, model_path)
    print(f"Model successfully saved to {model_path}")
    
    # Evaluation
    predictions = clf.predict(X)
    anomalies = (predictions == -1).sum()
    print(f"Detected {anomalies} anomalies out of {len(X)} samples.")

if __name__ == "__main__":
    train_model()
