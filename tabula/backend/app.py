from fastapi import FastAPI, UploadFile, Form, HTTPException, Depends, status, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import mysql.connector
from mysql.connector import Error
import pandas as pd
import numpy as np
import io
import json
import logging
import os
from typing import Optional, Dict, Any
from tabulax import (
    serialize_examples,
    classify_transformation,
    generate_string_function,
    generate_algorithmic_function,
    generate_general_lookup_function,
    fit_numeric_function,
    apply_function_on_column
)
from models.user import UserCreate, User as UserModelFromModels # Alias to avoid conflict with AppUser
from database import (
    connect_to_mongo,
    close_mongo_connection,
    get_user_by_username,
    create_user,
    verify_password,
    get_password_hash,
    update_last_login,
    get_user_by_email # Added this import
)
from bson import ObjectId
import motor.motor_asyncio
from pymongo.operations import UpdateOne # <-- Added this import

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="TabulaX API", description="API for TabulaX data transformation platform")

# Configure CORS - Adjusted for debugging
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Added 127.0.0.1 explicitly
    allow_credentials=True,
    allow_methods=["*"], # Should allow all methods
    allow_headers=["*"]  # Should allow all headers, including Authorization and Content-Type
)

# Security configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Password hashing context is now managed in database.py
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Pydantic models for authentication
class Token(BaseModel):
    access_token: str
    token_type: str
    user: Optional[dict] = None # Added user field to match frontend expectation

class TokenData(BaseModel):
    username: Optional[str] = None

# User model for response (matches frontend expectations)
# class User defined in models.user is now the source of truth for this.
# This local definition might be slightly different or redundant.
# Let's ensure it's consistent or rely solely on models.user.User
# For now, keeping it as it was, but this is a point of potential refactoring.
class AppUser(BaseModel): # Renamed to avoid conflict with models.user.User
    id: str
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    created_at: datetime
    last_login: Optional[datetime] # last_login can be None initially
    is_active: bool

# App is already initialized at the top of the file

# Pydantic model for MySQL connection details
class MySQLConnectionInfo(BaseModel):
    host: str
    user: str
    password: str
    port: int = 3306 # Default MySQL port
    database: Optional[str] = None # Database is optional for initial connect to list DBs

# MongoDB Connection Information Model
class MongoConnectionInfo(BaseModel):
    uri: str # e.g., mongodb://user:password@host:port/

# In-memory storage for user data
df_storage = {}

# Authentication functions
async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    db_user = await get_user_by_username(username) # Renamed to db_user to avoid conflict
    if db_user is None:
        raise credentials_exception
    
    # Ensure all fields are present, providing defaults for Optional fields if missing
    return AppUser( # Using the renamed AppUser model
        id=str(db_user["_id"]),
        username=db_user["username"],
        email=db_user.get("email"),
        full_name=db_user.get("full_name"),
        created_at=db_user["created_at"],
        last_login=db_user.get("last_login"), # Use .get() for optional field
        is_active=db_user["is_active"]
    )

async def get_current_active_user(current_user: AppUser = Depends(get_current_user)): # Changed to AppUser
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

# Utility functions
def convert_numpy_types(obj):
    if isinstance(obj, dict):
        return {k: convert_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(i) for i in obj]
    elif isinstance(obj, (np.integer, np.floating, np.bool_)):
        return obj.item()
    elif pd.isna(obj):
        return None
    elif isinstance(obj, (np.ndarray,)):
        return obj.tolist()
    return obj

# Events
@app.on_event("startup")
async def startup_db_client():
    await connect_to_mongo()

@app.on_event("shutdown")
async def shutdown_db_client():
    await close_mongo_connection()
    # If we add a persistent MongoDB client for user interactions, close it here too
    # For now, connections for data operations will be per-request

# Authentication endpoints
@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user_doc = await get_user_by_username(form_data.username) # Renamed to user_doc
    if not user_doc or not verify_password(form_data.password, user_doc["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Update last login
    await update_last_login(user_doc["_id"])
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user_doc["username"]}, expires_delta=access_token_expires
    )
    
    # Return structure changed slightly to match Token model and common practice
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user": { # Add user details for frontend AuthContext
            "id": str(user_doc["_id"]),
            "username": user_doc["username"],
            "email": user_doc.get("email"),
            "full_name": user_doc.get("full_name")
            # Ensure these fields match what AuthContext expects for its user state
        }
    }

@app.get("/users/me/", response_model=AppUser) # Changed to AppUser
async def read_users_me(current_user: AppUser = Depends(get_current_active_user)): # Changed to AppUser
    return current_user

@app.post("/register/", response_model=AppUser)
async def register_user(user_data: UserCreate): # Renamed to user_data
    # Check if username exists
    db_user_by_name = await get_user_by_username(user_data.username) # Renamed
    if db_user_by_name:
        logger.info(f"Attempt to register existing username: {user_data.username}")
        raise HTTPException(
            status_code=400,
            detail="Username already registered"
        )
    # Check if email exists (assuming get_user_by_email is available and working)
    db_user_by_email = await get_user_by_email(user_data.email)
    if db_user_by_email:
        logger.info(f"Attempt to register existing email: {user_data.email}")
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    # Create new user using user_data.model_dump()
    # The create_user function in database.py already handles hashing
    new_user_id = await create_user(user_data.model_dump())
    
    # Get created user to return its details
    created_user_doc = await get_user_by_username(user_data.username) # Renamed
    if not created_user_doc:
        logger.error(f"Failed to retrieve user {user_data.username} after creation.")
        raise HTTPException(
            status_code=500,
            detail="Failed to create user or retrieve after creation"
        )
    
    # Log successful registration before returning AppUser model
    logger.info(f"Successfully registered and retrieved user: {created_user_doc['username']}")
    return AppUser(
        id=str(created_user_doc["_id"]),
        username=created_user_doc["username"],
        email=created_user_doc.get("email"),
        full_name=created_user_doc.get("full_name"),
        created_at=created_user_doc["created_at"],
        last_login=created_user_doc.get("last_login"),
        is_active=created_user_doc["is_active"]
    )

