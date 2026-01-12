from pymongo import MongoClient
import time
import os
from dotenv import load_dotenv

load_dotenv()

def connect_mongodb(max_retries=3, retry_delay=2):
    """
    Establish MongoDB connection with retry logic
    """
    MONGODB_URI = os.getenv('MONGODB_URI')
    DB_NAME = os.getenv('DB_NAME', 'sih2573')
    
    for attempt in range(max_retries):
        try:
            client = MongoClient(MONGODB_URI,
                               serverSelectionTimeoutMS=5000,
                               connectTimeoutMS=5000)
            
            client.server_info()
            print(f"[SUCCESS] MongoDB connection successful (attempt {attempt + 1})")
            
            db = client[DB_NAME]
            
            # Create indexes
            db['users'].create_index('email', unique=True)
            db['exercise_sessions'].create_index([('user_id', 1), ('date', -1)])
            db['exercise_results'].create_index([('session_id', 1)])
            db['exercise_results'].create_index([('user_id', 1), ('analyzed_at', -1)])
            
            return client, db
            
        except Exception as e:
            print(f"MongoDB connection attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                print("Failed to connect to MongoDB after all retries")
                return None, None
                
    return None, None

def get_db():
    client, db = connect_mongodb()
    return db if db else None