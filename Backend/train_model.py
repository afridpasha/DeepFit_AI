import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
from sklearn.preprocessing import StandardScaler
import joblib
import os

# Get correct path to training data
current_dir = os.path.dirname(os.path.abspath(__file__))
training_data_path = os.path.join(current_dir, '..', 'Datasets', 'training_data.csv')
training_data_path = os.path.normpath(training_data_path)

print(f"Loading training data from: {training_data_path}")

if not os.path.exists(training_data_path):
    print(f"❌ Error: training_data.csv not found at {training_data_path}")
    exit(1)

df = pd.read_csv(training_data_path)
print(f"✅ Loaded {len(df)} training samples")

X = df[['avg_rom', 'avg_velocity', 'weight_kg']]  # Features (weight as target)
y = df['weight_kg']

scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)
model = RandomForestRegressor(n_estimators=100)
model.fit(X_train, y_train)

predictions = model.predict(X_test)
error = mean_absolute_error(y_test, predictions)
print(f"Model trained! Error: {error:.2f} kg")

# Save models to models directory
models_dir = os.path.join(current_dir, 'models')
os.makedirs(models_dir, exist_ok=True)

model_path = os.path.join(models_dir, 'weight_model.pkl')
scaler_path = os.path.join(models_dir, 'scaler.pkl')

joblib.dump(model, model_path)
joblib.dump(scaler, scaler_path)

print(f"✅ Model saved to: {model_path}")
print(f"✅ Scaler saved to: {scaler_path}")