# Data endpoints
@app.post("/upload_file/")
async def upload_file(file: UploadFile, current_user: AppUser = Depends(get_current_active_user)): # Changed to AppUser
    try:
        content = await file.read()
        logger.info("Received file: %s, size: %d bytes", file.filename, len(content))
        
        if len(content) == 0:
            logger.error("Empty file uploaded")
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        
        file_extension = file.filename.split('.')[-1].lower()
        
        if file_extension == 'csv':
            try:
                df = pd.read_csv(io.BytesIO(content), encoding='utf-8')
            except UnicodeDecodeError:
                logger.error("Unicode decode error, trying latin1 encoding")
                df = pd.read_csv(io.BytesIO(content), encoding='latin1')
            except pd.errors.ParserError as e:
                logger.error("CSV parsing error: %s", str(e))
                raise HTTPException(status_code=400, detail=f"Invalid CSV format: {str(e)}")
        
        elif file_extension == 'json':
            try:
                # First, try to read as a standard JSON object/array
                df = pd.read_json(io.BytesIO(content))
            except ValueError as e:
                # If standard parsing fails, try reading as newline-delimited JSON
                # Common errors for NDJSON being read without lines=True include 'Trailing data', 'Extra data'
                # Also, control characters within strings if not properly escaped might cause issues
                # if the file is treated as one giant string.
                if 'Trailing data' in str(e) or 'Extra data' in str(e):
                    try:
                        logger.info("Standard JSON parsing failed due to trailing data, trying as newline-delimited JSON (NDJSON).")
                        df = pd.read_json(io.BytesIO(content), lines=True, encoding='utf-8')
                    except ValueError as e_ndjson:
                        logger.error(f"NDJSON parsing also failed: {str(e_ndjson)}")
                        raise HTTPException(status_code=400, detail=f"Invalid JSON format (tried standard and NDJSON): {str(e_ndjson)}")
                    except Exception as e_general: # Catch other potential errors with lines=True
                        logger.error(f"Error parsing as NDJSON: {str(e_general)}")
                        raise HTTPException(status_code=400, detail=f"Error processing JSON file (NDJSON attempt): {str(e_general)}")
                else: # Other ValueError not indicative of NDJSON
                    logger.error(f"JSON parsing error: {str(e)}")
                raise HTTPException(status_code=400, detail=f"Invalid JSON format: {str(e)}")
            except Exception as e: # Catch-all for other pd.read_json issues
                logger.error(f"Unexpected error reading JSON: {str(e)}")
                raise HTTPException(status_code=400, detail=f"Could not process JSON file: {str(e)}")
        
        elif file_extension == 'xlsx':
            try:
                df = pd.read_excel(io.BytesIO(content))
            except Exception as e:
                logger.error(f"XLSX parsing error: {str(e)}")
                raise HTTPException(status_code=400, detail=f"Invalid XLSX format: {str(e)}")
        
        elif file_extension == 'sql':
            try:
                # For SQL files, we'll read the content as text and return it
                sql_content = content.decode('utf-8')
                return {
                    "sql_content": sql_content,
                    "preview": None,
                    "columns": None,
                    "file_type": "sql"
                }
            except UnicodeDecodeError as e:
                logger.error("SQL file decode error: %s", str(e))
                raise HTTPException(status_code=400, detail="Invalid SQL file encoding")
        
        else:
            logger.error("Unsupported file type: %s", file_extension)
            raise HTTPException(
                status_code=400, 
                detail="Unsupported file type. Please upload a CSV, JSON, XLSX, or SQL file."
            )
        
        if file_extension in ['csv', 'json', 'xlsx']:
            logger.info("File parsed successfully, columns: %s", df.columns.tolist())
            original_df_key = f"{current_user.username}_original" # User-specific key
            df_storage[original_df_key] = df # Store with user-specific key
            return {
                "columns": df.columns.tolist(),
                "preview": df.head().to_dict(orient="records"),
                "file_type": file_extension
            }
    
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error("Unexpected error in upload_file: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")

@app.post("/classify/")
async def classify_column(column: str = Form(...), examples: str = Form(...), current_user: AppUser = Depends(get_current_active_user)): # Changed to AppUser
    try:
        parsed_examples = [tuple(line.split(",")) for line in examples.strip().splitlines()]
        # Validate examples
        for src, tgt in parsed_examples:
            if not src or not tgt:
                logger.error("Invalid example format: %s", examples)
                raise HTTPException(status_code=400, detail="Each example must be 'input,output'")
        serialized = serialize_examples(parsed_examples)
        logger.info("Serialized examples: %s", serialized)
        classification = classify_transformation(serialized)
        logger.info("Classification result: %s", classification)
        valid_classes = ["String-based", "Numerical", "Algorithmic", "General"]
        if classification not in valid_classes:
            logger.error("Invalid classification: %s", classification)
            raise HTTPException(status_code=400, detail=f"Invalid classification: {classification}")
        return {"column": column, "classification": classification}
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error("Error in classify_column: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to classify: {str(e)}")

@app.post("/generate_function/")
async def generate_function(column: str = Form(...), examples: str = Form(...), classification: str = Form(...), current_user: AppUser = Depends(get_current_active_user)): # Changed to AppUser
    try:
        parsed_examples = [tuple(line.split(",")) for line in examples.strip().splitlines()]
        classification = classification.lower()
        logger.info("Generating function for classification: %s", classification)

        if "string" in classification:
            code = generate_string_function(parsed_examples)
        elif "numerical" in classification:
            code = fit_numeric_function(parsed_examples)
        elif "algorithmic" in classification:
            code = generate_algorithmic_function(parsed_examples)
        elif "general" in classification:
            code = generate_general_lookup_function(parsed_examples)
        else:
            logger.warning("Unknown classification: %s", classification)
            code = "# Could not determine transformation class"

        logger.info("Generated code: %s", code[:100])  # Log first 100 chars
        return {"code": code}
    except Exception as e:
        logger.error("Error in generate_function: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Failed to generate function: {str(e)}")

