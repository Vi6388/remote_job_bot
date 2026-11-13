import json
import subprocess
import sys
from pathlib import Path
import pandas as pd
import streamlit as st
st.title("Remote Job Discovery")
BOT=Path(__file__).resolve().parents[1]/"bot"
config=json.loads((BOT/"config.json").read_text(encoding="utf-8"))
st.write(f"Daily target: **{config['target_daily_leads']}** | Software: **{config['role_priorities']['software_development']}%** | AI: **{config['role_priorities']['ai_training_annotation']}%**")
st.caption("Public sources: Remotive, Arbeitnow, RemoteOK, Jobicy, Himalayas. Optional Lever, Greenhouse and Ashby board IDs are editable in bot/config.json. Some sources may be blocked or unavailable.")
if st.button("Find jobs now",type="primary"):
    with st.spinner("Fetching jobs from public APIs; this may take a minute..."):
        try:
            r=subprocess.run([sys.executable,str(BOT/"job_bot.py")],cwd=str(BOT),capture_output=True,text=True,timeout=240)
            if r.returncode: st.error("Bot failed"); st.code((r.stderr or r.stdout)[-4000:])
            else: st.success("Job search completed"); st.code(r.stdout[-3000:])
        except subprocess.TimeoutExpired: st.error("Search timed out. Try again later.")
files=sorted((BOT/"output").glob("jobs_*.csv"),reverse=True) if (BOT/"output").exists() else []
if files:
    latest=files[0]; data=latest.read_bytes()
    df=pd.read_csv(latest)
    st.metric("Latest report rows",len(df))
    st.dataframe(df,hide_index=True,use_container_width=True)
    st.download_button("Download latest job CSV",data=data,file_name=latest.name,mime="text/csv")
    st.info("Open the Application Studio page to use this report automatically, or upload a different CSV there.")
else: st.info("Run your first search to create a CSV, or upload an existing V4 CSV on the Application Studio page.")
