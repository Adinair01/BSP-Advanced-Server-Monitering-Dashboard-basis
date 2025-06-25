import streamlit as st
import pandas as pd
import paramiko
import re
import base64
import os
from streamlit_autorefresh import st_autorefresh
from pathlib import Path
from db_conn import get_oracle_connection
import socket

# File paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = os.path.join(BASE_DIR, 'SAIL_Logo.png')
CSV_PATH = os.path.join(BASE_DIR, 'credentials.csv')

# Target filesystems to highlight
TARGET_FS = ["/dev/sdal", "tmpfs", "/dev/sda2", "/dev/sda4"]

# Database configurations
DB_CONFIGS = {
    "Development": ["rundb1", "rundb2"],
    "Testing": ["TestDB1", "TestDB2"],
    "Production": ["ProdDB1", "ProdDB2"]
}

# Tablespace SQL Query
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

# Sessions SQL Query
SESSIONS_QUERY = """
SELECT 
    s.sid,
    s.serial#,
    s.username,
    s.status,
    s.osuser,
    s.machine,
    s.program,
    s.module,
    s.action,
    TO_CHAR(s.logon_time, 'DD-MON-YYYY HH24:MI:SS') AS logon_time,
    ROUND((SYSDATE - s.logon_time) * 24, 2) AS hours_connected,
    s.blocking_session,
    s.sql_id,
    s.prev_sql_id,
    ROUND(st.value/1024/1024, 2) AS memory_mb
FROM v$session s
LEFT JOIN v$sesstat st ON s.sid = st.sid AND st.statistic# = (
    SELECT statistic# FROM v$statname WHERE name = 'session pga memory'
)
WHERE s.type = 'USER'
ORDER BY s.status DESC, s.logon_time DESC
"""

# === Enhanced Styling ===
def apply_custom_style():
    st.markdown("""
    <style>
        .stApp {
            background: linear-gradient(135deg, #0D47A1, #1976D2, #2196F3);
            color: white;
        }
        
        .main .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
        
        .section {
            background: linear-gradient(145deg, #1565C0, #1E88E5);
            border: 2px solid #42A5F5;
            border-radius: 15px;
            padding: 25px;
            margin: 20px 0;
            box-shadow: 0 8px 25px rgba(0,0,0,0.3);
            backdrop-filter: blur(10px);
        }
        
        .metric {
            font-size: 22px;
            font-weight: bold;
            margin-bottom: 8px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        
        .dataframe {
            background-color: rgba(255,255,255,0.1);
            border-radius: 10px;
            backdrop-filter: blur(5px);
        }
        
        .dataframe tbody tr:hover {
            background-color: rgba(100,181,246,0.3) !important;
        }
        
        .stSelectbox > div > div {
            background-color: rgba(25,118,210,0.8);
            color: white;
            border: 2px solid #42A5F5;
            border-radius: 8px;
        }
        
        .stExpander > div {
            background: linear-gradient(145deg, #1565C0, #1E88E5);
            border: 1px solid #42A5F5;
            border-radius: 10px;
        }
        
        .stTab > div {
            background-color: rgba(25,118,210,0.8);
            border-radius: 10px 10px 0 0;
        }
        
        div[data-testid="metric-container"] {
            background: linear-gradient(145deg, #1976D2, #2196F3);
            border: 2px solid #64B5F6;
            border-radius: 12px;
            padding: 15px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        }
        
        div[data-testid="metric-container"] > div {
            color: white !important;
        }
        
        html, body, [class*="css"] {
            font-size: 1rem !important;
        }
        
        h1, h2, h3 {
            color: #E3F2FD !important;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        
        .status-critical {
            background-color: #D32F2F !important;
            color: white !important;
            font-weight: bold;
            border-radius: 8px;
            padding: 8px;
        }
        
        .status-warning {
            background-color: #F57C00 !important;
            color: white !important;
            font-weight: bold;
            border-radius: 8px;
            padding: 8px;
        }
        
        .status-good {
            background-color: #388E3C !important;
            color: white !important;
            font-weight: bold;
            border-radius: 8px;
            padding: 8px;
        }
        
        .status-down {
            background-color: #8B0000 !important;
            color: white !important;
            font-weight: bold;
            border-radius: 8px;
            padding: 8px;
        }
    </style>
    """, unsafe_allow_html=True)