# Pydantic model for DB connection details within the apply payload
class DBInfo(BaseModel):
    host: Optional[str] = None
    port: Optional[str] = None 
    user: Optional[str] = None
    password: Optional[str] = None
    database: Optional[str] = None
    table: Optional[str] = None
    uri: Optional[str] = None # For MongoDB

# Pydantic model for the /apply/ endpoint payload
class ApplyPayload(BaseModel):
    code: str
    selected_column: str
    source_type: Optional[str] = None
    db_info: Optional[DBInfo] = None

@app.post("/apply/")
async def apply_transformation(
    payload: ApplyPayload, # Changed from Form fields to Pydantic model
    current_user: AppUser = Depends(get_current_active_user)
):
    logger.info(f"Apply transformation requested by {current_user.username} for column '{payload.selected_column}' with source type '{payload.source_type}'")
    
    df = None
    original_df_key = f"{current_user.username}_original"
    transformed_df_key = f"{current_user.username}_transformed"

    # Use fields from payload directly
    code_to_execute = payload.code
    column_to_transform = payload.selected_column
    source_type = payload.source_type
    db_connection_info = payload.db_info # This is now a DBInfo object or None

    try:
        if source_type == "file":
            if original_df_key not in df_storage or df_storage[original_df_key] is None:
                raise HTTPException(status_code=400, detail="Original file data not found. Please upload a file first.")
            df = df_storage[original_df_key].copy()
            logger.info(f"Applying transformation to file data for user {current_user.username}")
        
        elif source_type == "mongodb_stored":
            mongo_original_key = f"{current_user.username}_mongodb_original"
            if mongo_original_key not in df_storage or df_storage[mongo_original_key] is None:
                raise HTTPException(status_code=400, detail="Original MongoDB data not found. Please load from MongoDB first.")
            df = df_storage[mongo_original_key].copy()
            logger.info(f"Applying transformation to stored MongoDB data for user {current_user.username}")
            # Ensure _id is dropped if it exists, as transformation functions might not expect it
            # and it can cause issues if the function tries to create a new column with the same name implicitly.
            if '_id' in df.columns:
                 df = df.drop(columns=['_id'], errors='ignore') # Add errors='ignore' for safety

        elif source_type == "database":
            if not db_connection_info or not db_connection_info.database or not db_connection_info.table:
                raise HTTPException(status_code=400, detail="Missing database connection information, database name, or table name for database source.")
            
            logger.info(f"Connecting to database for transformation: DB: {db_connection_info.database}, Table: {db_connection_info.table}")
            conn = None
            cursor = None
            try:
                # get_db_connection expects a dict-like object, DBInfo model should work if fields match
                conn = await get_db_connection(db_connection_info) 
                cursor = conn.cursor(dictionary=True)
                # Safely quote table and database names
                query = f"SELECT * FROM `{db_connection_info.database}`.`{db_connection_info.table}`"
                logger.info(f"Executing query: {query}")
                cursor.execute(query)
                rows = cursor.fetchall()
                if not rows:
                    # Distinguish between empty table and table not found (though MySQL might raise error for not found)
                    logger.warning(f"No data found in table '{db_connection_info.table}' for user {current_user.username}")
                    # Return empty preview instead of 404 if table is valid but empty
                    # raise HTTPException(status_code=404, detail=f"No data found in table '{db_connection_info.table}'.")
                    df = pd.DataFrame() # Create an empty DataFrame
                else:
                    df = pd.DataFrame(rows)
                
                # Store a copy of the original df from DB in df_storage if needed for other operations or revert
                # df_storage[f"{current_user.username}_db_original_{db_connection_info.database}_{db_connection_info.table}"] = df.copy()

            except Error as e:
                logger.error(f"MySQL Database error during /apply/ for user {current_user.username}: {e}")
                raise HTTPException(status_code=500, detail=f"Database connection or query error: {e}")
            finally:
                if cursor: cursor.close()
                if conn and conn.is_connected(): conn.close()
        else:
            valid_sources = ["file", "mongodb_stored", "database"]
            raise HTTPException(status_code=400, detail=f"Invalid source_type: '{source_type}'. Must be one of {valid_sources}.")

        if df is None: # Should only happen if source_type was invalid and not caught, or logic error
            logger.error(f"DataFrame is None after source handling for user {current_user.username}, source_type: {source_type}")
            raise HTTPException(status_code=500, detail="Failed to load data for transformation due to an internal error.")

        # Handle empty DataFrame case gracefully before checking column
        if df.empty:
            logger.info(f"Source data for column '{column_to_transform}' is empty for user {current_user.username}. Applying transformation to empty DataFrame.")
            # If df is empty, applying function might be fine or might error depending on function
            # We'll let apply_function_on_column handle it, it should return an empty df if input is empty.
        elif column_to_transform not in df.columns:
            logger.error(f"Column '{column_to_transform}' not found. Available columns: {df.columns.tolist()} for user {current_user.username}")
            raise HTTPException(status_code=400, detail=f"Column '{column_to_transform}' not found in the dataset. Available columns: {df.columns.tolist()}")

        logger.info(f"Applying generated code to column '{column_to_transform}' for user {current_user.username}")
        
        # Prepare the input series for the transformation function
        input_series = pd.Series(dtype=object) # Default for empty df
        original_dtype = object # Default dtype
        if not df.empty:
            # This check is technically redundant due to the one above, but good for safety.
            if column_to_transform not in df.columns: 
                logger.error(f"Column '{column_to_transform}' unexpectedly not found before series extraction in /apply/ for user {current_user.username}.")
                raise HTTPException(status_code=400, detail=f"Column '{column_to_transform}' missing from data source.")
            original_dtype = df[column_to_transform].dtype
            input_series = df[column_to_transform].copy() # Make a copy
        else: # df is empty
            # If df has columns defined but no rows, try to get the dtype.
            if column_to_transform in df.columns:
                 original_dtype = df[column_to_transform].dtype
            input_series = pd.Series(dtype=original_dtype)


        # apply_function_on_column expects (code_string, series) and returns transformed_series
        # It raises an exception on error.
        error_details = None
        transformed_column_series = pd.Series(dtype=original_dtype) # Initialize with original dtype

        try:
            logger.info(f"Calling tabulax.apply_function_on_column for column '{column_to_transform}' with code.")
            transformed_column_series = apply_function_on_column(code_to_execute, input_series.copy()) # Pass a copy of the series
        except Exception as e:
            logger.error(f"Exception from tabulax.apply_function_on_column for user {current_user.username} on column '{column_to_transform}': {str(e)}", exc_info=True)
            error_details = f"Error during transformation function execution: {str(e)}"
        
        if error_details:
             logger.error(f"Error from tabulax.apply_function_on_column for user {current_user.username} on column '{column_to_transform}': {error_details}")
             raise HTTPException(status_code=400, detail=f"Error applying transformation logic: {error_details}")

        # Create the full transformed DataFrame
        df_transformed = df.copy() # Start with a copy of the original DataFrame
        
        if not df.empty: 
            # If the original df was not empty, assign the transformed series.
            df_transformed[column_to_transform] = transformed_column_series
        elif column_to_transform in df_transformed.columns : # df is empty, but column was defined
            # The transformed_column_series should be an empty Series with the correct dtype.
            df_transformed[column_to_transform] = transformed_column_series
        # If df was empty and column_to_transform was not in df.columns, 
        # df_transformed remains an empty copy. transformed_column_series should be an empty Series.
        # No special handling needed here as df_transformed is already a copy of empty df.
        
        df_storage[transformed_df_key] = df_transformed.copy() # Store the full transformed DataFrame
        
        preview_data = df_transformed.head(100).to_dict(orient='records')
        preview_data_converted = convert_numpy_types(preview_data)
        
        logger.info(f"Transformation successful for user {current_user.username}. Preview generated.")
        return {"message": "Transformation applied successfully", "preview": preview_data_converted}

    except HTTPException as http_exc:
        # Log and re-raise known HTTP exceptions
        logger.warning(f"HTTPException in /apply/ for user {current_user.username}: {http_exc.detail}")
        raise http_exc
    except Error as db_err: # Catch MySQL specific errors if not caught by inner try-except
        logger.error(f"Unhandled MySQL Error in /apply/ for user {current_user.username}: {db_err}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"A database error occurred: {str(db_err)}")
    except Exception as e:
        logger.error(f"Unexpected error in /apply/ for user {current_user.username}: {type(e).__name__} - {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected server error occurred during transformation: {str(e)}")
        
@app.get("/download/")
async def download_transformed(current_user: AppUser = Depends(get_current_active_user)): # Changed to AppUser
    try:
        original_df_key = f"{current_user.username}_original"
        transformed_df_key = f"{current_user.username}_transformed"

        df_to_download = None
        if transformed_df_key in df_storage and df_storage[transformed_df_key] is not None:
            df_to_download = df_storage[transformed_df_key]
            logger.info(f"Found transformed data for user {current_user.username} for download.")
        elif original_df_key in df_storage and df_storage[original_df_key] is not None:
            df_to_download = df_storage[original_df_key]
            logger.info(f"Found original data for user {current_user.username} for download (no transformed data).")
        else:
            logger.error(f"No DataFrame (original or transformed) available for download for user {current_user.username}")
            raise HTTPException(status_code=400, detail="No data available for download. Please upload or load data first.")
        
        csv_buffer = io.StringIO()
        df_to_download.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)
        
        logger.info(f"Returning CSV for download for user {current_user.username}")
        return StreamingResponse(
            io.BytesIO(csv_buffer.getvalue().encode('utf-8')),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=transformed_data.csv"}
        )
    except Exception as e:
        logger.error(f"Error in download_transformed for user {current_user.username}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to download CSV: {str(e)}")
        
        
