import pandas as pd
import numpy as np
from pymongo import MongoClient
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

class DynamicBenchmarkSystem:
    def __init__(self, mongo_uri=None, db_name=None):
        if mongo_uri is None:
            mongo_uri = os.getenv('MONGODB_URI')
        if db_name is None:
            db_name = os.getenv('DB_NAME', 'sih2573')
        
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.athlete_data = self.load_athlete_data()
        
    def load_athlete_data(self):
        try:
            # Get the directory where this script is located
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # Go up one level to project root, then into Datasets folder
            csv_path = os.path.join(current_dir, '..', 'Datasets', 'AthleteData.csv')
            csv_path = os.path.normpath(csv_path)  # Normalize the path
            
            print(f"Loading athlete data from: {csv_path}")
            
            if not os.path.exists(csv_path):
                print(f"[ERROR] File not found at: {csv_path}")
                return None
            
            data = pd.read_csv(csv_path)
            print(f"[OK] Athlete data loaded successfully: {len(data)} athletes")
            return data
            
        except FileNotFoundError:
            print("[ERROR] AthleteData.csv not found")
            return None
        except Exception as e:
            print(f"[ERROR] Error loading athlete data: {e}")
            return None
    
    def get_user_profile(self, email):
        user = self.db.users.find_one({"email": email})
        if not user:
            return None
        
        height, weight = None, None
        
        # Check Height and Weight collection
        measurement = self.db['Height and Weight'].find_one(
            {"user_email": email}, 
            sort=[("timestamp", -1)]
        )
        if measurement:
            height = measurement.get('height_cm')
            weight = measurement.get('weight_kg')
        
        # Check Final_Estimated_Height_and_Weight if not found
        if not (height and weight):
            measurement = self.db['Final_Estimated_Height_and_Weight'].find_one(
                {"user_email": email}, 
                sort=[("timestamp", -1)]
            )
            if measurement:
                height = measurement.get('final_height_cm')
                weight = measurement.get('final_weight_kg')
        
        return {
            'age': user.get('age'),
            'gender': user.get('gender'),
            'height': height,
            'weight': weight
        }
    
    def find_matching_athlete(self, user_profile):
        if self.athlete_data is None:
            raise ValueError("Athlete dataset not loaded")
        if not all(user_profile.values()):
            raise ValueError("Incomplete user profile data")
        
        scores = []
        for _, athlete in self.athlete_data.iterrows():
            score = (
                abs(athlete['Height_cm'] - user_profile['height']) +
                abs(athlete['Weight_kg'] - user_profile['weight']) +
                abs(athlete['Age'] - user_profile['age']) +
                (100 if athlete['Gender'] != user_profile['gender'] else 0)
            )
            scores.append(score)
        
        best_match_idx = np.argmin(scores)
        return self.athlete_data.iloc[best_match_idx]
    
    def get_dynamic_benchmarks(self, email):
        user_profile = self.get_user_profile(email)
        if not user_profile or not all(user_profile.values()):
            raise ValueError(f"Incomplete user profile for {email}")
        
        matched_athlete = self.find_matching_athlete(user_profile)
        if matched_athlete is None:
            raise ValueError(f"No matching athlete found for user {email}")
        
        return {
            'situp': float(matched_athlete['Situps_per_min']),
            'vertical_jump': float(matched_athlete['Vertical_Jump_cm']),
            'dumbbell': float(matched_athlete['Dumbbell_Curl_per_min'])
        }