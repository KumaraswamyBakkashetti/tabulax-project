from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection
from typing import Optional
import bcrypt
from datetime import datetime
import logging
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MongoDB connection URL
MONGODB_URL = os.getenv('MONGODB_URL', "mongodb://localhost:27017")
DATABASE_NAME = os.getenv('DATABASE_NAME', "tabula")

logger.info(f"Using MongoDB URL: {MONGODB_URL}")
logger.info(f"Using Database: {DATABASE_NAME}")

# MongoDB client instance
client: Optional[AsyncIOMotorClient] = None
db: Optional[Database] = None

# Collections
users: Optional[Collection] = None

async def connect_to_mongo():
    """Connect to MongoDB."""
    global client, db, users
    try:
        logger.info("Attempting to connect to MongoDB...")
        client = AsyncIOMotorClient(MONGODB_URL, serverSelectionTimeoutMS=5000)
        # Verify the connection
        await client.server_info()
        
        db = client[DATABASE_NAME]
        users = db.users
        
        # Create unique index on username and email
        await users.create_index("username", unique=True)
        await users.create_index("email", unique=True)
        
        logger.info("Successfully connected to MongoDB.")
        # Log the number of existing users
        user_count = await users.count_documents({})
        logger.info(f"Number of existing users in database: {user_count}")
        
    except Exception as e:
        logger.error(f"Could not connect to MongoDB: {str(e)}")
        raise

async def close_mongo_connection():
    """Close MongoDB connection."""
    global client
    if client:
        client.close()
        logger.info("MongoDB connection closed.")

def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt."""
    try:
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode(), salt)
        return hashed.decode()
    except Exception as e:
        logger.error(f"Error hashing password: {str(e)}")
        raise

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode(),
            hashed_password.encode()
        )
    except Exception as e:
        logger.error(f"Error verifying password: {str(e)}")
        return False

async def get_user_by_username(username: str):
    """Get a user by username."""
    if users is None:
        logger.error("Database not initialized")
        raise Exception("Database not initialized")
    try:
        logger.info(f"Looking up user: {username}")
        user = await users.find_one({"username": username})
        if user:
            logger.info(f"Found user: {username}")
        else:
            logger.info(f"User not found: {username}")
        return user
    except Exception as e:
        logger.error(f"Error finding user {username}: {str(e)}")
        raise

async def get_user_by_email(email: str):
    """Get a user by email."""
    if users is None:
        logger.error("Database not initialized")
        raise Exception("Database not initialized")
    try:
        return await users.find_one({"email": email})
    except Exception as e:
        logger.error(f"Error finding user by email {email}: {str(e)}")
        raise

async def create_user(user_data: dict):
    """Create a new user."""
    if users is None:
        logger.error("Database not initialized")
        raise Exception("Database not initialized")
    
    try:
        logger.info(f"Creating new user: {user_data['username']}")
        # Hash the password
        user_data["hashed_password"] = get_password_hash(user_data.pop("password"))
        user_data["created_at"] = datetime.utcnow()
        user_data["last_login"] = None
        user_data["is_active"] = True
        
        result = await users.insert_one(user_data)
        logger.info(f"Successfully created user: {user_data['username']}")
        return result.inserted_id
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        raise

async def update_last_login(user_id: str):
    """Update user's last login time."""
    if users is None:
        logger.error("Database not initialized")
        raise Exception("Database not initialized")
    
    try:
        logger.info(f"Updating last login for user ID: {user_id}")
        await users.update_one(
            {"_id": user_id},
            {"$set": {"last_login": datetime.utcnow()}}
        )
        logger.info(f"Successfully updated last login for user ID: {user_id}")
    except Exception as e:
        logger.error(f"Error updating last login: {str(e)}")
        raise 