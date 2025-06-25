import oracledb
from db_conn import get_oracle_connection

def test_connection(env="Development", db_name="rundb1"):
    """
    Test Oracle database connection for specified environment and database
    
    Args:
        env (str): Environment name (Development, Testing, Production)
        db_name (str): Database name
    """
    try:
        print(f"Testing connection to {env}/{db_name}...")
        
        # Get the connection
        conn = get_oracle_connection(env, db_name)
        cursor = conn.cursor()

        # Query 1: Check database version
        cursor.execute("SELECT * FROM v$version WHERE ROWNUM = 1")
        version = cursor.fetchone()
        print("Database Version:", version[0] if version else "Unknown")

        # Query 2: Get current user
        cursor.execute("SELECT USER FROM dual")
        user = cursor.fetchone()
        print("Current User:", user[0])

        # Query 3: Get database name
        cursor.execute("SELECT sys_context('USERENV','DB_NAME') FROM dual")
        db = cursor.fetchone()
        print("Database Name:", db[0])

        # Query 4: Simple calculation test
        cursor.execute("SELECT 1 + 1 FROM dual")
        result = cursor.fetchone()
        print("1 + 1 =", result[0])

        # Query 5: Test tablespace query (basic version)
        try:
            cursor.execute("SELECT COUNT(*) FROM dba_tablespaces")
            count = cursor.fetchone()
            print("Number of tablespaces:", count[0])
        except Exception as e:
            print("Tablespace query failed (might need DBA privileges):", str(e))

        print("✅ Connection test successful!")

    except oracledb.Error as e:
        print(f"❌ Error connecting to Oracle database ({env}/{db_name}):", e)
    except Exception as e:
        print(f"❌ General error: {e}")
    finally:
        try:
            cursor.close()
            conn.close()
            print("Connection closed.")
        except:
            pass

def test_all_environments():
    """Test connections to all configured environments and databases"""
    environments = {
        "Development": ["rundb1", "rundb2"],
        "Testing": ["TestDB1", "TestDB2"],
        "Production": ["ProdDB1", "ProdDB2"]
    }
    
    for env, dbs in environments.items():
        for db in dbs:
            print(f"\n{'='*50}")
            test_connection(env, db)
            print('='*50)

if __name__ == "__main__":
    # Test single connection (modify as needed)
    test_connection("Development", "rundb1")
    
    # Uncomment below to test all configured connections
    # test_all_environments()