db_connections = {}

async def get_db_connection(connection_info: MySQLConnectionInfo): # Updated signature
    try:
        # Fields are now accessed directly from the Pydantic model, with type validation
        logger.info(f"Attempting MySQL connection to host: {connection_info.host}:{connection_info.port}, user: {connection_info.user}, db: {connection_info.database or 'N/A'}")
        connection = mysql.connector.connect(
            host=connection_info.host,
            port=connection_info.port,
            user=connection_info.user,
            password=connection_info.password,
            database=connection_info.database if connection_info.database else '' # Use empty string if None for connect
        )
        if connection.is_connected():
            logger.info(f"MySQL connection successful to {connection_info.host}:{connection_info.port}")
            return connection
        else:
            # This case might not be explicitly hit if mysql.connector.connect raises on failure
            logger.error(f"MySQL connection failed for {connection_info.host}:{connection_info.port} - connection.is_connected() returned False.")
            raise HTTPException(status_code=500, detail="Failed to establish an active database connection (is_connected() is false).")

    except mysql.connector.Error as db_err: # More specific MySQL errors
        err_msg = str(db_err)
        logger.error(f"MySQL connection error for {connection_info.host}:{connection_info.port} - User: {connection_info.user}. Error: {err_msg}", exc_info=True)
        
        if "Access denied" in err_msg: # Error 1045
            raise HTTPException(status_code=401, detail=f"Access denied for user '{connection_info.user}'. Please check credentials.")
        elif "Unknown database" in err_msg and connection_info.database: # Error 1049
            raise HTTPException(status_code=400, detail=f"Unknown database '{connection_info.database}'.")
        elif "Can't connect to MySQL server" in err_msg: # Error 2003 / 2005
             raise HTTPException(status_code=503, detail=f"Cannot connect to MySQL server at {connection_info.host}:{connection_info.port}. Server might be down or network issues.")
        else: # Other MySQL errors
            raise HTTPException(status_code=400, detail=f"Database connection error: {err_msg}")
    except Exception as e: # Catch any other unexpected errors during connection setup
        logger.error(f"Unexpected error in get_db_connection to {connection_info.host}:{connection_info.port}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected server error occurred while trying to connect to the database: {str(e)}")

