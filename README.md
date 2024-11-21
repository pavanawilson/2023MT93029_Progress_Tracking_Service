# Progress Tracking Service

## Technologies used
- **Backend**: Python, Flask
- **Database**: Postgres hosted in Cloud Platform(https://neon/tech/)
- **Security**: JWT from Auth0(https://auth0.com)
- **API testing tool**: Postman
## Prerequisites
- Install python
- Install pip
- Install dependencies
- Install flask

## Execution Instructions
`python progress_tracking_app.py` is the command to run the Progress Tracking microservice.

Optional arguments:
- `user_svc_base_url`: The base URL for User Profile microservice. It has default value as `http://127.0.0.1:5001/api/users`.
- `port`: The port where the Progress Tracking app has to run. It has default value as `5000`.

```
python progress_tracking_app.py --user_svc_base_url http://127.0.0.1:5001/api/ --port 5000
```

## Service Functionality
| HTTP Verb  | URL                      | Description                                   |
|------------|--------------------------|-----------------------------------------------|
| GET        | /api/progress/{user_id}          | Get all progress logs for a user      |
| GET        | /api/progress/summary/<user_id>  | Get summary of user progress          |
| POST       | /api/progress/log                | Log a new progress entry              |
| PUT        | /api/progress/log/{log_id}       | Update an existing progress log entry          |
| DELETE     | /api/progress/log/{log_id}       | Delete a progress log entry           |
| DELETE     | /api/progress/user/{user_id}/logs| Delete all progress logs for a specific user  |

## Security
All API calls are authenticated with a JWT Bearer token in header.

## Inter-service communication
Synchronous REST API call  to User Profile service is used for validating user before logging user progress.

## Database Pattern
**Event Sourcing Pattern**: Each log entry (progress_logs) is treated as an immutable event, capturing user progress over time. This pattern supports historical data analysis and rollback capabilities.

**Foreign Key Pattern**: The user_id in progress_logs references the user_id in the User Profile Service, maintaining consistency.