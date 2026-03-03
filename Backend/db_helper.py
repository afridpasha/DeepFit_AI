"""
Database Helper - Simplifies access to separate MongoDB databases
"""
from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

class DatabaseHelper:
    _instance = None
    _client = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseHelper, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize MongoDB connection"""
        MONGODB_URI = os.getenv('MONGODB_URI')
        self._client = MongoClient(MONGODB_URI)
        
        # Database references
        self.users_db = self._client[os.getenv('DB_USERS', 'users_db')]
        self.height_videos_db = self._client[os.getenv('DB_HEIGHT_VIDEOS', 'height_videos_db')]
        self.exercise_sessions_db = self._client[os.getenv('DB_EXERCISE_SESSIONS', 'exercise_sessions_db')]
        self.exercise_results_db = self._client[os.getenv('DB_EXERCISE_RESULTS', 'exercise_results_db')]
        self.situps_db = self._client[os.getenv('DB_SITUPS', 'situps_db')]
        self.dumbbell_db = self._client[os.getenv('DB_DUMBBELL', 'dumbbell_db')]
        self.vertical_jump_db = self._client[os.getenv('DB_VERTICAL_JUMP', 'vertical_jump_db')]
        self.height_weight_db = self._client[os.getenv('DB_HEIGHT_WEIGHT', 'height_weight_db')]
        self.final_estimated_db = self._client[os.getenv('DB_FINAL_ESTIMATED', 'final_estimated_db')]
        self.qualified_results_db = self._client[os.getenv('DB_QUALIFIED_RESULTS', 'qualified_results_db')]
        self.measurements_db = self._client[os.getenv('DB_MEASUREMENTS', 'measurements_db')]
    
    # Collection shortcuts
    @property
    def users(self):
        return self.users_db['users']
    
    @property
    def height_videos(self):
        return self.height_videos_db['videos']
    
    @property
    def exercise_sessions(self):
        return self.exercise_sessions_db['sessions']
    
    @property
    def exercise_results(self):
        return self.exercise_results_db['results']
    
    @property
    def situps(self):
        return self.situps_db['data']
    
    @property
    def dumbbell(self):
        return self.dumbbell_db['data']
    
    @property
    def vertical_jump(self):
        return self.vertical_jump_db['data']
    
    @property
    def height_weight(self):
        return self.height_weight_db['measurements']
    
    @property
    def final_estimated(self):
        return self.final_estimated_db['estimates']
    
    @property
    def qualified_results(self):
        return self.qualified_results_db['results']
    
    @property
    def measurements(self):
        return self.measurements_db['data']

# Singleton instance
db_helper = DatabaseHelper()
