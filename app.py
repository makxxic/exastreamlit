# =========================
# Carbon Footprint Calculator — Full
# =========================

import os
import io
import datetime
import sqlite3
from typing import Dict, Any
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from openai import OpenAI

# -------------------- CONFIG --------------------
st.set_page_config(page_title="Carbon Footprint Calculator — Full", page_icon="🌍", layout="wide")

EMISSION_FACTORS = {
    "Car (Petrol)": 0.192,
    "Car (Diesel)": 0.171,
    "Motorbike": 0.103,
    "Matatu/Bus": 0.105,
    "Bicycle/Walking": 0.0
}
ELECTRICITY_FACTOR = 0.18
LPG_FACTOR = 3.0

# -------------------- ENV --------------------
# Streamlit Cloud secrets preferred
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY")
OPENAI_MODEL = st.secrets.get("OPENAI_MODEL", "gpt-4o-mini")
SUPABASE_URL = st.secrets.get("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY")

# -------------------- OPENAI CLIENT --------------------
OPENAI_AVAILABLE = bool(OPENAI_API_KEY)
if OPENAI_AVAILABLE:
    client = OpenAI(api_key=OPENAI_API_KEY)

# -------------------- SUPABASE --------------------
try:
    from supabase import create_client
    SUPABASE_AVAILABLE = bool(SUPABASE_URL and SUPABASE_KEY)
except Exception:
    SUPABASE_AVAILABLE = False

def init_supabase():
    if SUPABASE_AVAILABLE:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    return None

supabase = init_supabase()

# -------------------- LOCAL SQLITE --------------------
sqlite_conn = sqlite3.connect("emissions.db", check_same_thread=False)
cur = sqlite_conn.cursor()
# daily_emissions table
cur.execute("""
CREATE TABLE IF NOT EXISTS daily_emissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    alias TEXT,
    date TEXT,
    transport_mode TEXT,
    distance REAL,
    electricity REAL,
    lpg REAL,
    transport_emission REAL,
    electricity_emission REAL,
    lpg_emission REAL,
    total_emission REAL,
    notes TEXT
);
""")
# user goals
cur.execute("""
CREATE TABLE IF NOT EXISTS user_goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    weekly_target REAL
);
""")
# leaderboard aliases
cur.execute("""
CREATE TABLE IF NOT EXISTS leaderboard_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    alias TEXT
);
""")
sqlite_conn.commit()

# -------------------- HELPERS --------------------
def compute_emissions(distance_km, transport_mode, electricity_kwh, lpg_kg):
    tf = EMISSION_FACTORS.get(transport_mode, 0.0)
    t_e = float(distance_km) * float(tf)
    e_e = float(electricity_kwh) * float(ELECTRICITY_FACTOR)
    l_e = float(lpg_kg) * float(LPG_FACTOR)
    total = t_e + e_e + l_e
    return {
        "transport_emission": t_e,
        "electricity_emission": e_e,
        "lpg_emission": l_e,
        "total_emission": total
    }