def encode_image(image_path):
    try:
        with open(image_path, "rb") as img_file:
            b64 = base64.b64encode(img_file.read()).decode()
        return b64
    except:
        return None

# === Server Monitoring Functions ===
def read_credentials(path):
    try:
        df = pd.read_csv(path)
        required_cols = ["Host", "User", "Password"]
        if not all(col in df.columns for col in required_cols):
            st.error(f"CSV must contain: {required_cols}")
            return []
        return df.to_dict(orient="records")
    except Exception as e:
        st.error(f"Error reading CSV: {e}")
        return []

def ssh_exec(client, cmd):
    stdin, stdout, stderr = client.exec_command(cmd)
    return stdout.read().decode()

def parse_cpu_linux(client):
    try:
        output = ssh_exec(client, "uname")
        if "HP-UX" in output:
            output = ssh_exec(client, "sar 1 1 | tail -1")
            parts = output.split()
            if len(parts) >= 5:
                idle = float(parts[-1])
                return round(100 - idle, 2)
        elif "AIX" in output or "SunOS" in output:
            output = ssh_exec(client, "vmstat 1 2 | tail -1")
            parts = output.split()
            if len(parts) >= 15:
                idle = float(parts[14])
                return round(100 - idle, 2)
        else:
            output = ssh_exec(client, "top -bn1 | grep '%Cpu' || mpstat 1 1")
            idle_match = re.search(r'(\d+.\d+)\s*id', output)
            if idle_match:
                idle = float(idle_match.group(1))
                return round(100 - idle, 2)
    except:
        return None
    return None

def parse_mem_linux(client):
    try:
        os_check = ssh_exec(client, "uname")
        if "HP-UX" in os_check:
            return 1024, 512, 512, 0  # Placeholder
        elif "AIX" in os_check or "SunOS" in os_check:
            output = ssh_exec(client, "vmstat")
            lines = output.strip().splitlines()
            if len(lines) >= 3:
                parts = lines[-1].split()
                if len(parts) >= 5:
                    free = int(parts[4]) // 1024
                    total = 1024
                    used = total - free
                    return total, used, free, 0
        else:
            output = ssh_exec(client, "free -m")
            lines = output.splitlines()
            for line in lines:
                if line.lower().startswith("mem:"):
                    parts = line.split()
                    total = int(parts[1])
                    used = int(parts[2])
                    free = int(parts[3])
                    buff_cache = int(parts[5]) if len(parts) > 5 else 0
                    return total, used, free, buff_cache
    except:
        return None, None, None, None
    return None, None, None, None

def parse_filesystem(client):
    try:
        os_type = ssh_exec(client, "uname").strip()
        if "HP-UX" in os_type:
            output = ssh_exec(client, "bdf")
        elif "AIX" in os_type or "SunOS" in os_type:
            output = ssh_exec(client, "df -k")
        else:
            output = ssh_exec(client, "df -h")

        fs_list = []
        lines = output.strip().splitlines()
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 6:
                fs_list.append({
                    "Filesystem": parts[0],
                    "Size": parts[1],
                    "Used": parts[2],
                    "Available": parts[3],
                    "Use%": parts[4],
                    "Mounted on": parts[5]
                })
        return fs_list
    except:
        return []

def colorize_usage(value):
    try:
        val = float(value)
        if val >= 90:
            return '#D32F2F'  # Red
        else:
            return '#388E3C'  # Green
    except:
        return '#9E9E9E'

