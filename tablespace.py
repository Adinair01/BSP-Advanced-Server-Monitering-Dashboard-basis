import streamlit as st
import pandas as pd
from pathlib import Path
from db_conn import get_oracle_connection

# --- Available Database Environments and DBs ---
DB_CONFIGS = {
    "Development": ["rundb1", "rundb2"],
    "Testing": ["TestDB1", "TestDB2"],
    "Production": ["ProdDB1", "ProdDB2"]
}

# --- SQL Query for Tablespace Monitoring ---
#WITH ts_alloc AS (
#  SELECT
#    tablespace_name,
#    SUM(bytes) / 1024 / 1024 AS allocated_mb,
#    SUM(DECODE(autoextensible, 'YES', maxbytes, bytes)) / 1024 / 1024 AS max_mb
#  FROM dba_data_files
#  GROUP BY tablespace_name
#),
#ts_free AS (
# SELECT
#    tablespace_name,
#    SUM(bytes) / 1024 / 1024 AS free_mb
#  FROM dba_free_space
#  GROUP BY tablespace_name
#),
#ts_autoextend AS (
#  SELECT
#    tablespace_name,
#    SUM(DECODE(autoextensible, 'YES', (maxbytes - bytes), 0)) / 1024 / 1024 AS available_extension_mb
#  FROM dba_data_files
#  GROUP BY tablespace_name
#)
#SELECT
#  a.tablespace_name AS "Tablespace Name",
#  ROUND(a.max_mb, 2) AS "Max MB",
#  ROUND(a.allocated_mb, 2) AS "Allocated MB",
#  ROUND(NVL(f.free_mb, 0), 2) AS "Free MB",
#  ROUND((a.allocated_mb - NVL(f.free_mb, 0)), 2) AS "Used MB",
#  CASE
#    WHEN a.allocated_mb = 0 THEN 0
#    ELSE ROUND(((a.allocated_mb - NVL(f.free_mb, 0)) / a.allocated_mb) * 100, 2)
#  END AS "Percentage Used",
#  ROUND(NVL(x.available_extension_mb, 0), 2) AS "Available Extension MB",
#  CASE
#    WHEN a.allocated_mb = 0 THEN 0
#    ELSE ROUND((NVL(f.free_mb, 0) / a.allocated_mb) * 100, 2)
#  END AS "Percentage Free"
#FROM ts_alloc a
#LEFT JOIN ts_free f ON a.tablespace_name = f.tablespace_name
#LEFT JOIN ts_autoextend x ON a.tablespace_name = x.tablespace_name
#ORDER BY a.tablespace_name
#"""
TABLESPACE_QUERY = """
WITH ts_alloc AS (
  SELECT
    tablespace_name,
    SUM(bytes) / 1024 / 1024 AS allocated_mb,
    SUM(DECODE(autoextensible, 'YES', maxbytes, bytes)) / 1024 / 1024 AS max_mb
  FROM dba_data_files
  GROUP BY tablespace_name
),
ts_free AS (
  SELECT
    tablespace_name,
    SUM(bytes) / 1024 / 1024 AS free_mb
  FROM dba_free_space
  GROUP BY tablespace_name
),
ts_autoextend AS (
  SELECT
    tablespace_name,
    SUM(DECODE(autoextensible, 'YES', maxbytes - bytes, 0)) / 1024 / 1024 AS available_extension_mb
  FROM dba_data_files
  GROUP BY tablespace_name
)
SELECT
  a.tablespace_name AS "Tablespace Name",
  ROUND(a.max_mb, 2) AS "Max MB",
  ROUND(a.allocated_mb, 2) AS "Allocated MB",
  ROUND(NVL(f.free_mb, 0), 2) AS "Free MB",
  ROUND((a.allocated_mb - NVL(f.free_mb, 0)), 2) AS "Used MB",
  CASE
    WHEN a.allocated_mb = 0 THEN 0
    ELSE ROUND(((a.allocated_mb - NVL(f.free_mb, 0)) / a.allocated_mb) * 100, 2)
  END AS "Percentage Used",
  ROUND(NVL(x.available_extension_mb, 0), 2) AS "Available Extension MB",
  CASE
    WHEN a.allocated_mb = 0 THEN 0
    ELSE ROUND((NVL(f.free_mb, 0) / a.allocated_mb) * 100, 2)
  END AS "Percentage Free"
FROM ts_alloc a
LEFT JOIN ts_free f ON a.tablespace_name = f.tablespace_name
LEFT JOIN ts_autoextend x ON a.tablespace_name = x.tablespace_name
ORDER BY a.tablespace_name
"""
def get_status(row):
    max_mb = row["Max MB"]
    pct_free = row["Percentage Free"]
    if pct_free <= (10 if max_mb < 1000 else 5):
        return "Needs Extension"
    return "Normal"

