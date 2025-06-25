import oracledb
import json
import os

# Automatically use Thin mode (no Oracle Instant Client required)
oracledb.init_oracle_client = lambda *args, **kwargs: None  # Safeguard if called elsewhere

def load_db_config():
    config_path = os.path.join(os.path.dirname(__file__), "cred.json")
    try:
        with open(config_path, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        raise RuntimeError("cred.json file not found.")
    except json.JSONDecodeError:
        raise RuntimeError("Invalid JSON format in cred.json.")

def get_oracle_connection(env, db_name):
    """
    Get Oracle database connection for specified environment and database.
    
    Args:
        env (str): Environment name (Development, Testing, Production)
        db_name (str): Database name (rundb1, rundb2, TestDB1, etc.)
    
    Returns:
        oracledb.Connection: Oracle database connection object
    """
    config = load_db_config()

    if env not in config:
        raise ValueError(f"Environment '{env}' not found in configuration.")
    if db_name not in config[env]:
        raise ValueError(f"Database '{db_name}' not found in environment '{env}'.")

    creds = config[env][db_name]
    try:
        connection = oracledb.connect(
            user=creds["user"],
            password=creds["password"],
            dsn=creds["dsn"],
            config_dir=None  # Ensures thin mode
        )
        return connection
    except oracledb.DatabaseError as e:
        raise RuntimeError(f"Oracle DB connection failed for {env}/{db_name}: {e}")