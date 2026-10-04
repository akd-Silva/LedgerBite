import os, re, json, requests
from datetime import datetime
import pytesseract
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
from dotenv import load_dotenv
load_dotenv()
if os.getenv('TESSERACT_CMD','').strip():
    pytesseract.pytesseract.tesseract_cmd = os.getenv('TESSERACT_CMD').strip()

WORDS={'Produce':['tomato','onion','potato','vegetable','fruit','lettuce','coriander','carrot'],
       'Dairy':['milk','cheese','butter','cream','curd','paneer','yogurt'],
       'Meat':['chicken','beef','mutton','fish','meat','egg','prawn'],
       'Packaging':['box','cup','container','bag','packaging','wrapper','foil','lid'],
       'Beverages':['water','juice','cola','coffee','tea','drink']}


def preprocess(im):
    im=ImageOps.autocontrast(im.convert('L')); im=im.resize((im.width*2,im.height*2)); im=ImageEnhance.Contrast(im).enhance(1.25)
    return im.filter(ImageFilter.SHARPEN)


def ocr_image(im):
    return pytesseract.image_to_string(preprocess(im), config='--psm 6')


def amounts(t):
    out=[]
    for x in re.findall(r'(?:₹|rs\.?|inr)?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)',t,re.I):
        try: out.append(float(x.replace(',','')))
        except: pass
    return out


def _clean_name(s):
    s=re.sub(r'[^A-Za-z0-9 &()\-./]', ' ', s)
    s=re.sub(r'\s+',' ',s).strip(' -.:')
    return s[:100]


def extract_items(t):
    """Best-effort local receipt line extraction.
    It deliberately avoids obvious totals/tax/payment lines. OCR is imperfect, so the UI lets users edit ingredients.
    """
    items=[]
    skip=re.compile(r'(total|subtotal|grand|amount due|tax|gst|invoice|receipt|change|cash|upi|card|payment|thank|date|phone|address|balance)',re.I)
    unit_re=re.compile(r'(\d+(?:\.\d+)?)\s*(kg|g|l|ml|pcs?|pack|box|dozen)\b',re.I)
    money_re=re.compile(r'(?:₹|rs\.?|inr|%|x|@)?\s*(\d+[\d,]*(?:\.\d{1,2})?)\s*$',re.I)
    for raw in t.splitlines():
        line=raw.strip()
        if not line or skip.search(line): continue
        m=money_re.search(line)
        if not m: continue
        price=float(m.group(1).replace(',',''))
        left=line[:m.start()].strip(' -:|')
        # Remove common quantity/price separators at the end of the name.
        q=1.0; unit='pcs'
        um=unit_re.search(left)
        if um:
            q=float(um.group(1)); unit=um.group(2).lower()
            if unit.startswith('pc'): unit='pcs'
            elif unit=='pack': unit='pack'
            elif unit=='box': unit='box'
            left=left[:um.start()].strip(' -:|')
        else:
            # e.g. "Tomatoes x 2 300" or "Tomatoes 2 300"
            qm=re.search(r'(?:x|@)?\s*(\d+(?:\.\d+)?)\s*$',left,re.I)
            if qm:
                q=float(qm.group(1)); left=left[:qm.start()].strip(' -:|')
        name=_clean_name(left)
        if len(name)<2 or re.fullmatch(r'[\d .,-]+',name): continue
        # Prevent OCR metadata from becoming ingredients.
        if any(k in name.lower() for k in ['supermarket','store','wholesale','mart']): continue
        unit_cost=price/q if q else price
        items.append({'ingredient_name':name,'quantity':q,'unit':unit,'total_price':price,'unit_cost':unit_cost})
    # Deduplicate same name while preserving first occurrence.
    out=[]; seen=set()
    for x in items:
        key=re.sub(r'\s+',' ',x['ingredient_name'].lower())
        if key not in seen:
            seen.add(key); out.append(x)
    return out[:50]


def extract(t):
    lines=[x.strip() for x in t.splitlines() if x.strip()]
    vendor='Unknown Vendor'
    for x in lines[:8]:
        if not any(w in x.lower() for w in ['invoice','receipt','tax','gst','total','date','bill','amount']) and not re.search(r'\d{2,}',x): vendor=x[:100]; break
    d=re.search(r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b',t)
    total=0
    for line in t.splitlines():
        if re.search(r'(grand\s+total|net\s+total|total\s+amount|total|amount\s+due)',line,re.I) and amounts(line): total=amounts(line)[-1]
    if not total and amounts(t): total=max(amounts(t))
    cat='Other'; low=t.lower()
    for k,ws in WORDS.items():
        if any(w in low for w in ws): cat=k; break
    return {'vendor':vendor,'date':d.group(1) if d else datetime.now().strftime('%Y-%m-%d'),'total':total,'category':cat,'items':extract_items(t)}


def ai_extract(t):
    key=os.getenv('AI_API_KEY','').strip()
    if not key:return None
    base=os.getenv('AI_BASE_URL','https://api.openai.com/v1').rstrip('/'); model=os.getenv('AI_MODEL','gpt-4o-mini')
    prompt='Extract vendor,date,total,category and receipt line items. Return ONLY JSON with vendor,date,total,category,items. items must be an array of {ingredient_name,quantity,unit,total_price,unit_cost}. Do not invent values.\n'+t[:12000]
    try:
        r=requests.post(base+'/chat/completions',headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},json={'model':model,'temperature':0,'messages':[{'role':'user','content':prompt}]},timeout=30); r.raise_for_status()
        s=r.json()['choices'][0]['message']['content'].strip(); s=re.sub(r'^```(?:json)?\s*|\s*```$','',s); return json.loads(s)
    except:return None


def process_receipt(im):
    t=ocr_image(im); result=extract(t); ai=ai_extract(t)
    if ai:
        for k in ('vendor','date','total','category','items'):
            if k in ai: result[k]=ai[k]
        result['source']='OCR + AI'
    else: result['source']='OCR + local rules'
    result['raw_text']=t; return result