def highlight_status(row):
    max_mb = row["Max MB"]
    pct_free = row["Percentage Free"]
    avail_ext = row["Available Extension MB"]

    if avail_ext < 10000:
        if max_mb >= 1000 and pct_free <= 5:
            color = "#ffcccc"  # Light red
        elif max_mb < 1000 and pct_free <= 10:
            color = "#fff5cc"  # Light yellow
        else:
            color = ""
    else:
        color = ""

    return [f"background-color: {color}"] * len(row)

@st.cache_data(ttl=300)
def fetch_tablespace_data(env, db):
    try:
        conn = get_oracle_connection(env, db)
        cursor = conn.cursor()
        cursor.execute(TABLESPACE_QUERY)
        cols = [desc[0] for desc in cursor.description]
        data = cursor.fetchall()
        cursor.close()
        conn.close()
        return pd.DataFrame(data, columns=cols)
    except Exception as e:
        st.error(f"Error fetching tablespace data: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def fetch_db_info(env, db):
    try:
        conn = get_oracle_connection(env, db)
        cursor = conn.cursor()

        cursor.execute("SELECT sys_context('USERENV','DB_NAME') FROM dual")
        db_name = cursor.fetchone()[0]

        cursor.execute("SELECT sys_context('USERENV','IP_ADDRESS') FROM dual")
        ip = cursor.fetchone()[0] or "Unavailable"

        cursor.close()
        conn.close()
        return db_name, ip
    except Exception as e:
        return "Unknown", "Unknown"

def main():
    st.set_page_config(page_title="Oracle Tablespace Monitor", layout="wide")

    st.sidebar.title("Settings")
    selected_env = st.sidebar.selectbox("Select Database Environment", list(DB_CONFIGS.keys()))
    db_list = DB_CONFIGS[selected_env]
    selected_db = st.sidebar.selectbox("Select Database", db_list)

    # Header with logo (optional)
    logo_path = Path(__file__).parent / "SAIL_Logo.png"
    col_logo, col_title = st.columns([1, 8])
    if logo_path.exists():
        with col_logo:
            st.image(str(logo_path), width=100)
    with col_title:
        st.markdown("<h1 style='margin-bottom:0;'>Oracle Tablespace Monitoring Dashboard</h1>", unsafe_allow_html=True)
        st.markdown("Monitor tablespace usage and health across environments.")

    db_name, ip_address = fetch_db_info(selected_env, selected_db)
    st.markdown(f"""
        **Environment:** `{selected_env}`  
        **Database:** `{selected_db}`  
        **Database Name:** `{db_name}`  
        **Server IP:** `{ip_address}`
    """)

    st.markdown("---")

    df = fetch_tablespace_data(selected_env, selected_db)
    if df.empty:
        st.warning("No tablespace data available.")
        return

    df["Status"] = df.apply(get_status, axis=1)

    total_ts = len(df)
    needs_ext = (df["Status"] == "Needs Extension").sum()

    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric(label="Total Tablespaces", value=total_ts)
    kpi2.metric(label="Needs Extension", value=needs_ext, delta=f"{(needs_ext/total_ts)*100:.1f}%" if total_ts else "0%")
    kpi3.metric(label="Normal", value=total_ts - needs_ext)

    st.markdown("---")

    styled_df = df.style.apply(highlight_status, axis=1).format({
        "Max MB": "{:,.0f}",
        "Allocated MB": "{:,.0f}",
        "Free MB": "{:,.0f}",
        "Used MB": "{:,.0f}",
        "Percentage Used": "{:.2f}%",
        "Available Extension MB": "{:,.0f}",
        "Percentage Free": "{:.2f}%",
    })

    st.dataframe(styled_df, height=500)

    st.markdown("---")
    st.markdown(
        f"<div style='text-align:right; color:gray; font-size:0.8em;'>Last updated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}</div>",
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()
