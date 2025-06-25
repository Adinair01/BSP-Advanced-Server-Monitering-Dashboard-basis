# 🔧 SAIL Server + Oracle DB Monitoring Dashboard

A REAL TIME, all-in-one monitoring solution for system health and Oracle database performance — built during my internship at **Bhilai Steel Plant, C&IT Division**.

---

## 🚀 Features

### 🖥️ Server Monitoring (via SSH)
- Real-time CPU, memory, and filesystem usage
- OS-aware parsing (Linux, AIX, HP-UX, Solaris)
- Targeted filesystem highlights (e.g., `/dev/sdal`, `/dev/sda4`)
- Status classification (UP / ATTENTION / CRITICAL / DOWN)
- Gradient-based styling for visual clarity

### 🗄️ Oracle Database Monitoring
- **Tablespace Analysis**:
  - Max, Allocated, Free, Used MB
  - Percentage Used/Free
  - Auto-extension tracking
  - Status tags: `Normal` / `Needs Extension`

- **Session Analysis**:
  - Active, Inactive, Blocked sessions
  - Logon time, memory usage, and blocking session details
  - Filter by username, status, or connection time

### 🧩 Multi-Environment Support
- Supports Dev, Testing, and Production DBs
- Credentials securely handled using `cred.json`

---

## 💻 Tech Stack

| Component           | Tech Used                  |
|---------------------|----------------------------|
| Frontend UI         | Streamlit                  |
| SSH Server Metrics  | Paramiko + Shell Commands  |
| DB Access           | oracledb (thin mode)       |
| Data Handling       | Pandas, SQL                |
| Styling             | Custom CSS via Streamlit   |

