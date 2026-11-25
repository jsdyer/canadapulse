from datetime import date
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from refresh import parse_country,parse_series,valid_config
class RefreshTests(unittest.TestCase):
 def test_country_identity_and_upper_bounds(self):
  raw={'items':[{'country':'CA','year':'2026','month':'01','day':'02','articles':[{'article':f'Article_{i}','project':'en.wikipedia','rank':i+1,'views_ceil':100+i} for i in range(12)]}]}
  rows=parse_country(raw,date(2026,1,2),20)['articles'];self.assertEqual(rows[0]['views_ceil'],100)
  with self.assertRaises(ValueError):parse_country(raw,date(2026,1,3),20)
 def test_incomplete_series_is_rejected(self):
  raw={'items':[{'timestamp':'2026010100','views':0}]}
  with self.assertRaises(ValueError):parse_series(raw,date(2026,1,1),date(2026,1,2))
  self.assertEqual(parse_series(raw,date(2026,1,1),date(2026,1,1))[0]['views'],0)
 def test_negative_and_duplicate_series_rejected(self):
  for items in [[{'timestamp':'2026010100','views':-1}],[{'timestamp':'2026010100','views':1}]*2]:
   with self.assertRaises(ValueError):parse_series({'items':items},date(2026,1,1),date(2026,1,1))
 def test_configuration_can_expand(self):
  config=json.loads((Path(__file__).resolve().parents[1]/'config/sources.json').read_text());config['topics'].append({'title':'Chebucto Community Net','project':'en.wikipedia','group':'Networks'});self.assertIs(valid_config(config),config)
 def test_bad_project_rejected(self):
  config={'country':'CA','history_days':2,'baseline_days':7,'country_limit':20,'topics':[{'title':'A','project':'evil.example','group':'A'}]}
  with self.assertRaises(ValueError):valid_config(config)
