import pandas as pd
import numpy as np
from pymongo import MongoClient
from datetime import datetime
import os
import re
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

    @staticmethod
    def _normalize_email(email):
        if not email:
            return None
        return str(email).strip().lower()

    @staticmethod
    def _to_float(value):
        try:
            numeric = float(value)
            return numeric if numeric > 0 else None
        except (TypeError, ValueError):
            return None

    def _build_email_query(self, email):
        normalized = self._normalize_email(email)
        if not normalized:
            return None

        escaped = re.escape(normalized)
        return {
            "$or": [
                {"user_email": normalized},
                {"email": normalized},
                {"user_email": {"$regex": f"^{escaped}$", "$options": "i"}},
                {"email": {"$regex": f"^{escaped}$", "$options": "i"}}
            ]
        }

    def _find_user_by_email(self, email):
        query = self._build_email_query(email)
        if not query:
            return None
        return self.db.users.find_one(query)

    def _get_latest_measurement(self, collection_name, email_query):
        if collection_name not in self.db.list_collection_names():
            return None

        collection = self.db[collection_name]
        sort_candidates = ['timestamp', 'submission_time', 'created_at']

        for sort_field in sort_candidates:
            measurement = collection.find_one(email_query, sort=[(sort_field, -1)])
            if measurement:
                return measurement
        return None

    def _extract_height_weight(self, measurement):
        if not measurement:
            return None, None

        height = self._to_float(
            measurement.get('final_height_cm')
            if measurement.get('final_height_cm') is not None
            else measurement.get('height_cm')
        )
        weight = self._to_float(
            measurement.get('final_weight_kg')
            if measurement.get('final_weight_kg') is not None
            else measurement.get('weight_kg')
        )
        return height, weight

    @staticmethod
    def _normalize_gender(gender):
        if not gender:
            return None
        value = str(gender).strip().lower()
        if value.startswith('m'):
            return 'M'
        if value.startswith('f'):
            return 'F'
        return str(gender).strip()
    
    def get_user_profile(self, email):
        normalized_email = self._normalize_email(email)
        if not normalized_email:
            return None

        user = self._find_user_by_email(normalized_email)
        if not user:
            return None
        
        email_query = self._build_email_query(normalized_email)
        if not email_query:
            return None

        height, weight = None, None
        for collection_name in [
            'Final_Estimated_Height_and_Weight',
            'Height and Weight',
            'measurements'
        ]:
            measurement = self._get_latest_measurement(collection_name, email_query)
            if measurement:
                height, weight = self._extract_height_weight(measurement)
                if height and weight:
                    break

        # Fallback to profile fields if they exist.
        height = height or self._to_float(user.get('height'))
        weight = weight or self._to_float(user.get('weight'))

        age = user.get('age')
        try:
            age = int(age) if age is not None else None
        except (TypeError, ValueError):
            age = None
        
        return {
            'age': age,
            'gender': self._normalize_gender(user.get('gender')),
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
        if not user_profile:
            raise ValueError(f"User profile not found for {email}")

        missing_fields = [key for key, value in user_profile.items() if value in (None, "", 0)]
        if missing_fields:
            raise ValueError(
                f"Incomplete user profile for {email}. Missing fields: {', '.join(missing_fields)}"
            )
        
        matched_athlete = self.find_matching_athlete(user_profile)
        if matched_athlete is None:
            raise ValueError(f"No matching athlete found for user {email}")
        
        return {
            'situp': float(matched_athlete['Situps_per_min']),
            'vertical_jump': float(matched_athlete['Vertical_Jump_cm']),
            'dumbbell': float(matched_athlete['Dumbbell_Curl_per_min'])
        }
