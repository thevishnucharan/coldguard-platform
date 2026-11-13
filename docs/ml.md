# Machine Learning Integration

The ColdGuard platform includes provisions for Machine Learning anomaly detection, running concurrently alongside the deterministic rule-based engines.

## Anomaly Service
The `MLAnomalyService` evaluates telemetry streams for predictive failures that do not necessarily cross hard thresholds.

### Example Use Cases
1. **Compressor Degradation**: Identifying a slow, steady rise in average temperature over weeks, indicating imminent hardware failure.
2. **Defrost Cycle Anomalies**: Detecting irregular patterns during automated defrost cycles.

### Current Implementation
Currently implemented locally using a Mock Provider (`AI_PROVIDER=mock`). The service is stubbed out to evaluate readings and generate placeholder predictions to test the architecture flow without requiring a heavy GPU or PyTorch dependency.

### Future Enhancements
Integration with Azure Machine Learning or custom trained models (Isolation Forests, LSTMs) to provide genuine predictive insights.
