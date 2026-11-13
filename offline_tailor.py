"""Deterministic, local-only application tailoring. No model or network required."""
import re

ALIASES = {
 'react.js':['react','reactjs'], 'next.js':['next.js','nextjs'], 'vue.js':['vue','vuejs'],
 'node.js':['node','nodejs'], 'fastapi':['fastapi','fast api'], 'postgresql':['postgres','postgresql'],
 'aws':['aws','amazon web services'], 'ci/cd':['ci/cd','continuous integration','continuous delivery'],
 'rest apis':['rest api','restful','rest apis'], 'ai training':['ai training','ai trainer','train ai'],
 'data annotation':['data annotation','data labeling','data labelling','annotator'],
 'coding ai evaluation':['coding evaluation','code evaluation','ai evaluator','llm evaluator'],
 'shopify':['shopify'], 'bubble':['bubble','bubble.io'], 'ecommerce development':['ecommerce','e-commerce'],
}

def mentions(text,skill):
    t=text.casefold(); s=skill.casefold(); variants=ALIASES.get(s,[s]);
    return any(re.search(r'(?<![\w])'+re.escape(v)+r'(?![\w])',t) for v in variants)

def tailor_offline(resume,row,jd):
    if not isinstance(resume.get('experience'),list) or not resume['experience'] or not isinstance(resume.get('skills'),list):
        raise ValueError('Structured master resume requires experience and skills arrays')
    skills=[str(x) for x in resume['skills'] if isinstance(x,str)]
    matched=[s for s in skills if mentions(jd+' '+str(row.get('role','')),s)]
    others=[s for s in skills if s not in matched]
    # Keep source skills only; highlight matches at front. Limit length to keep documents readable.
    ordered=(matched+others)[:48]
    experience=[]
    for item in resume['experience']:
        bullets=list(item.get('bullets',[]))
        ranked=sorted(enumerate(bullets),key=lambda pair:(-sum(mentions(pair[1],s) for s in matched),pair[0]))
        experience.append({'company':item.get('company',''),'title':item.get('title',''),
                           'dates':item.get('dates',''),'bullets':[b for _,b in ranked]})
    base=str(resume.get('summary','')).strip()
    intro=('Relevant technologies for this position: '+', '.join(matched[:10])+'. ') if matched else ''
    summary=(intro+base).strip()
    company=str(row.get('company','the company')); role=str(row.get('role','the position'))
    evidence=[]
    for entry in experience:
        if entry['bullets']:
            evidence.append((entry['company'],entry['bullets'][0]))
    paragraph=' '.join(f'At {c}, {b[0].lower()+b[1:] if b else b}' for c,b in evidence[:2])
    if len(paragraph)>540: paragraph=paragraph[:537].rsplit(' ',1)[0]+'.'
    focus=('My background includes '+', '.join(matched[:6])+', which aligns with the technologies mentioned in the posting.' if matched else
           'My full-stack development background includes web applications, integrations, and cross-functional delivery.')
    letter=(f'Dear Hiring Team,\n\nI am applying for the {role} position at {company}. '
            f'{focus}\n\n{paragraph}\n\n'
            'I would welcome the opportunity to discuss how my documented experience could support your team. '
            'Thank you for considering my application.\n\nSincerely,\n'+str(resume.get('name','Juan Paolo Ramos')))
    return {'summary':summary,'skills':ordered,'experience':experience,'cover_letter':letter,
            'matched_skills':matched,'mode':'Offline (rule-based)'}
