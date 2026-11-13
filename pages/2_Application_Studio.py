import io, json, os, re, time, zipfile, socket, ipaddress
from urllib.parse import urlparse
import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from openai import OpenAI
from docx import Document
from docx.shared import Inches, Pt
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_LEFT
from reportlab.lib import colors
from xml.sax.saxutils import escape
from pypdf import PdfReader

st.set_page_config(page_title='Job Application Studio', page_icon='📄', layout='wide')
st.title('Job Application Studio')
st.caption('Remote Job Bot V4 CSV → verified job descriptions → tailored resume DOCX/PDF + cover letter DOCX')

SYSTEM = '''You tailor job applications accurately. Only use verified facts from the master resume. Never invent skills, employers, dates, metrics, qualifications, or experience. Preserve company names, employment dates, and factual job titles EXACTLY. Return ONLY valid JSON with keys summary (string), skills (array of strings), experience (array of objects with company, title, dates, bullets array), cover_letter (string). Include all experience entries in their original order. Preserve every company, title and dates verbatim. Reword bullets without introducing unverified achievements. Keep cover letter under 300 words, professional and specific to the job. Do not claim location eligibility unless explicitly stated.''' 

def extract_resume(upload):
    name=upload.name.lower(); raw=upload.getvalue()
    if name.endswith('.json'):
        return json.loads(raw)
    if name.endswith('.docx'):
        doc=Document(io.BytesIO(raw)); txt='\n'.join(p.text for p in doc.paragraphs if p.text.strip())
        for table in doc.tables:
            txt+='\n'+'\n'.join(' | '.join(c.text for c in row.cells) for row in table.rows)
        return {'source_text':txt}
    if name.endswith('.pdf'):
        reader=PdfReader(io.BytesIO(raw)); txt='\n'.join(page.extract_text() or '' for page in reader.pages)
        if len(txt.strip())<100: raise ValueError('PDF text could not be extracted. Upload a text-based PDF, DOCX, or JSON.')
        return {'source_text':txt}
    raise ValueError('Unsupported resume format')

def validate_public_url(url):
    parsed=urlparse(url)
    if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Only public HTTP(S) job URLs are supported')
    host=parsed.hostname.lower().rstrip('.')
    if host in ('localhost','localhost.localdomain') or host.endswith(('.local','.internal')):
        raise ValueError('Private job URL blocked')
    try:
        addresses=socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme=='https' else 80),type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError('Job URL host could not be resolved') from exc
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError('Job URL resolves to a non-public address')
    return url

def extract_job(url):
    # Redirects are checked individually. Keep this dashboard on a trusted local machine;
    # a public deployment requires additional network-level SSRF protections.
    with requests.Session() as session:
        for _ in range(6):
            validate_public_url(url)
            r=session.get(url,headers={'User-Agent':'Mozilla/5.0 (compatible; JobApplicationStudio/2.0)'},timeout=18,allow_redirects=False,stream=True)
            if r.status_code in (301,302,303,307,308):
                from urllib.parse import urljoin
                target=r.headers.get('Location')
                r.close()
                if not target: raise ValueError('Redirect without location')
                url=urljoin(url,target)
                continue
            r.raise_for_status()
            if 'html' not in r.headers.get('Content-Type','html').lower():
                r.close(); raise ValueError('Link did not return HTML')
            if int(r.headers.get('Content-Length','0') or 0)>2_000_000:
                r.close(); raise ValueError('Job page is too large')
            raw=r.raw.read(2_000_001,decode_content=True)
            r.close()
            if len(raw)>2_000_000: raise ValueError('Job page is too large')
            soup=BeautifulSoup(raw,'html.parser')
            for tag in soup(['script','style','nav','footer','header','form']): tag.decompose()
            for tag in soup.select('[role="navigation"], .cookie-banner, #cookie-banner'): tag.decompose()
            text='\n'.join(t.strip() for t in soup.stripped_strings)
            if len(text)<350: raise ValueError('Job description too short or requires JavaScript/login; paste the full JD manually')
            return text[:22000]
        raise ValueError('Too many redirects')

def normalize_csv(df):
    aliases={'company name':'company','company':'company','role':'role','title':'role','compensation':'compensation','salary':'compensation','job link':'url','url':'url','link':'url'}
    df=df.rename(columns={c:aliases.get(str(c).strip().lower(),str(c)) for c in df.columns})
    for key in ('company','role','url'):
        if key not in df: raise ValueError(f'Missing CSV column: {key}')
    if 'compensation' not in df: df['compensation']='Not disclosed'
    return df[['company','role','compensation','url']].fillna('').drop_duplicates(subset=['url'])

