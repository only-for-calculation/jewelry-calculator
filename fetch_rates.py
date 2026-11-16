"""Retrieve and strictly validate Housho's public 37-row price table.
Run only after confirming automated access is permitted by the site operator.
"""
import json, re, urllib.request, datetime, pathlib
from bs4 import BeautifulSoup
URL='https://www.housho-diamond.co.jp/'
OUT=pathlib.Path(__file__).parent/'rates.json'
KEYS=['金インゴット','K24','K22','K21.6','K20','K18','K14','K10','K9','K18WG','Pt1000インゴット','Pt1000','Pt950','Pt900','Pt900（ダイヤ付き）','Pt850','Pt850（ダイヤ付き）','SV1000','SV925']
KEYS += [f'K18/Pt{pt}（{n}:{10-n}）' for pt in (900,850) for n in range(9,0,-1)]
assert len(KEYS)==37

def norm(s):
    return re.sub(r'\s+','',s).upper().replace('ＷＧ','WG').replace('ＰＴ','PT').replace('ＳＶ','SV')

def convert(label):
    x=norm(label).replace('（純銀）','')
    if '金インゴット' in label: return '金インゴット'
    if 'インゴット' in label and 'PT1000' in x:return 'Pt1000インゴット'
    if x=='WGK18':return 'K18WG'
    if x.startswith('K18') and 'PT' in x:
        m=re.search(r'PT(900|850).*?（([1-9]):([1-9])）',x)
        if m:return f'K18/Pt{m.group(1)}（{m.group(2)}:{m.group(3)}）'
    if x.startswith('PT'):
        m=re.match(r'PT(1000|950|900|850)',x)
        if m:return 'Pt'+m.group(1)+('（ダイヤ付き）' if 'ダイヤモンド付き' in label else '')
    if x in ['SV1000','SV925']:return x
    if re.fullmatch(r'K(?:24|22|21\.6|20|18|14|10|9)',x):return x
    return None

req=urllib.request.Request(URL,headers={'User-Agent':'PersonalPriceChecker/1.0 (contact site operator before enabling)'})
with urllib.request.urlopen(req,timeout=25) as response:
    html=response.read(3_000_000)
soup=BeautifulSoup(html,'html.parser')
heading=soup.find(string=re.compile('本日の地金買取価格'))
if heading is None:raise ValueError('Price heading missing')
# Scope to text after price heading and before usage notes, avoiding unrelated price tables.
text=soup.get_text('\n',strip=True)
start=text.find('本日の地金買取価格')
end=text.find('ご利用上の注意点',start)
if start<0 or end<0:raise ValueError('Price table boundary missing')
section=text[start:end]
rows=[v.strip() for v in section.splitlines() if v.strip()]
prices={}
for i,label in enumerate(rows[:-1]):
    key=convert(label)
    if key and key in KEYS:
        following=rows[i+1]
        m=re.fullmatch(r'([0-9,]+)円',following)
        if m:
            value=int(m.group(1).replace(',',''))
            if not 1<=value<=100000:raise ValueError('Price outside plausible range: '+key)
            if key in prices:raise ValueError('Duplicate '+key)
            prices[key]=value
if set(prices)!=set(KEYS):raise ValueError('Missing/unexpected grades: '+str(sorted(set(KEYS)-set(prices))))
match=re.search(r'20\d\d/\d\d?/\d\d?\([^)]*\)\s+\d\d?:\d\d',section)
if not match:raise ValueError('Publication timestamp missing')
now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
payload={'source':URL,'published_at':match.group(),'checked_at':now.isoformat(timespec='seconds'),'rates':prices}
OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Validated 37 grades, publication:',match.group())
