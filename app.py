import streamlit as st
import pandas as pd
import paramiko
import re
import base64
import os
from streamlit_autorefresh import st_autorefresh

# File paths
# LOGO_PATH = /dashboard/dash/BSP_Internship/SAIL_Logo.png
# CSV_PATH = /dashboard/dash/BSP_Internship/credentials.csv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


LOGO_PATH = os.path.join(BASE_DIR, 'SAIL_Logo.png')
CSV_PATH = os.path.join(BASE_DIR, 'credentials.csv')

# Target filesystems to highlight
TARGET_FS = ["/dev/sdal", "tmpfs", "/dev/sda2", "/dev/sda4"]

# === Styling ===
def apply_custom_style():
    st.markdown("""
    <style>
        .stApp {
            background: linear-gradient(to right, #001F4D, #003366);
            color: white;
        }
        .section {
            background-color: #002B5C;
            border-left: 5px solid #00bcd4;
            border-radius: 10px;
            padding: 20px;
            margin: 20px 0;
            box-shadow: 2px 2px 10px #000000;
        }
        .metric {
            font-size: 20px;
            font-weight: bold;
            margin-bottom: 5px;
        }
        .dataframe tbody tr:hover {
            background-color: #263238 !important;
        }
    </style>
    """, unsafe_allow_html=True)

def encode_image(image_path):
    with open(image_path, "rb") as img_file:
        b64 = base64.b64encode(img_file.read()).decode()
    return b64

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
            return '#D32F2F'
        elif val >= 80:
            return '#F57C00'
        else:
            return '#388E3C'
    except:
        return '#9E9E9E'

# === Main App ===
def main():
    print("hello main")
    st.set_page_config(page_title="SAIL Server Dashboard", layout="wide")
    apply_custom_style()
    st_autorefresh(interval=3000000, key="refresh_key")

    # Header
    st.markdown(f"""
    <div style='display:flex; align-items:center; margin-bottom:20px;'>
        <img src="data:image/png;base64,{encode_image(LOGO_PATH)}" style="width:60px; margin-right:15px;" />
        <h1 style='color:white;'>Bhilai Steel Plant - C&IT  - Server Monitoring Dashboard</h1>
    </div>
    """, unsafe_allow_html=True)

    credentials = read_credentials(CSV_PATH)
    if not credentials:
        st.warning("No credentials found.")
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
                    row_style = 'background-color: #B71C1C;'
                    status = 'CRITICAL'
                    status_level = 0
                elif cpu >= 80:
                    row_style = 'background-color: #F57C00;'
                    status = 'NEED ATTENTION'
                    status_level = 1
                else:
                    row_style = 'background-color: #1B5E20;'
                    status = 'UP'
                    status_level = 2
            else:
                row_style = 'background-color: #616161;'
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
                "row_style": 'background-color: #8B0000;',
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
            st.markdown(f"<div class='section' style='background-color: #8B0000;'><strong style='color:white;'>🛑 {host} is DOWN</strong></div>", unsafe_allow_html=True)
            continue

        with st.expander(f"🖥️ Server: {host}  — Status: **{status}**", expanded=False):
            st.markdown(f'<div class="section" style="{row_style} color: white;">', unsafe_allow_html=True)
            st.markdown(f'<div class="metric" style="color:{cpu_color}">⚙️ CPU Usage: {cpu if cpu is not None else "N/A"}%</div>', unsafe_allow_html=True)

            if None not in (total, used, free):
                mem_usage_pct = round((used / total) * 100, 2)
                mem_color = colorize_usage(mem_usage_pct)
                st.markdown(f'<div class="metric" style="color:{mem_color}">💾 Memory Usage: {used}MB / {total}MB ({mem_usage_pct}%)</div>', unsafe_allow_html=True)
                st.markdown(f'<div style="color:lightgray;">Free: {free}MB | Buff/Cache: {buff_cache}MB</div>', unsafe_allow_html=True)
            else:
                st.write("Memory data unavailable")

            if fs:
                df_fs = pd.DataFrame(fs)

                def color_use(val):
                    try:
                        pct = int(val.strip('%'))
                        if pct >= 85:
                            return 'color: #D32F2F;'
                        elif pct >= 60:
                            return 'color: #F57C00;'
                        else:
                            return 'color: #388E3C;'
                    except:
                        return ''

                def highlight_target(row):
                    if row["Filesystem"] in TARGET_FS:
                        return ['background-color: #004d40; color: white;'] * len(row)
                    else:
                        return [''] * len(row)

                st.dataframe(
                    df_fs.style
                        .apply(highlight_target, axis=1)
                        .map(color_use, subset=['Use%']),
                    height=300
                )
            else:
                st.write("No filesystem info available.")

            client.close()

if __name__ == "__main__":
    main()