@app.post("/connect_database/")
async def connect_database(conn_info_model: MySQLConnectionInfo, current_user: AppUser = Depends(get_current_active_user)):
    connection = None
    cursor = None
    try:
        logger.info(f"User {current_user.username} attempting to connect to MySQL host: {conn_info_model.host}")
        # Pass the Pydantic model directly; database field in conn_info_model can be None here
        cloned_conn_info_for_listing_dbs = conn_info_model.copy(update={"database": None}) # Ensure we connect without a specific DB to list all
        connection = await get_db_connection(cloned_conn_info_for_listing_dbs)
        
        cursor = connection.cursor()
        
        # Get databases
        cursor.execute("SHOW DATABASES")
        system_databases = ['information_schema', 'mysql', 'performance_schema', 'sys', 'tmp'] # Common system DBs
        databases = [db[0] for db in cursor.fetchall() if db[0].lower() not in system_databases]
        
        logger.info(f"Successfully connected and fetched databases for user {current_user.username}: {databases}")
        return {"databases": databases}
    except HTTPException as he:
        raise he # Re-raise HTTPExceptions from get_db_connection or validation
    except Error as e: # Catch MySQL specific errors not caught by get_db_connection (e.g., during SHOW DATABASES)
        logger.error(f"MySQL Error in /connect_database/ for user {current_user.username}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"A MySQL error occurred while listing databases: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in /connect_database/ for user {current_user.username}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected server error occurred: {str(e)}")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

@app.post("/get_tables/")
async def get_tables(conn_info_model: MySQLConnectionInfo, current_user: AppUser = Depends(get_current_active_user)):
    connection = None
    cursor = None
    try:
        if not conn_info_model.database:
            logger.error(f"User {current_user.username} attempted to list tables without specifying a database for host {conn_info_model.host}.")
            raise HTTPException(status_code=400, detail="Database name must be provided in connection details to list tables.")
        
        logger.info(f"User {current_user.username} attempting to get tables from DB '{conn_info_model.database}' on host {conn_info_model.host}")
        connection = await get_db_connection(conn_info_model) # conn_info_model includes .database
        cursor = connection.cursor()
        
        # mysql.connector.connect handles setting the DB context if database is provided in conn_info_model
        cursor.execute("SHOW TABLES")
        tables = [table[0] for table in cursor.fetchall()]
        
        logger.info(f"Successfully fetched tables for user {current_user.username} from DB '{conn_info_model.database}': {tables}")
        return {"tables": tables}
    except HTTPException as he:
        raise he
    except Error as e:
        logger.error(f"MySQL Error in /get_tables/ for user {current_user.username}, DB '{conn_info_model.database}': {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"A MySQL error occurred while listing tables: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in /get_tables/ for user {current_user.username}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected server error occurred: {str(e)}")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

@app.post("/get_columns/")
async def get_columns(conn_info_model: MySQLConnectionInfo, table_name: str = Query(..., description="The name of the table to fetch columns and preview data from"), current_user: AppUser = Depends(get_current_active_user)):
    connection = None
    cursor = None
    try:
        if not conn_info_model.database:
            logger.error(f"User {current_user.username} attempted to get columns without specifying a database for host {conn_info_model.host}, table '{table_name}'.")
            raise HTTPException(status_code=400, detail="Database name must be provided in connection details.")
        if not table_name: # Should be caught by Query(...)
            raise HTTPException(status_code=400, detail="Table name must be provided.")

        logger.info(f"User {current_user.username} attempting to get columns for table '{table_name}' in DB '{conn_info_model.database}' on host {conn_info_model.host}")
        connection = await get_db_connection(conn_info_model)
        cursor = connection.cursor(dictionary=True) # Important for easy conversion to dict
        
        # Safely quote table name. Database context is set by the connection.
        # DESCRIBE is fine with backticks if table name has special chars, though not strictly needed for simple names.
        query_cols = f"DESCRIBE `{conn_info_model.database}`.`{table_name}`"
        logger.info(f"Executing query for columns: {query_cols} for user {current_user.username}")
        cursor.execute(query_cols)
        columns_desc = cursor.fetchall()
        columns = [col['Field'] for col in columns_desc]
        
        # Get preview data
        query_preview = f"SELECT * FROM `{conn_info_model.database}`.`{table_name}` LIMIT 5"
        logger.info(f"Executing query for preview: {query_preview} for user {current_user.username}")
        cursor.execute(query_preview)
        preview_raw = cursor.fetchall()
        preview = convert_numpy_types(preview_raw) # Use existing numpy converter
        
        logger.info(f"Successfully fetched columns and preview for user {current_user.username} from table '{conn_info_model.database}'.'{table_name}'")
        return {"columns": columns, "preview": preview}
    except HTTPException as he:
        raise he
    except Error as e:
        logger.error(f"MySQL Error in /get_columns/ for user {current_user.username}, table '{conn_info_model.database}'.'{table_name}': {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"A MySQL error occurred while fetching column data: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in /get_columns/ for user {current_user.username}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected server error occurred: {str(e)}")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

# Pydantic model for the /apply_to_database/ endpoint payload
class ApplyToSQLPayload(BaseModel):
    connection_details: MySQLConnectionInfo # host, user, pass, port, database (must be set by client)
    table_name: str
    column_to_transform: str
    code: str

@app.post("/apply_to_database/")
async def apply_to_database(
    payload: ApplyToSQLPayload, # New way
    current_user: AppUser = Depends(get_current_active_user) 
):
    connection = None # Initialize
    cursor = None # Initialize
    try:
        conn_model = payload.connection_details
        table = payload.table_name
        column_to_transform_db = payload.column_to_transform # Renamed to avoid clash with `columns` list
        transformation_code_db = payload.code # Renamed for clarity

        if not conn_model.database:
            raise HTTPException(status_code=400, detail="Database name missing in connection details for applying to database.")
        if not table: # Should be validated by Pydantic if table_name is not Optional
            raise HTTPException(status_code=400, detail="Table name is required for applying to database.")

        logger.info(f"User {current_user.username} attempting to apply transformation to SQL DB. Host: {conn_model.host}, DB: {conn_model.database}, Table: {table}, Column: {column_to_transform_db}")
        
        connection = await get_db_connection(conn_model) # New way, conn_model already includes .database
        cursor = connection.cursor(dictionary=True)

        # Step 1: Fetch original data and schema
        fetch_query = f"SELECT * FROM `{conn_model.database}`.`{table}`"
        logger.info(f"Executing query to fetch original data: {fetch_query} for user {current_user.username}")
        cursor.execute(fetch_query)
        original_data = cursor.fetchall()
        if not original_data:
            logger.warning(f"No data found in table '{conn_model.database}'.'{table}'. Transformation will be applied to an empty dataset if columns exist.")
            # If table is truly empty (no rows), df will be empty.
            # We need to fetch schema to create df with columns if table is empty.
            # However, if table doesn't exist, SELECT * will error out (handled by Error catch).
            pass # df will be created from empty list or schema next.

        # Simpler: pandas can create DataFrame from list of dicts (original_data)
        # If original_data is empty, df will be empty but may or may not have columns.
        # If it has columns (e.g. from a previous query if cursor was reused, not the case here),
        # or if original_data was [{}] (empty row), then df.columns will exist.
        df = pd.DataFrame(original_data if original_data else [])

        if column_to_transform_db not in df.columns and not df.empty: # Only raise if df is not empty but column is missing
            logger.error(f"Column '{column_to_transform_db}' not found in table '{table}' for user {current_user.username}. Available: {df.columns.tolist()}")
            raise HTTPException(status_code=400, detail=f"Column '{column_to_transform_db}' not found in table '{table}'.")
        elif df.empty and not original_data : # Table is empty, no rows.
             # If the table is genuinely empty, we can't transform a column that doesn't effectively exist with data.
             # However, if apply_function_on_column can handle an empty series, we might proceed.
             # Let's check if the column *would* exist based on schema if we had fetched it separately.
             # For now, if table is empty, applying transformation to a column is a no-op or error.
             # Let's return a message indicating nothing was changed.
             # OR: if the column itself is part of the schema, proceed with an empty series.
             # This requires fetching the schema as above. Let's assume for now `apply_function_on_column`
             # can handle an empty series if df[column_to_transform_db] results in one.
            logger.info(f"Table '{conn_model.database}'.'{table}' is empty. Transformation on column '{column_to_transform_db}' will result in no changes if column exists in schema, or error if not.")
            # If df is empty, df[column_to_transform_db] will raise KeyError unless columns were predefined.
            # To robustly handle empty tables, we MUST get columns from schema.
            describe_query = f"DESCRIBE `{conn_model.database}`.`{table}`"
            cursor.execute(describe_query)
            schema_info_for_empty = cursor.fetchall()
            df_cols_for_empty = [col['Field'] for col in schema_info_for_empty]
            if column_to_transform_db not in df_cols_for_empty:
                logger.error(f"Column '{column_to_transform_db}' not found in schema of empty table '{table}' for user {current_user.username}.")
                raise HTTPException(status_code=400, detail=f"Column '{column_to_transform_db}' not found in schema of empty table '{table}'.")
            # If we are here, table is empty, but column exists in schema. df is empty.
            # df_to_transform will also be empty. apply_function_on_column will get an empty series.
            # The rest of the logic (temp table etc) should handle an empty df.

        # Apply transformation
        df_to_transform = df.copy()
        if not df_to_transform.empty: # Only apply if there's data
            original_series_dtype_db = df_to_transform[column_to_transform_db].dtype
            transformed_series_sql = pd.Series(dtype=original_series_dtype_db)
            error_details_sql = None
            try:
                logger.info(f"Calling tabulax.apply_function_on_column for SQL DB update, column '{column_to_transform_db}'. User: {current_user.username}")
                input_series_sql = df_to_transform[column_to_transform_db].copy()
                transformed_series_sql = apply_function_on_column(transformation_code_db, input_series_sql)
                df_to_transform[column_to_transform_db] = transformed_series_sql
            except Exception as e:
                logger.error(f"Exception from tabulax.apply_function_on_column during SQL DB update for column '{column_to_transform_db}', user {current_user.username}: {str(e)}", exc_info=True)
                error_details_sql = f"Error during transformation for SQL Database: {str(e)}"
            
            if error_details_sql:
                if connection: connection.rollback()
                raise HTTPException(status_code=400, detail=error_details_sql)
        else: # df_to_transform is empty
            logger.info(f"Source table '{conn_model.database}'.'{table}' is empty. No transformation applied. User: {current_user.username}")
            # No actual data transformation to do. The temp table logic might still run but insert 0 rows.

        # Create a temporary table with the transformed data (or schema if empty)
        temp_table_name = f"{table}_temp_transform" # Keep it simple, ensure cleanup
        
        # Drop temporary table if it exists from a previous failed run
        cursor.execute(f"DROP TABLE IF EXISTS `{conn_model.database}`.`{temp_table_name}`")
        
        # Create temporary table with same schema as original table
        # Using CREATE TABLE LIKE ensures all constraints, indexes etc. are copied.
        create_table_query = f"CREATE TABLE `{conn_model.database}`.`{temp_table_name}` LIKE `{conn_model.database}`.`{table}`"
        logger.info(f"Executing query to create temp table: {create_table_query} for user {current_user.username}")
        cursor.execute(create_table_query)
        
        # Insert transformed data (if any)
        if not df_to_transform.empty:
            # df_to_transform.columns should match the schema if created properly
            placeholders = ', '.join(['%s'] * len(df_to_transform.columns))
            insert_query = f"INSERT INTO `{conn_model.database}`.`{temp_table_name}` ({', '.join([f'`{col}`' for col in df_to_transform.columns])}) VALUES ({placeholders})"
            
            # Convert DataFrame to list of tuples for insertion, handling NaT/NaN for SQL
            values_to_insert = []
            for row_tuple in df_to_transform.to_records(index=False):
                # Apply convert_numpy_types to each value in the tuple
                values_to_insert.append(tuple(convert_numpy_types(val) for val in row_tuple))

            if values_to_insert: # Only execute if there are rows to insert
                logger.info(f"Inserting {len(values_to_insert)} rows into temp table {temp_table_name} for user {current_user.username}")
                cursor.executemany(insert_query, values_to_insert)
            else:
                logger.info(f"Transformed DataFrame is empty (or all NaN rows). No data inserted into temp table {temp_table_name}. User: {current_user.username}")
        else:
            logger.info(f"Original table was empty, so no data to insert into temp table {temp_table_name}. User: {current_user.username}")

        
        # Rename tables to swap them: original -> backup, temp -> original, drop backup
        backup_table_name = f"{table}_backup_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        
        logger.info(f"Starting table rename process: Original='{table}', Temp='{temp_table_name}', Backup='{backup_table_name}'. User: {current_user.username}")
        cursor.execute(f"DROP TABLE IF EXISTS `{conn_model.database}`.`{backup_table_name}`") 
        cursor.execute(f"ALTER TABLE `{conn_model.database}`.`{table}` RENAME TO `{conn_model.database}`.`{backup_table_name}`")
        logger.info(f"Renamed original table '{table}' to '{backup_table_name}'. User: {current_user.username}")
        cursor.execute(f"ALTER TABLE `{conn_model.database}`.`{temp_table_name}` RENAME TO `{conn_model.database}`.`{table}`")
        logger.info(f"Renamed temp table '{temp_table_name}' to '{table}'. User: {current_user.username}")
        cursor.execute(f"DROP TABLE `{conn_model.database}`.`{backup_table_name}`") 
        logger.info(f"Dropped backup table '{backup_table_name}'. User: {current_user.username}")
        
        connection.commit()
        logger.info(f"Database update successful for table '{conn_model.database}'.'{table}'. User: {current_user.username}")
        return {"message": "Database updated successfully"}
        
    except HTTPException as he: # Re-raise application-level HTTP exceptions
        if connection: connection.rollback() # Rollback on any HTTPException during the process
        raise he
    except Error as e: # Catch MySQL specific errors
        logger.error(f"MySQL Error in /apply_to_database/ for user {current_user.username}, table '{payload.table_name}': {str(e)}", exc_info=True)
        if connection:
            connection.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update database due to a MySQL error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in /apply_to_database/ for user {current_user.username}: {str(e)}", exc_info=True)
        if connection:
            connection.rollback()
        raise HTTPException(status_code=500, detail=f"An unexpected server error occurred while updating database: {str(e)}")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

# Function to create access token (was missing)
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# Helper function to get a MongoDB client (used by new endpoints)
async def get_mongo_client(conn_info: MongoConnectionInfo):
    try:
        client = motor.motor_asyncio.AsyncIOMotorClient(conn_info.uri)
        # Test connection by listing server info - this will raise an exception on failure
        await client.server_info() 
        return client
    except Exception as e:
        logger.error(f"MongoDB connection/authentication error: {e}")
        raise HTTPException(status_code=400, detail=f"MongoDB connection error: {e}")

@app.post("/connect_mongo/")
async def connect_mongo(conn_info: MongoConnectionInfo, current_user: AppUser = Depends(get_current_active_user)):
    client = None
    try:
        client = await get_mongo_client(conn_info)
        databases = await client.list_database_names()
        # Filter out admin/config/local databases if desired, but let's show all for now
        return {"databases": databases}
    except HTTPException as e: # Re-raise HTTPExceptions from get_mongo_client
        raise e
    except Exception as e:
        logger.error(f"Error listing MongoDB databases: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list MongoDB databases: {str(e)}")
    finally:
        if client:
            client.close()

@app.post("/get_mongo_collections/")
async def get_mongo_collections(conn_info: MongoConnectionInfo, database_name: str = Query(...), current_user: AppUser = Depends(get_current_active_user)):
    client = None
    try:
        client = await get_mongo_client(conn_info)
        db = client[database_name]
        collections = await db.list_collection_names()
        return {"collections": collections}
    except HTTPException as e: # Re-raise HTTPExceptions
        raise e
    except Exception as e:
        logger.error(f"Error listing MongoDB collections in {database_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list MongoDB collections: {str(e)}")
    finally:
        if client:
            client.close()

@app.post("/get_mongo_data/")
async def get_mongo_data(conn_info: MongoConnectionInfo, database_name: str = Query(...), collection_name: str = Query(...), current_user: AppUser = Depends(get_current_active_user)):
    client = None
    try:
        client = await get_mongo_client(conn_info)
        db = client[database_name]
        collection = db[collection_name]

        # Fetch a sample of documents for preview and schema inference (e.g., first 100)
        # For MongoDB, _id is an ObjectId, convert it to string for JSON serialization
        preview_cursor = collection.find().limit(100)
        preview_data_raw = await preview_cursor.to_list(length=100)
        
        preview_data = []
        all_keys = set()
        for doc_raw in preview_data_raw:
            doc = {}
            for key, value in doc_raw.items():
                if isinstance(value, ObjectId):
                    doc[key] = str(value)
                elif isinstance(value, (list, dict)):
                    # For simplicity in DataFrame conversion, we can JSON stringify complex types
                    # Or handle them as-is if pandas can manage.
                    # Let's try to keep them as-is for now, pandas might handle them.
                    doc[key] = value 
                else:
                    doc[key] = value
                all_keys.add(key)
            preview_data.append(doc)

        if not preview_data:
            return {"columns": [], "preview": [], "file_type": "mongodb"}

        # Convert to DataFrame to leverage existing logic and for consistency, though it's an extra step
        # This also helps in handling missing keys in some documents (pandas fills with NaN)
        df = pd.DataFrame(preview_data)
        
        # Ensure all collected keys are columns, even if some are all NaN in the preview
        # (e.g. a key appears only in document 101 and not in the first 100)
        # For now, columns will be from the df, which is based on the preview sample.
        columns = df.columns.tolist()

        # Store this DataFrame for potential transformation (similar to df_storage["original"] for files)
        # We might need a different storage mechanism or keying for DB sources if we want to support multiple simultaneously.
        # For now, let's use a specific key for MongoDB data.
        mongo_original_key = f"{current_user.username}_mongodb_original"
        df_storage[mongo_original_key] = df 

        return {
            "columns": columns,
            "preview": convert_numpy_types(df.head().to_dict(orient="records")), # Use existing numpy converter
            "file_type": "mongodb"
        }

    except HTTPException as e: # Re-raise HTTPExceptions
        raise e
    except Exception as e:
        logger.error(f"Error fetching MongoDB data from {database_name}.{collection_name}: {e}")
        # Print full traceback for detailed debugging of MongoDB data fetching/processing
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch MongoDB data: {str(e)}")
    finally:
        if client:
            client.close()

@app.post("/apply_to_mongodb/")
async def apply_to_mongodb(
    conn_info_json: str = Form(...), # MongoConnectionInfo as a JSON string
    database_name: str = Form(...),
    collection_name: str = Form(...),
    column_to_transform: str = Form(...),
    transformation_code: str = Form(...),
    current_user: AppUser = Depends(get_current_active_user)
):
    client = None
    try:
        # Deserialize conn_info_json back to Pydantic model
        conn_info = MongoConnectionInfo.parse_raw(conn_info_json)
        client = await get_mongo_client(conn_info)
        db = client[database_name]
        collection = db[collection_name]

        documents_cursor = collection.find()
        original_documents = await documents_cursor.to_list(length=None) 

        if not original_documents:
            return {"message": "No documents found to transform."}

        # Prepare data for DataFrame, ensuring _id is preserved correctly
        data_for_df = []
        for doc in original_documents:
            d = {}
            for key, value in doc.items():
                # Keep original _id type for matching, but convert for df if it was stringified by /get_mongo_data/
                # However, for this direct operation, we should rely on the original doc's _id.
                d[key] = str(value) if isinstance(value, ObjectId) else value
            data_for_df.append(d)
        
        df = pd.DataFrame(data_for_df)

        if column_to_transform not in df.columns:
            raise HTTPException(status_code=400, detail=f"Column '{column_to_transform}' not found.")

        # Apply transformation
        # apply_function_on_column expects (code_string, series) and returns transformed_series.
        # It raises an exception on error.
        # df_transformed, error_details = apply_function_on_column(
        #     df_copy_for_transform,  # This was incorrect, should be code and series
        #     column_to_transform,    # This was incorrect
        #     transformation_code
        # )

        # if error_details:
        #     logger.error(f"Error applying transformation function for MongoDB update: {error_details}")
        #     raise HTTPException(status_code=400, detail=f"Error applying transformation logic for MongoDB: {error_details}")
        
        # df_transformed now holds the dataframe with the transformed column.
        # Corrected approach:
        df_to_transform = df.copy() # Work on a copy
        transformed_series = pd.Series(dtype=df_to_transform[column_to_transform].dtype)
        error_details_mongo = None

        try:
            logger.info(f"Calling tabulax.apply_function_on_column for MongoDB update, column '{column_to_transform}'.")
            # Ensure the input series is of a type expected by the transformation function (e.g., string)
            # The original apply_to_database cast to str: df[column].astype(str)
            # Let's be cautious and cast to string for consistency if it's a common expectation for tabulax functions
            # input_series_mongo = df_to_transform[column_to_transform].astype(str) # Removed for consistency
            input_series_mongo = df_to_transform[column_to_transform].copy() # Use a copy
            transformed_series = apply_function_on_column(transformation_code, input_series_mongo)
            df_to_transform[column_to_transform] = transformed_series
        except Exception as e:
            logger.error(f"Exception from tabulax.apply_function_on_column during MongoDB update for column '{column_to_transform}': {str(e)}", exc_info=True)
            error_details_mongo = f"Error during transformation for MongoDB: {str(e)}"
        
        if error_details_mongo:
            raise HTTPException(status_code=400, detail=error_details_mongo)
        
        # df_to_transform now contains the modified column

        # Perform bulk update
        operations = []
        for i, original_doc in enumerate(original_documents):
            # original_doc_id will have its original type (ObjectId)
            original_doc_id = original_doc['_id'] 
            
            # Get the transformed value from df_transformed using the same index
            if i < len(df_to_transform) and column_to_transform in df_to_transform.columns:
                transformed_value = df_to_transform.at[i, column_to_transform]
                # Convert transformed value to a type storable in MongoDB
                storable_value = convert_numpy_types(transformed_value)
            
                operations.append(
                    UpdateOne( # <-- Changed from motor.motor_asyncio.UpdateOne
                        {"_id": original_doc_id},
                        {"$set": {column_to_transform: storable_value}}
                    )
                )
            else:
                logger.warning(f"Could not find transformed value for document index {i}, _id {original_doc_id} (column: {column_to_transform}). Skipping update for this document.")


        if not operations:
            # This could happen if df_transformed was empty or column_to_transform was missing in df_transformed for all rows
            logger.info(f"No update operations prepared for collection {collection_name}. This might be due to empty source or issues in accessing transformed data.")
            # Depending on desired behavior, we might return a specific message or just proceed (bulk_write on empty list is a no-op)
            # For now, let it proceed, result.modified_count will be 0.
            pass


        result = await collection.bulk_write(operations)
        logger.info(f"MongoDB bulk write result for {collection_name}: Matched: {result.matched_count}, Modified: {result.modified_count}, Upserted: {result.upserted_count}")
        return {
            "message": f"Updated {result.modified_count} documents in {collection_name}. Matched: {result.matched_count}."
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error applying transformation to MongoDB: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to apply transformation to MongoDB: {str(e)}")
    finally:
        if client:
            client.close()

# Add other MongoDB related endpoints here in subsequent steps...
