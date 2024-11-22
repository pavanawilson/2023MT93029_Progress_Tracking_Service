import argparse
from flask import Flask, request, jsonify
import psycopg2
import requests
import jwt
from jwt.algorithms import RSAAlgorithm
from psycopg2.extras import RealDictCursor
import warnings
import logging

logger = logging.getLogger('progress_tracking_app')
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()

# Create a formatter and set it for the console handler
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)

# Add the console handler to the logger
logger.addHandler(console_handler)

app = Flask(__name__)

warnings.filterwarnings('ignore', category=UserWarning, message="This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.")

# Global variables to store the token and its expiration time
access_token = None
token_expiration_time = 0

# Auth0 settings
AUTH0_DOMAIN = "dev-xf7eb30rgaz2rvse.us.auth0.com"
CLIENT_ID = "sZp4AQgp95rIMgcpKoXLuzZtqNM72j2e"
CLIENT_SECRET = "ufkpj_72QmMvLUWKhLheZiPrgnr5ZjqQfr5qLowhY3e6VZnVUkwwm3rQuUrNZUlu"

USER_SVC_BASE_URL = None

db_config = {
    "dbname": "fitnessdb",
    "user": "fitnessdb_owner",
    "password": "zUkQGO3BXec2",
    "host": "ep-winter-block-a5pb6mh3.us-east-2.aws.neon.tech",
    "port": "5432"
}

class InvalidTokenException(Exception):
    pass

class ExpiredTokenException(Exception):
    pass

class MissingTokenException(Exception):
    pass

def initialize_parameters(args : argparse.Namespace):
    global USER_SVC_BASE_URL
    USER_SVC_BASE_URL = str(args.user_svc_base_url).rstrip("/")
    logger.info("User service base url intialized with: " + USER_SVC_BASE_URL)

def get_public_key(token, audience):
    try:
        # The public key URL for validating JWT
        url = f'https://{AUTH0_DOMAIN}/.well-known/jwks.json'
        response = requests.get(url)
        jwks = response.json()
        # Decode the JWT to get the header
        unverified_header = jwt.get_unverified_header(token)
        if unverified_header is None:
            raise Exception("Invalid token")

        rsa_key = {}
        for key in jwks['keys']:
            if key['kid'] == unverified_header['kid']:
                rsa_key = {
                    'kty': key['kty'],
                    'kid': key['kid'],
                    'use': key['use'],
                    'n': key['n'],
                    'e': key['e']
                }
                break

        if rsa_key:
            return RSAAlgorithm.from_jwk(rsa_key)
        else:
            raise Exception("Unable to find appropriate key")
    except jwt.ExpiredSignatureError:
        raise ExpiredTokenException("Token has expired")
    except jwt.InvalidTokenError:
        raise InvalidTokenException("Invalid token")

def validate_token(request, audience):
        # Extract the token from the Authorization header
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        logger.error("Authorization header missing for URL: " + audience )
        raise MissingTokenException("Authorization header missing")

    # Expecting token in format "Bearer <token>"
    try:
        token = auth_header.split(" ")[1]
    except IndexError:
        logger.error("Token format invalid for URL: " + audience )
        raise InvalidTokenException("Token format invalid")
    
    # Decode the token
    try:
        # Fetch the public key in PEM format
        public_key = get_public_key(token, audience)

        # Decode the JWT with the PEM-formatted public key
        decoded_token = jwt.decode(token, public_key, algorithms="RS256", audience=audience)
        logger.info("Token decoded")
        return decoded_token
    except jwt.ExpiredSignatureError:
        logger.error("Token has expired for URL: " + audience )
        raise ExpiredTokenException("Token has expired")
    except jwt.InvalidTokenError:
        logger.error("Invalid token for URL: " + audience )
        raise InvalidTokenException("Invalid token for URL: " + audience )
    
            
def get_db_connection():
    try:
        conn = psycopg2.connect(**db_config)
        logger.info("Connected to Neon DB successfully")
        return conn
    except Exception as e:
        logger.error("Error connecting to Neon DB: "+ e )

def validate_user(user_id):
    # Validate the user by calling the User Service endpoint
    try:
        validation_url = f"{USER_SVC_BASE_URL}/api/users/validate/{user_id}"
        logger.info(validation_url)
        validation_response = requests.get(validation_url)
        if validation_response.status_code == 200 and validation_response.json().get("valid") == True:
            logger.info("Valid User")
            return validation_response.json().get("valid")
        else:
            # User validation failed
            return validation_response.json().get("valid")
    except requests.exceptions.RequestException as e:
        # Handle errors in making the validation request
        return False
    