# Insert local
def insert_local(record: Dict[str, Any]):
    cur = sqlite_conn.cursor()
    cur.execute("""
        INSERT INTO daily_emissions (user_id, alias, date, transport_mode, distance, electricity, lpg,
            transport_emission, electricity_emission, lpg_emission, total_emission, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        record.get('user_id'), record.get('alias'), record.get('date'), record.get('transport_mode'), record.get('distance'),
        record.get('electricity'), record.get('lpg'), record.get('transport_emission'), record.get('electricity_emission'),
        record.get('lpg_emission'), record.get('total_emission'), record.get('notes')
    ))
    sqlite_conn.commit()

def fetch_all_local_for_user(user_id=None):
    if user_id:
        df = pd.read_sql_query("SELECT * FROM daily_emissions WHERE user_id=? ORDER BY date ASC", sqlite_conn, params=(user_id,))
    else:
        df = pd.read_sql_query("SELECT * FROM daily_emissions ORDER BY date ASC", sqlite_conn)
    if not df.empty:
        df['date'] = pd.to_datetime(df['date']).dt.date
    return df

def insert_supabase(record: Dict[str, Any]):
    if supabase:
        try:
            supabase.table('daily_emissions').insert(record).execute()
            return True
        except Exception as e:
            st.error(f"Supabase insert error: {e}")
            return False
    return False

# -------------------- AUTH --------------------
def supabase_sign_in_ui():
    st.sidebar.markdown("### Account")
    if not supabase:
        st.sidebar.info("Supabase not configured: local-only mode.")
        return None
    if 'user' not in st.session_state:
        st.session_state['user'] = None
        st.session_state['user_id'] = None
    if st.session_state['user'] is None:
        email = st.sidebar.text_input("Email for sign in (magic link)")
        if st.sidebar.button("Send Magic Link") and email:
            try:
                supabase.auth.sign_in_with_email(email=email)
                st.sidebar.success("Check your email for magic link. Refresh page after signing in.")
            except Exception as e:
                st.sidebar.error(f"Auth error: {e}")
        if st.sidebar.button("Continue as guest"):
            st.session_state['user'] = {"id": f"guest-{os.getpid()}"}
            st.session_state['user_id'] = st.session_state['user']['id']
    else:
        st.sidebar.write(f"Signed in as: {st.session_state['user'].get('email', st.session_state['user']['id'])}")
        if st.sidebar.button("Sign out"):
            try:
                supabase.auth.sign_out()
            except Exception:
                pass
            st.session_state['user'] = None
            st.session_state['user_id'] = None

# -------------------- PAGES --------------------
def page_home():
    st.title("🌍 Carbon Footprint Calculator — Full")
    st.write("Track, compare, and reduce your daily carbon emissions. Supports user accounts via Supabase.")

def page_enter_data():
    st.header("Enter or upload daily data")
    user_id = st.session_state.get('user_id')
    alias = st.text_input("Display alias for leaderboard (optional)")
    col1, col2, col3 = st.columns([3,2,2])
    date = st.date_input("Date", value=datetime.date.today())
    with col1:
        distance = st.number_input("Distance (km)", min_value=0.0, value=0.0)
        transport_mode = st.selectbox("Transport mode", list(EMISSION_FACTORS.keys()))
    with col2:
        electricity = st.number_input("Electricity (kWh)", min_value=0.0, value=0.0)
        lpg = st.number_input("LPG used (kg)", min_value=0.0, value=0.0)
    notes = st.text_area("Notes")
    if st.button("Save entry"):
        em = compute_emissions(distance, transport_mode, electricity, lpg)
        record = {
            'user_id': user_id,
            'alias': alias,
            'date': date.isoformat(),
            'transport_mode': transport_mode,
            'distance': distance,
            'electricity': electricity,
            'lpg': lpg,
            'transport_emission': em['transport_emission'],
            'electricity_emission': em['electricity_emission'],
            'lpg_emission': em['lpg_emission'],
            'total_emission': em['total_emission'],
            'notes': notes
        }
        if not insert_supabase(record):
            insert_local(record)
        st.success(f"Saved — {em['total_emission']:.2f} kg CO₂")

    # CSV Upload
    st.markdown("---")
    st.markdown("### Import CSV (columns: date, distance, transport_mode, electricity, lpg, alias(optional), notes(optional))")
    uploaded = st.file_uploader("Upload CSV", type=["csv"])
    if uploaded:
        df_csv = pd.read_csv(uploaded)
        required = ['date','distance','transport_mode','electricity','lpg']
        missing = [c for c in required if c not in df_csv.columns]
        if missing:
            st.error(f"Missing required columns: {missing}")
        else:
            count = 0
            for _, row in df_csv.iterrows():
                try:
                    date_str = pd.to_datetime(row['date']).date().isoformat()
                    em = compute_emissions(row['distance'], row['transport_mode'], row['electricity'], row['lpg'])
                    rec = {
                        'user_id': user_id,
                        'alias': row.get('alias', alias),
                        'date': date_str,
                        'transport_mode': row['transport_mode'],
                        'distance': float(row['distance']),
                        'electricity': float(row['electricity']),
                        'lpg': float(row['lpg']),
                        'transport_emission': em['transport_emission'],
                        'electricity_emission': em['electricity_emission'],
                        'lpg_emission': em['lpg_emission'],
                        'total_emission': em['total_emission'],
                        'notes': row.get('notes','')
                    }
                    if not insert_supabase(rec):
                        insert_local(rec)
                    count += 1
                except Exception as e:
                    st.warning(f"Failed row: {e}")
            st.success(f"Imported {count} rows")

# -------------------- HISTORY --------------------
def page_history():
    st.header("History & Charts")
    user_id = st.session_state.get('user_id')
    df = fetch_all_local_for_user(user_id)
    if df.empty:
        st.info("No data yet")
        return

    st.dataframe(df[['date','alias','distance','electricity','lpg','total_emission']].sort_values('date',ascending=False))

    df['date'] = pd.to_datetime(df['date'])
    # Monthly totals
    df_monthly = df.groupby(df['date'].dt.to_period("M")).sum().reset_index()
    df_monthly['date'] = df_monthly['date'].dt.to_timestamp()
    fig, ax = plt.subplots(figsize=(8,4))
    ax.plot(df_monthly['date'], df_monthly['total_emission'], marker="o")
    ax.set_title("Monthly Total CO₂ Emissions")
    ax.set_xlabel("Month")
    ax.set_ylabel("kg CO₂")
    plt.xticks(rotation=45)
    st.pyplot(fig)

    # Last 14 days stacked bar
    last = df.sort_values('date').tail(14)
    fig2, ax2 = plt.subplots(figsize=(10,4))
    ax2.bar(last['date'], last['transport_emission'], label='Transport')
    ax2.bar(last['date'], last['electricity_emission'], bottom=last['transport_emission'], label='Electricity')
    bottoms = last['transport_emission'] + last['electricity_emission']
    ax2.bar(last['date'], last['lpg_emission'], bottom=bottoms, label='LPG')
    ax2.legend()
    plt.xticks(rotation=45)
    st.pyplot(fig2)

    # CSV download
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Download History CSV", data=csv, file_name="co2_history.csv", mime="text/csv")

# -------------------- GOALS & ALERTS --------------------
def page_goals_and_alerts():
    st.header("Goals & Alerts")
    user_id = st.session_state.get('user_id')
    c = sqlite_conn.cursor()
    current = None
    if user_id:
        c.execute("SELECT weekly_target FROM user_goals WHERE user_id=?", (user_id,))
        r = c.fetchone()
        if r: current = r[0]
    target = st.number_input("Weekly emissions target (kg CO2)", min_value=0.0, value=current or 20.0)
    if st.button("Save target"):
        if current is None:
            c.execute("INSERT INTO user_goals (user_id, weekly_target) VALUES (?,?)", (user_id, float(target)))
        else:
            c.execute("UPDATE user_goals SET weekly_target=? WHERE user_id=?", (float(target), user_id))
        sqlite_conn.commit()
        st.success("Saved goal")

    # Weekly check
    today = datetime.date.today()
    start_week = today - datetime.timedelta(days=today.weekday())
    df = fetch_all_local_for_user(user_id)
    if not df.empty:
        df['date'] = pd.to_datetime(df['date']).dt.date
        week_df = df[(df['date'] >= start_week) & (df['date'] <= today)]
        weekly_total = week_df['total_emission'].sum()
        st.metric("This week's total (kg CO2)", f"{weekly_total:.2f}")
        if weekly_total > target:
            st.error("⚠️ You have exceeded your weekly target.")
        else:
            st.success("👍 Within weekly target.")

# -------------------- LEADERBOARD --------------------
def page_leaderboard():
    st.header("Public Leaderboard")
    df_all = fetch_all_local_for_user(None)
    if df_all.empty:
        st.info("No data yet")
        return
    today = datetime.date.today()
    start_week = today - datetime.timedelta(days=7)
    df_all['date'] = pd.to_datetime(df_all['date']).dt.date
    week = df_all[df_all['date'] >= start_week]
    agg = week.groupby('alias').agg({'total_emission':'sum'}).reset_index()
    agg['alias'] = agg['alias'].fillna('Anonymous')
    agg = agg.sort_values('total_emission')
    st.table(agg.head(10).rename(columns={'total_emission':'weekly_total_kgCO2'}))
    st.markdown("**Leaderboard:** Top performers have lowest weekly CO₂ totals.")

# -------------------- INSIGHTS --------------------
def page_insights():
    st.header("Insights & AI Recommendations")
    user_id = st.session_state.get('user_id')
    df = fetch_all_local_for_user(user_id)
    if df.empty:
        st.info("Add entries first to see insights.")
        return
    total_saved = df['total_emission'].sum()
    avg_per_entry = df['total_emission'].mean()
    col1, col2 = st.columns(2)
    col1.metric("Total (saved entries) kg CO₂", f"{total_saved:.2f}")
    col2.metric("Average per entry (kg CO₂)", f"{avg_per_entry:.2f}")

    # GPT Tips
    if OPENAI_AVAILABLE:
        if st.button("Get GPT Tips"):
            last = df.tail(7)
            summary = "\n".join([f"{r['date']}: {r['total_emission']:.2f} kg" for _,r in last.iterrows()])
            prompt = f"You are a sustainability assistant. Given recent daily CO₂ totals:\n{summary}\nProvide 10 actionable tips for reducing emissions."
            try:
                response = client.responses.create(model=OPENAI_MODEL, input=prompt, max_output_tokens=300)
                st.markdown(response.output_text)
            except Exception as e:
                st.error(f"AI Error: {e}")
    else:
        st.warning("OpenAI not configured.")

# -------------------- MAIN APP --------------------
def main():
    st.sidebar.title("Navigation")
    supabase_sign_in_ui()
    pages = {
        "Home": page_home,
        "Enter Data": page_enter_data,
        "History": page_history,
        "Goals & Alerts": page_goals_and_alerts,
        "Leaderboard": page_leaderboard,
        "Insights": page_insights
    }
    choice = st.sidebar.radio("Go to", list(pages.keys()))
    pages[choice]()

if __name__ == "__main__":
    main()
