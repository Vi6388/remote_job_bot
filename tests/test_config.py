import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_priorities():
 c=json.loads((ROOT/'bot'/'config.json').read_text())
 assert c['role_priorities']=={'software_development':80,'ai_training_annotation':20}
 assert 'lemon.io' in c['excluded_companies']
 assert 'React' in c['search_profile']['unverified_do_not_assume']
def test_integration():
 s=(ROOT/'pages'/'2_Application_Studio.py').read_text()
 assert 'latest_files[0]' in s
 for name in ['Juan_Paolo_Ramos_resume.docx','Juan_Paolo_Ramos_resume.pdf','Juan_Paolo_Ramos_cover_letter.docx']:
  assert name in s