def tailor(client, model, resume, row, jd):
    payload={'master_resume':resume,'job':{'company':row['company'],'role':row['role'],'compensation':row['compensation'],'url':row['url'],'description':jd}}
    response=client.chat.completions.create(model=model,temperature=0.2,response_format={'type':'json_object'},messages=[{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}])
    result=json.loads(response.choices[0].message.content)
    if not isinstance(result.get('experience'),list): raise ValueError('AI did not return structured experience')
    if not isinstance(result.get('skills'),list) or not isinstance(result.get('summary'),str) or not isinstance(result.get('cover_letter'),str): raise ValueError('AI response missing required fields')
    # If the source is structured, enforce exact company, title, dates and count.
    original=resume.get('experience') if isinstance(resume,dict) else None
    if isinstance(original,list) and original:
        if len(result['experience'])!=len(original): raise ValueError('AI omitted experience entries')
        for generated,source in zip(result['experience'],original):
            for field in ('company','title','dates'):
                if str(generated.get(field,''))!=str(source.get(field,'')):
                    raise ValueError(f'AI changed protected field: {field}')
    # Skills are limited to exact entries in the verified master profile.
    allowed={str(x).casefold():str(x) for x in resume.get('skills',[])}
    result['skills']=[allowed[str(x).casefold()] for x in result['skills'] if str(x).casefold() in allowed]
    return result

def make_resume_docx(data, original):
    doc=Document(); section=doc.sections[0]; section.top_margin=Inches(.65); section.bottom_margin=Inches(.65)
    name=original.get('name','Candidate') if isinstance(original,dict) else 'Candidate'
    doc.add_heading(name,0)
    contact=original.get('contact','') if isinstance(original,dict) else ''
    if contact: doc.add_paragraph(str(contact))
    doc.add_heading('Professional Summary',1); doc.add_paragraph(data.get('summary',''))
    doc.add_heading('Technical Skills',1); doc.add_paragraph(' • '.join(map(str,data.get('skills',[]))))
    doc.add_heading('Professional Experience',1)
    for item in data['experience']:
        doc.add_heading(f"{item.get('title','')} | {item.get('company','')}",2)
        doc.add_paragraph(str(item.get('dates','')))
        for bullet in item.get('bullets',[]): doc.add_paragraph(str(bullet),style='List Bullet')
    for section_name in ('education','certifications','projects'):
        value=original.get(section_name) if isinstance(original,dict) else None
        if value:
            doc.add_heading(section_name.title(),1)
            if isinstance(value,list):
                for v in value: doc.add_paragraph(json.dumps(v,ensure_ascii=False) if isinstance(v,dict) else str(v))
            else: doc.add_paragraph(str(value))
    output=io.BytesIO(); doc.save(output); return output.getvalue()

def make_pdf(data,original):
    output=io.BytesIO(); pdf=SimpleDocTemplate(output,pagesize=(612,792),leftMargin=45,rightMargin=45,topMargin=42,bottomMargin=42)
    s=getSampleStyleSheet(); s['Normal'].fontSize=9; s['Normal'].leading=12
    story=[]
    def p(value,style='Normal'): story.append(Paragraph(escape(str(value)).replace('\n','<br/>'),s[style])); story.append(Spacer(1,6))
    p(original.get('name','Candidate'),'Title')
    if original.get('contact'): p(original['contact'])
    p('Professional Summary','Heading2'); p(data.get('summary',''))
    p('Technical Skills','Heading2'); p(' • '.join(map(str,data.get('skills',[]))))
    p('Professional Experience','Heading2')
    for item in data['experience']:
        p(f"{item.get('title','')} | {item.get('company','')}",'Heading3'); p(item.get('dates',''))
        for bullet in item.get('bullets',[]): p('• '+str(bullet))
    for name in ('education','certifications','projects'):
        value=original.get(name)
        if value:
            p(name.title(),'Heading2')
            if isinstance(value,list):
                for x in value: p(json.dumps(x,ensure_ascii=False) if isinstance(x,dict) else x)
            else: p(value)
    pdf.build(story); return output.getvalue()

def make_letter_docx(data,original,company,role):
    doc=Document(); doc.add_heading('Cover Letter',0)
    if original.get('name'): doc.add_paragraph(str(original['name']))
    doc.add_paragraph(f'Application: {role} — {company}')
    for para in data.get('cover_letter','').split('\n'):
        if para.strip(): doc.add_paragraph(para.strip())
    b=io.BytesIO(); doc.save(b); return b.getvalue()

def safe(s): return re.sub(r'[^a-zA-Z0-9_-]+','_',str(s)).strip('_')[:55] or 'job'