@app.route('/api/progress/<user_id>', methods=['GET'])
def get_user_progress(user_id):
    logger.info("Get user progress API call")
    #Extract the token and validate
    audience = "http://127.0.0.1:5000/api/progress/{user_id}"
    try:
        validate_token(request, audience)
        conn = get_db_connection()
        cursor = conn.cursor()
    
        cursor.execute("""
            SELECT * FROM progress_logs WHERE user_id = %s;
            """, (user_id,))
        logs = cursor.fetchall()
    
        progress_data = []
        for log in logs:
            progress_data.append({
                "log_id": log[0],
                "user_id": log[1],
                "date": log[2],
                "weight_kg": log[3],
                "workout_done": log[4],
                "calories_burned": log[5]
            })
    
        cursor.close()
        conn.close()
        return jsonify({"progress_logs": progress_data})
    except MissingTokenException as e:
            return jsonify({"message": "Authorization header missing"}), 401
    except ExpiredTokenException as e:
        return jsonify({"message": "Token has expired"}), 401
    except InvalidTokenException as e:
        return jsonify({"message": "Invalid token"}), 401
    except Exception as e:
        return jsonify({"message": "Error validating token "+ str(e)}), 401 
    
    
@app.route('/api/progress/summary/<user_id>', methods=['GET'])
def get_progress_summary(user_id):
    logger.info("Get user progress summary API call")
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT AVG(weight_kg), AVG(calories_burned) FROM progress_logs WHERE user_id = %s;
    """, (user_id,))
    summary = cursor.fetchone()
    
    cursor.close()
    conn.close()
   
    return jsonify({
        "user_id": user_id,
        "average_weight": summary[0],
        "average_calories_burned": summary[1]
    })
  
    
@app.route('/api/progress/log', methods=['POST'])
def log_progress():
    logger.info("Log user progress API call")
    #Extract the token and validate
    audience = "http://127.0.0.1:5000/api/progress/log"
    try:
        validate_token(request, audience)
    
        # Parse the JSON data from the request
        data = request.get_json()
        if not data:
            logger.error("Invalid or missing JSON data")
            return jsonify({"error": "Invalid or missing JSON data"}), 400

        # Extract required fields
        user_id = data.get('user_id')
        date_logged = data.get('date')
        weight_kg = data.get('weight_kg')
        workout_done = data.get('workout_done')
        calories_burned = data.get('calories_burned')

        # Validate required fields
        if not all([user_id, date_logged, weight_kg, workout_done, calories_burned]):
            logger.error("All fields required to be filled for logging progress")
            return jsonify({"error": "All fields (user_id, date, weight_kg, workout_done, calories_burned) are required"}), 400
        valid_user_response =  validate_user(user_id)

        if valid_user_response:
            try:
                # Connect to the database
                conn = get_db_connection()
                cursor = conn.cursor(cursor_factory=RealDictCursor)

                # Insert data into the progress_logs table
                cursor.execute("""
                INSERT INTO progress_logs (user_id, date, weight_kg, workout_done, calories_burned)
                VALUES (%s, %s, %s, %s, %s) RETURNING log_id;
                """, (user_id, date_logged, weight_kg, workout_done, calories_burned))

                # Get the ID of the newly inserted row
                progress_id = cursor.fetchone()['log_id']

                # Commit the transaction
                conn.commit()
                logger.info("Progress logged successfully for log_id: " + str(progress_id))
                # Return a success response
                return jsonify({"message": "Progress logged successfully", "id": progress_id}), 201

            except Exception as e:
                conn.rollback()
                logger.error("Error logging progress: " + {str(e)} )
                return jsonify({"error": str(e)}), 500
            finally:
                cursor.close()
                conn.close()
        else:
            logger.error("Invalid userid")
            return jsonify({"message": "Error in validating userid or user does not exist"}), 400
    except MissingTokenException as e:
        return jsonify({"message": "Authorization header missing"}), 401
    except ExpiredTokenException as e:
        return jsonify({"message": "Token has expired"}), 401
    except InvalidTokenException as e:
        return jsonify({"message": "Invalid token"}), 401
    except Exception as e:
        return jsonify({"message": "Error validating token "+ str(e)}), 401 
    
        
@app.route('/api/progress/log/<log_id>', methods=['PUT'])
def update_progress_log(log_id):
    logger.info("Update user progress API call")
    #Extract the token and validate
    audience = "http://127.0.0.1:5000/api/progress/log/{log_id}"
    try:
        validate_token(request, audience)
    
        data = request.json
        conn = get_db_connection()
        cursor = conn.cursor()
    
        try:
            # Update query
            cursor.execute("""
                UPDATE progress_logs 
                SET weight_kg = %s, workout_done = %s, calories_burned = %s
                WHERE log_id = %s
                RETURNING *;
            """, ( data['weight_kg'], data['workout_done'], data['calories_burned'], log_id))
        
            updated_row = cursor.fetchone()
            conn.commit()

            if updated_row:
                logger.info("Progress log updated for log_id: " + log_id)
                return jsonify({"message": "Progress log updated", "updated_log": updated_row}), 200
            else:
                logger.error("Log entry not found for log_id: " + log_id)
                return jsonify({"error": "Log entry not found"}), 404
        except Exception as e:
            conn.rollback()
            logger.error("Error in log update: " + str(e) )
            return jsonify({"error": str(e)}), 500      
        finally:
            cursor.close()
            conn.close()
    except MissingTokenException as e:
        return jsonify({"message": "Authorization header missing"}), 401
    except ExpiredTokenException as e:
        return jsonify({"message": "Token has expired"}), 401
    except InvalidTokenException as e:
        return jsonify({"message": "Invalid token"}), 401
    except Exception as e:
        return jsonify({"message": "Error validating token "+ str(e)}), 401 
    
@app.route('/api/progress/log/<log_id>', methods=['DELETE'])
def delete_progress_log(log_id):
    logger.info("Delete user progress API call")
    #Extract the token and validate
    audience = "http://127.0.0.1:5000/api/progress/log/{log_id}"
    try:
        validate_token(request, audience)
    
        conn = get_db_connection()
        cursor = conn.cursor()
    
        try:
            # Delete query
            cursor.execute("""
                DELETE FROM progress_logs 
                WHERE log_id = %s 
                RETURNING log_id;
            """, (log_id,))
        
            deleted_row = cursor.fetchone()
            conn.commit()

            if deleted_row:
                logger.info("Progress log deleted for log_id: " + log_id)
                return jsonify({"message": "Progress log deleted", "deleted_log_id": deleted_row[0]}), 200
            else:
                logger.error("Log entry not found for log_id: " + log_id)
                return jsonify({"error": "Log entry not found"}), 404
            
        except Exception as e:
            conn.rollback()
            logger.error("Error deleting log: " + str(e))
            return jsonify({"error": str(e)}), 500
        finally:
            cursor.close()
            conn.close()
    except MissingTokenException as e:
        return jsonify({"message": "Authorization header missing"}), 401
    except ExpiredTokenException as e:
        return jsonify({"message": "Token has expired"}), 401
    except InvalidTokenException as e:
        return jsonify({"message": "Invalid token"}), 401
    except Exception as e:
        return jsonify({"message": "Error validating token "+ str(e)}), 401 

@app.route('/api/progress/user/<user_id>/logs', methods=['DELETE'])
def delete_all_logs_for_user(user_id):
    logger.info("Delete all logs for a user API call")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Delete query
        cursor.execute("""
        DELETE FROM progress_logs 
        WHERE user_id = %s
        RETURNING user_id;
        """, (user_id,))
        
        deleted_rows = cursor.rowcount  # Number of deleted rows
        conn.commit()
            
        if deleted_rows > 0:
            logger.info("All progress logs deleted for userid: " + user_id)
            return jsonify({
                "message": f"All progress logs for user deleted",
                "deleted_log_count": deleted_rows
            }), 200
        else:
            logger.error("No logs found for userid: " + user_id)
            return jsonify({"error": "No logs found for the given user_id"}), 404
    except Exception as e:
        conn.rollback()
        logger.error("Error deleting logs: " + str(e))
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()
        
if __name__ == '__main__':
    from waitress import serve
    parser = argparse.ArgumentParser(description="Validate a user with a dynamic base URL")
    parser.add_argument("--user_svc_base_url", help="The base URL of the server (e.g., http://localhost:5000)", default="http://127.0.0.1:5001/api/users")
    parser.add_argument("--port", help="The port where the Progress Tracking app has to run (e.g., 5000)", default=5000)
    args = parser.parse_args()
    initialize_parameters(args=args)
    serve(app, host="0.0.0.0", port=args.port)
