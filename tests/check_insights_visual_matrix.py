"""Run independent native windows for the theme/language/scale/size matrix."""
import concurrent.futures
import itertools
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
from qa_support import QA_ROOT, qa_path
cases=list(itertools.product(('light','dark'),('th','en'),(1,1.25,1.5),('minimum','default','maximized')))

def check(case):
    theme,language,scale,size=case
    args=[sys.executable,str(ROOT/'tests'/'check_insights_visual.py'),'--theme',theme,'--language',language,'--scale',str(scale),'--size',size]
    result=subprocess.run(args,capture_output=True,text=True,timeout=60)
    return dict(case=list(case),passed=result.returncode==0,output=result.stdout.strip() if result.returncode==0 else result.stderr[-4000:])

with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    reports=list(pool.map(check,cases))
summary=dict(cases=len(reports),passed=sum(r['passed'] for r in reports),failures=[r for r in reports if not r['passed']],reports=reports)
(QA_ROOT/'insights_visual'/'matrix.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k!='reports'}))
raise SystemExit(0 if summary['passed']==len(reports) else 1)