with st.sidebar:
    st.header('Settings')
    api_key=st.text_input('OpenAI API key',type='password',value=os.getenv('OPENAI_API_KEY',''))
    model=st.text_input('Model',value='gpt-4o-mini')
    limit=st.number_input('Jobs to process per batch',1,100,5)
    st.caption('API requests incur usage costs. Start with 1–3 jobs to test. Each successful job produces 3 documents.')

from pathlib import Path
BOT_OUTPUT = Path(__file__).resolve().parents[1] / 'bot' / 'output'
latest_files = sorted(BOT_OUTPUT.glob('jobs_*.csv'), reverse=True) if BOT_OUTPUT.exists() else []
left,right=st.columns(2)
with left:
    csv=st.file_uploader('1. Upload job CSV (optional if bot has run)',type=['csv'])
    use_latest = st.checkbox('Use latest bot CSV automatically', value=bool(latest_files), disabled=not bool(latest_files))
    if latest_files and use_latest:
        st.caption(f'Using {latest_files[0].name} (uploaded CSV takes precedence)')
with right: master=st.file_uploader('2. Upload verified master resume JSON',type=['json'])

if csv or (latest_files and use_latest):
    try:
        df=normalize_csv(pd.read_csv(csv if csv else latest_files[0])); st.success(f'{len(df)} unique job links loaded')
        st.dataframe(df,use_container_width=True,hide_index=True)
    except Exception as exc: st.error(str(exc)); df=None
else: df=None

if df is not None and master:
    try:
        resume=extract_resume(master)
        if not isinstance(resume.get('experience'),list) or not resume.get('experience') or not isinstance(resume.get('skills'),list):
            raise ValueError('Master resume JSON must include a non-empty experience array and a skills array. See master_resume.example.json.')
        st.subheader('Job descriptions')
        selected=st.multiselect('Select jobs',options=list(range(len(df))),format_func=lambda i:f"{df.iloc[i]['company']} — {df.iloc[i]['role']}",default=list(range(min(len(df),int(limit)))))
        if len(selected)>int(limit): st.warning(f'Selected {len(selected)} jobs; the current batch limit is {limit}. Only the first {limit} selected will be processed.')
        if 'overrides' not in st.session_state: st.session_state.overrides={}
        with st.expander('Paste descriptions for blocked or JavaScript-only job pages'):
            for i in selected:
                key=str(df.iloc[i]['url'])
                st.session_state.overrides[key]=st.text_area(f"{df.iloc[i]['company']} — {df.iloc[i]['role']}",value=st.session_state.overrides.get(key,''),key=f'jd_{i}',height=100)
        if st.button('Generate application packages',type='primary',disabled=not api_key or not selected):
            selected=selected[:int(limit)]
            client=OpenAI(api_key=api_key)
            bundle=io.BytesIO(); logs=[]; bar=st.progress(0)
            with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as z:
                for pos,i in enumerate(selected):
                    row=df.iloc[i].to_dict(); key=str(row['url']); folder=f"{pos+1:03d}_{safe(row['company'])}_{safe(row['role'])}"
                    try:
                        jd=st.session_state.overrides.get(key,'').strip() or extract_job(key)
                        if len(jd)<250: raise ValueError('Job description is too short; paste the full JD')
                        if not any(term in jd.lower() for term in ('responsibilit','requirement','qualification','experience','about the role','what you')):
                            raise ValueError('Could not verify this is a complete job description; paste the full JD manually')
                        data=tailor(client,model,resume,row,jd)
                        z.writestr(f'{folder}/Juan_Paolo_Ramos_resume.docx',make_resume_docx(data,resume))
                        z.writestr(f'{folder}/Juan_Paolo_Ramos_resume.pdf',make_pdf(data,resume))
                        z.writestr(f'{folder}/Juan_Paolo_Ramos_cover_letter.docx',make_letter_docx(data,resume,row['company'],row['role']))
                        z.writestr(f'{folder}/job_description.txt',jd)
                        logs.append({'Company':row['company'],'Role':row['role'],'Status':'Generated','Detail':''})
                    except Exception as exc:
                        logs.append({'Company':row['company'],'Role':row['role'],'Status':'Needs review','Detail':str(exc)[:250]})
                    bar.progress((pos+1)/len(selected))
                z.writestr('processing_report.csv',pd.DataFrame(logs).to_csv(index=False))
            st.session_state['package']=bundle.getvalue(); st.session_state['logs']=logs
        if st.session_state.get('logs'):
            st.dataframe(pd.DataFrame(st.session_state['logs']),hide_index=True,use_container_width=True)
            st.download_button('Download all application documents (ZIP)',st.session_state['package'],file_name='application_packages.zip',mime='application/zip')
    except Exception as exc: st.error(str(exc))

st.divider()
st.caption('Review every generated document before applying. The app never submits applications. Do not deploy this local prototype publicly without URL security controls and authentication.')