# === Database Functions ===
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

        st.error(f"Error fetching sessions data: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def fetch_db_info(env, db):
    try:
        conn = get_oracle_connection(env, db)
        cursor = conn.cursor()

        cursor.execute("SELECT sys_context('USERENV','DB_NAME') FROM dual")
        db_name = cursor.fetchone()[0]

        cursor.execute("SELECT sys_context('USERENV','SERVER_HOST') FROM dual")
        host = cursor.fetchone()[0]

        try:
            ip = socket.gethostbyname(host)
        except:
            ip = "Unavailable"

        cursor.close()
        conn.close()
        return db_name, ip
    except Exception as e:
        return "Unknown", "Unknown"

# === Tab Functions ===
def server_monitoring_tab():
    st_autorefresh(interval=300000, key="refresh_key")  # 5 minutes
    
    st.markdown("### 🖥️ Server Health Monitoring")
    
    credentials = read_credentials(CSV_PATH)
    if not credentials:
        st.warning("No server credentials found.")
        return

    server_data = []

    for cred in credentials:
        host = cred["Host"]
        user = cred["User"]
        password = cred["Password"]

        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(hostname=host, username=user, password=password, timeout=7)

            cpu = parse_cpu_linux(client)
            cpu_color = colorize_usage(cpu) if cpu is not None else '#9E9E9E'

            if cpu is not None:
                if cpu >= 90:
                    row_style = 'background: linear-gradient(145deg, #D32F2F, #F44336);'
                    status = 'CRITICAL'
                    status_level = 0
                elif cpu >= 80:
                    row_style = 'background: linear-gradient(145deg, #F57C00, #FF9800);'
                    status = 'NEED ATTENTION'
                    status_level = 1
                else:
                    row_style = 'background: linear-gradient(145deg, #388E3C, #4CAF50);'
                    status = 'UP'
                    status_level = 2
            else:
                row_style = 'background: linear-gradient(145deg, #616161, #757575);'
                status = 'UNKNOWN'
                status_level = 3

            mem = parse_mem_linux(client)
            fs = parse_filesystem(client)

            server_data.append({
                "host": host,
                "client": client,
                "cpu": cpu,
                "cpu_color": cpu_color,
                "mem": mem,
                "fs": fs,
                "status": status,
                "row_style": row_style,
                "status_level": status_level
            })

        except Exception:
            server_data.append({
                "host": host,
                "cpu": None,
                "cpu_color": "#9E9E9E",
                "mem": (None, None, None, None),
                "fs": [],
                "status": "DOWN",
                "row_style": 'background: linear-gradient(145deg, #8B0000, #B71C1C);',
                "status_level": 4,
                "client": None
            })

    server_data.sort(key=lambda x: x["status_level"])

    for data in server_data:
        host = data["host"]
        cpu = data["cpu"]
        cpu_color = data["cpu_color"]
        row_style = data["row_style"]
        status = data["status"]
        total, used, free, buff_cache = data["mem"]
        fs = data["fs"]
        client = data["client"]

        if status == "DOWN":
            st.markdown(f"""
            <div class='section status-down'>
                <h3>🛑 {host} is DOWN</h3>
                <p>Server is not responding to connection attempts</p>
            </div>
            """, unsafe_allow_html=True)
            continue

        with st.expander(f"🖥️ Server: {host}  — Status: **{status}**", expanded=False):
            st.markdown(f'<div class="section" style="{row_style} color: white;">', unsafe_allow_html=True)
            
            # CPU Metrics
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f'<div class="metric" style="color:{cpu_color}">⚙️ CPU Usage: {cpu if cpu is not None else "N/A"}%</div>', unsafe_allow_html=True)
            
            # Memory Metrics
            if None not in (total, used, free):
                mem_usage_pct = round((used / total) * 100, 2)
                mem_color = colorize_usage(mem_usage_pct)
                with col2:
                    st.markdown(f'<div class="metric" style="color:{mem_color}">💾 Memory Usage: {used}MB / {total}MB ({mem_usage_pct}%)</div>', unsafe_allow_html=True)
                st.markdown(f'<div style="color:#E3F2FD; margin-top: 10px;">📊 Free: {free}MB | Buff/Cache: {buff_cache}MB</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="metric" style="color:#FFA726;">💾 Memory data unavailable</div>', unsafe_allow_html=True)

            # Filesystem Table
            if fs:
                st.markdown("### 📁 Filesystem Usage")
                df_fs = pd.DataFrame(fs)

                def color_filesystem_usage(val):
                    try:
                        pct = int(val.strip('%'))
                        if pct > 90:
                            return 'color: #D32F2F; font-weight: bold;'  # Red
                        else:
                            return 'color: #388E3C; font-weight: bold;'  # Green
                    except:
                        return ''

                def highlight_target(row):
                    if row["Filesystem"] in TARGET_FS:
                        return ['background-color: rgba(0,77,64,0.8); color: white; font-weight: bold;'] * len(row)
                    else:
                        return [''] * len(row)

                st.dataframe(
                    df_fs.style
                        .apply(highlight_target, axis=1)
                        .map(color_filesystem_usage, subset=['Use%']),
                    height=300,
                    use_container_width=True
                )
            else:
                st.markdown('<div style="color:#FFA726;">📁 No filesystem info available.</div>', unsafe_allow_html=True)

            st.markdown('</div>', unsafe_allow_html=True)
            
            if client:
                client.close()

