import streamlit as st
from pathlib import Path
st.set_page_config(page_title="Juan Job Platform",page_icon="💼",layout="wide")
st.title("Juan Job Platform")
st.subheader("Remote Job Discovery + Application Studio")
st.write("Use the pages in the left sidebar: **1. Job Discovery** searches public job APIs and exports a four-column CSV; **2. Application Studio** reads the latest CSV and generates tailored application files.")
st.info("Job discovery does not guarantee 100 listings or confirm Philippines eligibility. Review each posting before applying. AI generation uses your own OpenAI API key and incurs API charges.")
st.write("**Priorities:** 80% verified software-development roles; 20% AI training and annotation. Fully remote and Philippines-eligible opportunities are prioritized, not guaranteed.")
st.write("**Your document filenames:** Juan_Paolo_Ramos_resume.docx, Juan_Paolo_Ramos_resume.pdf, Juan_Paolo_Ramos_cover_letter.docx")
