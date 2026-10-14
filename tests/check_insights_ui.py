"""Compatibility entrypoint for the redesigned Insights UI checks."""
import argparse
import subprocess
import sys
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('--theme',choices=('light','dark'),default='light')
parser.add_argument('--language',choices=('en','th'),default='en')
parser.add_argument('--scale',type=float,default=1)
parser.add_argument('--size',choices=('minimum','default','maximized'),default='default')
parser.add_argument('--fixture',action='store_true')
parser.add_argument('--exercise',action='store_true')
args=parser.parse_args()
command=[sys.executable,str(Path(__file__).with_name('check_insights_visual.py')),'--theme',args.theme,'--language',args.language,'--scale',str(args.scale),'--size',args.size]
if not args.fixture:command.append('--live')
if args.exercise:command.append('--exercise')
raise SystemExit(subprocess.call(command))