def database_monitoring_tab():
    st.markdown("### 🗄️ Oracle Database Tablespace Monitoring")
    
    # Database selection
    col1, col2 = st.columns(2)
    with col1:
        selected_env = st.selectbox("Select Database Environment", list(DB_CONFIGS.keys()))
    with col2:
        db_list = DB_CONFIGS[selected_env]
        selected_db = st.selectbox("Select Database", db_list)

    if selected_db:
        db_name, ip_address = fetch_db_info(selected_env, selected_db)
        
        # REPLACE THIS SECTION - Make database info more compact
        st.markdown(f"""
        <div style='background: linear-gradient(145deg, #1565C0, #1E88E5); border: 1px solid #42A5F5; border-radius: 8px; padding: 12px; margin: 10px 0; box-shadow: 0 4px 10px rgba(0,0,0,0.2);'>
            <div style='display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px;'>
                <span style='color: #FFFFFF ; font-size: 0.9rem;'><strong>Environment:</strong> <span style='color: #FFFFFF ;'>{selected_env}</span></span>
                <span style='color: #FFFFFF ; font-size: 0.9rem;'><strong>Database:</strong> <span style='color: #FFFFFF ;'>{selected_db}</span></span>
                <span style='color: #FFFFFF ; font-size: 0.9rem;'><strong>DB Name:</strong> <span style='color: #FFFFFF ;'>{db_name}</span></span>
                <span style='color: #FFFFFF ; font-size: 0.9rem;'><strong>Server IP:</strong> <span style='color: #FFFFFF ;'>{ip_address}</span></span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        df = fetch_tablespace_data(selected_env, selected_db)
        if df.empty:
            st.warning("No tablespace data available.")
            return

        df["Status"] = df.apply(get_status, axis=1)

        total_ts = len(df)
        needs_ext = (df["Status"] == "Needs Extension").sum()

        # KPI Metrics
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

        st.dataframe(styled_df, height=500, use_container_width=True)

        st.markdown(
            f"<div style='text-align:right; color:#B3E5FC; font-size:0.8em; margin-top: 15px;'>Last updated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}</div>",
            unsafe_allow_html=True
        )
    else:
        st.info("Please select a database.")

def sessions_monitoring_tab():
yle='color: #FFFFFF; font-size: 0.9rem;'><strong>Environment:</strong> <span style='color: #FFFFFF;'>{selected_env}</span></span>
                <span style='color: #FFFFFF ; font-size: 0.9rem;'><strong>Database:</strong> <span style='color: #FFFFFF ;'>{selected_db}</span></span>
                <span style='color: #FFFFFF ; font-size: 0.9rem;'><strong>DB Name:</strong> <span style='color: #FFFFFF ;'>{db_name}</span></span>
                <span style='color: #FFFFFF ; font-size: 0.9rem;'><strong>Server IP:</strong> <span style='color: #FFFFFF ;'>{ip_address}</span></span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        df_sessions = fetch_sessions_data(selected_env, selected_db)
        if df_sessions.empty:
            st.warning("No session data available.")
            return

        # Session Statistics
        total_sessions = len(df_sessions)
        active_sessions = len(df_sessions[df_sessions['STATUS'] == 'ACTIVE'])
        inactive_sessions = len(df_sessions[df_sessions['STATUS'] == 'INACTIVE'])
        blocked_sessions = len(df_sessions[df_sessions['BLOCKING_SESSION'].notna()])

        # KPI Metrics
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric(label="Total Sessions", value=total_sessions)
        kpi2.metric(label="Active Sessions", value=active_sessions)
        kpi3.metric(label="Inactive Sessions", value=inactive_sessions)
        kpi4.metric(label="Blocked Sessions", value=blocked_sessions)

        st.markdown("---")

        # Filter options
        st.markdown("#### 🔍 Filter Options")
        filter_col1, filter_col2, filter_col3 = st.columns(3)
        
        with filter_col1:
            status_filter = st.multiselect(
                "Filter by Status",
                options=df_sessions['STATUS'].unique(),
                default=df_sessions['STATUS'].unique()
            )
        
        with filter_col2:
            username_filter = st.multiselect(
                "Filter by Username",
                options=df_sessions['USERNAME'].dropna().unique(),
                default=df_sessions['USERNAME'].dropna().unique()
            )
        
        with filter_col3:
            min_hours = st.number_input("Min Hours Connected", min_value=0.0, value=0.0, step=0.1)

        # Apply filters
        filtered_df = df_sessions[
            (df_sessions['STATUS'].isin(status_filter)) &
            (df_sessions['USERNAME'].isin(username_filter)) &
            (df_sessions['HOURS_CONNECTED'] >= min_hours)
        ]

        # Session status highlighting
        def highlight_session_status(row):
            status = row['STATUS']
            if status == 'ACTIVE':
                return ['background-color: rgba(76, 175, 80, 0.3);'] * len(row)  # Light green
            elif status == 'INACTIVE':
                return ['background-color: rgba(255, 193, 7, 0.3);'] * len(row)  # Light yellow
            elif status == 'KILLED':
                return ['background-color: rgba(244, 67, 54, 0.3);'] * len(row)  # Light red
            else:
                return [''] * len(row)

        # Display filtered sessions
        st.markdown(f"#### 📋 Session Details ({len(filtered_df)} sessions)")
        
        if not filtered_df.empty:
            styled_sessions = filtered_df.style.apply(highlight_session_status, axis=1).format({
                'HOURS_CONNECTED': '{:.2f}',
                'MEMORY_MB': '{:.2f}'
            })
            
            st.dataframe(styled_sessions, height=600, use_container_width=True)
        else:
            st.info("No sessions match the current filters.")

        # Session summary by user
        st.markdown("#### 📊 Sessions Summary by User")
        if not filtered_df.empty:
            user_summary = filtered_df.groupby(['USERNAME', 'STATUS']).size().reset_index(name='Count')
            user_pivot = user_summary.pivot(index='USERNAME', columns='STATUS', values='Count').fillna(0).astype(int)
            st.dataframe(user_pivot, use_container_width=True)

        st.markdown(
            f"<div style='text-align:right; color:#B3E5FC; font-size:0.8em; margin-top: 15px;'>Last updated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}</div>",
            unsafe_allow_html=True
        )
    else:
        st.info("Please select a database.")

# === Main Application ===
def main():
    st.set_page_config(page_title="SAIL Monitoring Dashboard", layout="wide", initial_sidebar_state="expanded")
    apply_custom_style()

    # Header with logo
    logo_b64 = encode_image(LOGO_PATH)
    if logo_b64:
        st.markdown(f"""
        <div style='display:flex; align-items:center; margin-bottom:30px; padding: 20px; background: linear-gradient(145deg, #0D47A1, #1976D2); border-radius: 15px; box-shadow: 0 8px 25px rgba(0,0,0,0.3);'>
            <img src="data:image/png;base64,{logo_b64}" style="width:150px; margin-right:50px; filter: drop-shadow(2px 2px 4px rgba(0,0,0,0.3));" />
            <div>
                <h1 style='color:white; margin:0; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);'>Bhilai Steel Plant - C&IT</h1>
                <h3 style='color:#E3F2FD; margin:0; font-weight:300;'>Advanced Monitoring Dashboard</h3>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style='margin-bottom:30px; padding: 25px; background: linear-gradient(145deg, #0D47A1, #1976D2); border-radius: 15px; box-shadow: 0 8px 25px rgba(0,0,0,0.3);'>
            <h1 style='color:white; margin:0; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);'>Bhilai Steel Plant - C&IT</h1>
            <h3 style='color:#E3F2FD; margin:0; font-weight:300;'>Advanced Monitoring Dashboard</h3>
        </div>
        """, unsafe_allow_html=True)

    # Create tabs
    tab1, tab2, tab3 = st.tabs(["🖥️ Server Monitoring", "🗄️ Database Monitoring", "👥 Sessions Monitoring"])
    
    with tab1:
        server_monitoring_tab()
    
    with tab2:
        database_monitoring_tab()
    
    with tab3:
        sessions_monitoring_tab()

if __name__ == "__main__":
    main()
