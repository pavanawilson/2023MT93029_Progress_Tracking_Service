import argparse
from flask import Flask, request, jsonify
import psycopg2
import requests
import uuid
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from jwt.algorithms import RSAAlgorithm
import time
from datetime import date
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# Global variables to store the token and its expiration time
access_token = None
token_expiration_time = 0

# Auth0 settings
AUTH0_DOMAIN = "dev-xf7eb30rgaz2rvse.us.auth0.com"
CLIENT_ID = "sZp4AQgp95rIMgcpKoXLuzZtqNM72j2e"
CLIENT_SECRET = "ufkpj_72QmMvLUWKhLheZiPrgnr5ZjqQfr5qLowhY3e6VZnVUkwwm3rQuUrNZUlu"

def get_access_token(audience):
    global access_token, token_expiration_time

    # Check if the token is still valid
    if access_token and time.time() < token_expiration_time:
        return access_token

    # Otherwise, request a new token
    url = f"https://{AUTH0_DOMAIN}/oauth/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "audience": audience
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url, data=payload, headers=headers)

    if response.status_code == 200:
        token_data = response.json()
        
        access_token = response.json().get('access_token')
        expires_in = token_data["expires_in"]  # In seconds
        token_expiration_time = time.time() + expires_in
        return access_token
    else:
        raise Exception("Failed to obtain token: " + response.text)

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
        raise Exception("Token has expired")
    except jwt.InvalidTokenError:
        raise Exception("Invalid token")

def decode_token(token, audience):
    # try:
        # Fetch the public key in PEM format
        public_key = get_public_key(token, audience)

        # Decode the JWT with the PEM-formatted public key
        decoded_token = jwt.decode(token, public_key, algorithms="RS256", audience=audience)
        return decoded_token

def validate_token(request, audience):
        # Extract the token from the Authorization header
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({"error": "Authorization header missing"}), 401

    # Expecting token in format "Bearer <token>"
    try:
        token = auth_header.split(" ")[1]
    except IndexError:
        return jsonify({"error": "Token format invalid"}), 401
    
    # Decode the token
    try:
        decoded_token = decode_token(token, audience)
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "Token has expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "Invalid token"}), 401
    if not decoded_token:
        return jsonify({"error": "Unauthorized"}), 401
    if not decoded_token:
        return jsonify({"error": "Unauthorized"}), 401
            
db_config = {
    "dbname": "fitnessdb",
    "user": "fitnessdb_owner",
    "password": "zUkQGO3BXec2",
    "host": "ep-winter-block-a5pb6mh3.us-east-2.aws.neon.tech",
    "port": "5432"  # or whatever port Neon DB specifies
}

def get_db_connection():
    try:
        # conn = psycopg2.connect(DATABASE_URL)
        conn = psycopg2.connect(**db_config)
        print("Connected to Neon DB successfully")
        return conn
    except Exception as e:
        print("Error connecting to Neon DB:", e)

def validate_user(user_id):
    # Get the access token for authorization
    validate_audience =  f"http://127.0.0.1:5001/api/users/validate/{user_id}"   #/validate/{userId} f"{base_url}/api/user/validate/{user_id}"
    try:
        access_token = get_access_token(validate_audience)
    except Exception as e:
        return jsonify({"error": f"Error getting access token: {str(e)}"}), 500
    
    # Validate the user by calling the User Service endpoint with the access token
    try:
        validation_url = f"http://127.0.0.1:5001/api/users/validate/{user_id}"   #/validate/{userId} f"{base_url}/api/user/validate/{user_id}"
        headers = {"Authorization": f"Bearer {access_token}"}
        validation_response = requests.get(validation_url, headers=headers)
        if validation_response.status_code == 200 and validation_response.json().get("valid") == True:
            return validation_response.json().get("valid")
        else:
            # User validation failed
            return jsonify({"error": "User validation failed or user does not exist"}), 404
    except requests.exceptions.RequestException as e:
        # Handle errors in making the validation request
        print(f"Error validating user: {e}")
        return jsonify({"error": "An error occurred while validating the user"}), 500
    
@app.route('/api/progress/<user_id>', methods=['GET'])
def get_user_progress(user_id):
    #Extract the token and validate
    audience = "http://127.0.0.1:5000/api/progress/{user_id}"
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

@app.route('/api/progress/summary/<user_id>', methods=['GET'])
def get_progress_summary(user_id):
    #Extract the token and validate
    audience = "http://127.0.0.1:5000/api/progress/summary/{user_id}"
    validate_token(request, audience)
    
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
     
    # Parse the JSON data from the request
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid or missing JSON data"}), 400

    # Extract required fields
    user_id = data.get('user_id')
    date_logged = data.get('date')
    weight_kg = data.get('weight_kg')
    workout_done = data.get('workout_done')
    calories_burned = data.get('calories_burned')

    # Validate required fields
    if not all([user_id, date_logged, weight_kg, workout_done, calories_burned]):
        return jsonify({"error": "All fields (user_id, date, weight_kg, workout_done, calories_burned) are required"}), 400

    # if validate_user(user_id) == True:
    #     #Check if validation was successful
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

        # Close the cursor and connection
        cursor.close()
        conn.close()

        # Return a success response
        return jsonify({"message": "Progress logged successfully", "id": progress_id}), 201

    except Exception as e:
        conn.rollback()
        print(f"Error logging progress: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()
        
@app.route('/api/progress/log/<log_id>', methods=['PUT'])
def update_progress_log(log_id):
    #Extract the token and validate
    audience = "http://127.0.0.1:5000/api/progress/log/{log_id}"
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
            return jsonify({"message": "Progress log updated", "updated_log": updated_row}), 200
        else:
            return jsonify({"error": "Log entry not found"}), 404
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500      
    finally:
        cursor.close()
        conn.close()
    
@app.route('/api/progress/log/<log_id>', methods=['DELETE'])
def delete_progress_log(log_id):
    #Extract the token and validate
    audience = "http://127.0.0.1:5000/api/progress/log/{log_id}"
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
            return jsonify({"message": "Progress log deleted", "deleted_log_id": deleted_row[0]}), 200
        else:
            return jsonify({"error": "Log entry not found"}), 404
            
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/progress/user/<user_id>/logs', methods=['DELETE'])
def delete_all_logs_for_user(user_id):
    #Extract the token and validate
    audience = "http://127.0.0.1:5000/api/progress/user/{user_id}/logs"
    validate_token(request, audience)
    
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
            return jsonify({
                "message": f"All progress logs for user {user_id} deleted",
                "deleted_log_count": deleted_rows
            }), 200
        else:
            return jsonify({"error": "No logs found for the given user_id"}), 404
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()
        
if __name__ == '__main__':
    # parser = argparse.ArgumentParser(description="Validate a user with a dynamic base URL")
    # parser.add_argument("base_url", help="The base URL of the server (e.g., http://localhost:5000)")
    # parser.add_argument("port", help="The port where the Progress Tracking app has to run (e.g., 5000)")
    # args = parser.parse_args()
    # app.run(debug=True, port=args.port)
    app.run(debug=True)
