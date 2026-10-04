import base64, io, os
from datetime import date, timedelta
import pandas as pd
import requests
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

load_dotenv()
API = os.getenv('LEDGERBITE_API_URL', 'https://ledgerbite.onrender.com')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGO = os.path.join(ROOT, 'assets', 'ledgerbite_logo.png')

st.set_page_config(page_title='LedgerBite',page_icon='🍴',layout='wide',initial_sidebar_state='expanded')
st.markdown('''<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Playfair+Display:wght@600;700&display=swap');
:root{--brown:#3B2717;--orange:#D65F32;--sage:#9CAA92;--cream:#F8F5EF;--ink:#201B17;--muted:#746C64;--line:#E7E0D7}
html,body,[class*="css"]{font-family:'DM Sans',sans-serif}.stApp{background:var(--cream)}.block-container{max-width:1280px;padding-top:1.2rem}
[data-testid="stSidebar"]{background:var(--brown)}[data-testid="stSidebar"] *{color:#FFF9F1!important}
.lb-brand{margin:0 0 18px}.lb-brand img{width:280px;max-width:80%;background:#fff;border-radius:14px}.eyebrow{color:var(--orange);font-size:.76rem;font-weight:700;letter-spacing:.13em;text-transform:uppercase}.hero{color:var(--brown);font-family:'Playfair Display',serif;font-size:2.25rem;line-height:1.12;margin:.2rem 0 .35rem}.sub{color:var(--muted);margin-bottom:1.2rem}
.kpi{background:#fff;border:1px solid var(--line);border-radius:18px;padding:17px 18px;min-height:112px;box-shadow:0 4px 18px rgba(59,39,23,.04)}.kl{color:var(--muted);font-size:.8rem;font-weight:600}.kv{color:var(--brown);font-size:1.55rem;font-weight:700;margin-top:7px}.accent{color:var(--orange)}
.card{background:#fff;border:1px solid var(--line);border-radius:18px;padding:18px;box-shadow:0 4px 18px rgba(59,39,23,.04)}.ct{color:var(--brown);font-weight:700;font-size:1.05rem}.cn{color:var(--muted);font-size:.88rem}
.alert-red{background:#fff1ed;border:1px solid #e7a38e;border-radius:16px;padding:16px;color:#7d2f1d}.alert-yellow{background:#fff8e8;border:1px solid #e7cc8c;border-radius:16px;padding:16px;color:#735313}.alert-green{background:#eef5eb;border:1px solid #b9ceb0;border-radius:16px;padding:16px;color:#385a31}
.recipe-loss{background:#fff1ed;border-left:5px solid #b63c25;border-radius:12px;padding:12px 15px;margin-bottom:8px}.recipe-profit{background:#eef5eb;border-left:5px solid #66845b;border-radius:12px;padding:12px 15px;margin-bottom:8px}.recipe-low{background:#fff8e8;border-left:5px solid #c4932d;border-radius:12px;padding:12px 15px;margin-bottom:8px}
div[data-testid="stButton"]>button,div[data-testid="stFormSubmitButton"]>button{background:var(--orange);color:white;border:0;border-radius:10px;font-weight:700;min-height:42px}div[data-testid="stButton"]>button:hover,div[data-testid="stFormSubmitButton"]>button:hover{background:var(--brown);color:white}
.stTextInput input,.stNumberInput input,.stDateInput input,.stTextArea textarea,.stSelectbox div[data-baseweb="select"]>div{border-radius:10px!important}
[data-testid="stFileUploader"]{background:#fff;border:1px dashed var(--sage);border-radius:14px;padding:10px}
.auth-wrap{max-width:520px;margin:5vh auto}.auth-card{background:#fff;border:1px solid var(--line);border-radius:24px;padding:30px;box-shadow:0 10px 35px rgba(59,39,23,.08)}
@media(max-width:700px){.block-container{padding-left:.8rem;padding-right:.8rem}.hero{font-size:1.8rem}.lb-brand img{width:220px}}
</style>''',unsafe_allow_html=True)


def headers():
    token=st.session_state.get('token'); return {'Authorization':f'Bearer {token}'} if token else {}

def _request(method,path,**kwargs):
    try:
        r=requests.request(method,API+path,headers=headers(),timeout=90,**kwargs)
        r.raise_for_status(); return r
    except requests.HTTPError as e:
        if 'r' in locals() and r.status_code==401:
            st.session_state.clear(); st.rerun()
        try: st.error(r.json().get('detail',str(e)))
        except Exception: st.error(str(e))
    except Exception as e: st.error('Backend is not running: '+str(e))
    return None

def public_post(path,data):
    try:
        r=requests.post(API+path,data=data,timeout=30); r.raise_for_status(); return r.json()
    except requests.HTTPError as e:
        try: st.error(r.json().get('detail',str(e)))
        except Exception: st.error(str(e))
    except Exception as e: st.error('Backend is not running: '+str(e))
    return None

def get(path,params=None):
    r=_request('GET',path,params=params)
    return r.json() if r else None

def post(path,data=None,files=None,json=None):
    r=_request('POST',path,data=data,files=files,json=json); return r.json() if r else None

def put(path,data=None,json=None):
    r=_request('PUT',path,data=data,json=json); return r.json() if r else None

def delete(path): return bool(_request('DELETE',path))

def money(v): return f'₹{float(v):,.2f}'

def kpi(label,value,accent=False):
    cls='accent' if accent else ''; st.markdown(f'<div class="kpi"><div class="kl">{label}</div><div class="kv {cls}">{value}</div></div>',unsafe_allow_html=True)

def img_data(path):
    with open(path,'rb') as f: return base64.b64encode(f.read()).decode()

def unit_options(): return ['g','kg','ml','L','pcs','pack','box']
def pdf_money(v): return f'Rs. {float(v):,.2f}'

if 'token' not in st.session_state: st.session_state.token=None
if 'user' not in st.session_state: st.session_state.user=None

# AUTH
if not st.session_state.token:
    st.markdown('<div class="auth-wrap">',unsafe_allow_html=True); st.image(LOGO,width=260); st.markdown('<div class="auth-card">',unsafe_allow_html=True)
    st.markdown('<div class="eyebrow">Simple accounting for food operators</div>',unsafe_allow_html=True); st.markdown('<div class="hero">Welcome to LedgerBite</div>',unsafe_allow_html=True); st.markdown('<div class="sub">Receipts, ingredients, dishes, shifts, expenses and profit in one place.</div>',unsafe_allow_html=True)
    mode=st.radio('Account',['Login','Register'],horizontal=True,label_visibility='collapsed')
    if mode=='Login':
        with st.form('login_form'):
            email=st.text_input('Email'); password=st.text_input('Password',type='password'); ok=st.form_submit_button('Login',type='primary',use_container_width=True)
        if ok:
            if not email.strip() or not password: st.warning('Enter your email and password.')
            else:
                r=public_post('/login',{'email':email,'password':password})
                if r: st.session_state.token=r['token']; st.session_state.user=r['user']; st.rerun()
    else:
        with st.form('register_form'):
            name=st.text_input('Your name'); email=st.text_input('Email'); password=st.text_input('Password',type='password'); confirm=st.text_input('Confirm password',type='password'); ok=st.form_submit_button('Create account',type='primary',use_container_width=True)
        if ok:
            if not name.strip() or not email.strip(): st.warning('Enter your name and email.')
            elif password!=confirm: st.warning('Passwords do not match.')
            elif len(password)<6: st.warning('Password must be at least 6 characters.')
            else:
                r=public_post('/register',{'name':name,'email':email,'password':password})
                if r: st.session_state.token=r['token']; st.session_state.user=r['user']; st.rerun()
    st.markdown('</div></div>',unsafe_allow_html=True); st.stop()

with st.sidebar:
    st.image(LOGO,use_container_width=True); st.caption('Micro-accounting for food operators'); st.divider(); user=st.session_state.user or {}; st.markdown(f'**Hi, {user.get("name","there")}**')
    page=st.radio('Workspace',['Overview','Receipt Scanner','Ingredients','Shift Cashout','Expenses','Recipe Costing','Reports'],label_visibility='collapsed'); st.divider(); location=st.text_input('Business location','Main')
    if st.button('Log out',use_container_width=True):
        try: requests.post(API+'/logout',headers=headers(),timeout=10)
        except Exception: pass
        st.session_state.clear(); st.rerun()
    st.caption('Local-first • AI optional • Private account data')

st.markdown(f'<div class="lb-brand"><img src="data:image/png;base64,{img_data(LOGO)}"/></div>',unsafe_allow_html=True)

# OVERVIEW
if page=='Overview':
    st.markdown('<div class="eyebrow">Daily command center</div>',unsafe_allow_html=True); st.markdown('<div class="hero">Know your numbers before you close the counter.</div>',unsafe_allow_html=True); st.markdown('<div class="sub">Your sales, expenses, dishes and pricing risks in one simple view.</div>',unsafe_allow_html=True)
    a,b=st.columns(2); start=a.date_input('From',date.today()-timedelta(days=6)); end=b.date_input('To',date.today()); d=get('/dashboard',{'start':str(start),'end':str(end),'location':location})
    if d:
        if d.get('loss_count',0):
            st.markdown(f'<div class="alert-red"><b>⚠️ Pricing warning: {d["loss_count"]} dish(es) are selling below their ingredient cost.</b><br>Open Recipe Costing to review and update selling prices.</div>',unsafe_allow_html=True); st.write('')
        elif d.get('price_alerts'):
            st.markdown('<div class="alert-yellow"><b>⚠️ Ingredient prices have changed.</b><br>Some recipe costs may have moved. Review the pricing insights below.</div>',unsafe_allow_html=True); st.write('')
        cols=st.columns(5)
        for col,label,val,acc in zip(cols,['Sales','COGS','Expenses','Net Profit','COGS %'],[money(d['sales']),money(d['cogs']),money(d['expenses']),money(d['net_profit']),f"{d['cogs_pct']:.1f}%"],[0,0,0,1,0]):
            with col:kpi(label,val,bool(acc))
        st.write('')
        left,right=st.columns([1.5,1])
        with left:
            st.markdown('<div class="ct">Your dishes</div>',unsafe_allow_html=True)
            recipes=d.get('recipes',[])
            if recipes:
                for r in recipes:
                    cls='recipe-loss' if r['status']=='loss' else ('recipe-low' if r['status']=='low' else 'recipe-profit'); icon='🔴' if r['status']=='loss' else ('🟡' if r['status']=='low' else '🟢')
                    st.markdown(f'<div class="{cls}"><b>{icon} {r["name"]}</b> &nbsp; Selling {money(r["selling_price"])} &nbsp; Cost {money(r["cost"])} &nbsp; <b>{money(r["profit"])} profit</b> &nbsp; {r["margin_pct"]:.1f}% margin</div>',unsafe_allow_html=True)
            else: st.info('Create your first dish in Recipe Costing to see profitability here.')
        with right:
            st.markdown('<div class="ct">Pricing & ingredient insights</div>',unsafe_allow_html=True)
            insights=[]
            loss=[r for r in d.get('recipes',[]) if r['status']=='loss']
            low=[r for r in d.get('recipes',[]) if r['status']=='low']
            if loss:
                insights.append('🔴 '+', '.join(x['name'] for x in loss[:3])+' are currently loss-making.')
            if low:
                insights.append('🟡 '+', '.join(x['name'] for x in low[:3])+' have margins below 20%.')
            for x in d.get('price_alerts',[])[:4]:
                arrow='increased' if x['change_pct']>0 else 'decreased'; insights.append(f'📈 {x["name"]} cost {arrow} {abs(x["change_pct"]):.1f}% to {money(x["current_cost"])} / {x["unit"]}.')
            if not insights: insights=['🟢 No pricing issues detected in the current data.']
            for s in insights: st.markdown(f'<div class="card" style="margin-bottom:8px">{s}</div>',unsafe_allow_html=True)
        st.write('')
        x,y=st.columns([1.6,1]); trend=pd.DataFrame(d['trend'])
        with x:
            st.markdown('<div class="ct">Sales & profit trend</div>',unsafe_allow_html=True)
            if not trend.empty:
                trend['profit']=trend['sales']-trend['cogs']; fig=px.line(trend,x='cash_date',y=['sales','profit'],markers=True); fig.update_layout(margin=dict(l=10,r=10,t=20,b=10),paper_bgcolor='white',plot_bgcolor='white',legend=dict(orientation='h',y=1.12)); st.plotly_chart(fig,use_container_width=True)
            else: st.info('No shift cashouts yet.')
        with y:
            st.markdown('<div class="ct">Expense mix</div>',unsafe_allow_html=True); cats=pd.DataFrame(d['expense_categories'])
            if not cats.empty:
                fig=px.pie(cats,names='category',values='amount',hole=.55); fig.update_layout(margin=dict(l=0,r=0,t=15,b=0),paper_bgcolor='white'); st.plotly_chart(fig,use_container_width=True)
            else: st.info('No expenses logged in this period.')

# RECEIPTS
elif page=='Receipt Scanner':
    st.markdown('<div class="eyebrow">P0 • Core feature</div>',unsafe_allow_html=True); st.markdown('<div class="hero">Scan receipts. Build your ingredient prices.</div>',unsafe_allow_html=True); st.markdown('<div class="sub">Every scanned ingredient is saved. When the same ingredient appears again, its current cost is updated from the latest receipt.</div>',unsafe_allow_html=True)
    a,b=st.columns([1.35,1]); uploaded=a.file_uploader('Receipt image',type=['png','jpg','jpeg','webp']); b.markdown('<div class="card"><div class="ct">What gets saved</div><div class="cn">Vendor • Date • Total • Ingredient lines • Quantity • Unit • Cost<br><br>OCR runs locally. You can correct saved ingredients from the Ingredients page.</div></div>',unsafe_allow_html=True)
    if uploaded:
        a.image(uploaded,caption='Receipt preview',use_container_width=True)
        if st.button('Scan & save receipt',type='primary',use_container_width=True):
            r=post('/receipts',data={'location':location},files={'file':(uploaded.name,uploaded.getvalue(),uploaded.type)})
            if r:
                st.success('Receipt saved and ingredient prices updated.'); cs=st.columns(4)
                for c,l,v,ac in zip(cs,['Vendor','Date','Total','Category'],[r['vendor'],r['receipt_date'],money(r['total']),r['category']],[0,0,1,0]):
                    with c:kpi(l,v,bool(ac))
                if r.get('items'):
                    st.markdown('**Ingredients detected from this receipt**'); st.dataframe(pd.DataFrame(r['items']),use_container_width=True,hide_index=True)
                else: st.warning('No ingredient lines were confidently detected. You can add the ingredients manually from the Ingredients page.')
                with st.expander('View raw OCR text'): st.text(r.get('raw_text',''))
    st.divider(); st.markdown('<div class="ct">Recent receipts</div>',unsafe_allow_html=True); rs=get('/receipts') or []
    for r in rs:
        with st.expander(f"#{r['id']} • {r['vendor'] or 'Unknown vendor'} • {money(r['total'])}"):
            if r.get('items'): st.dataframe(pd.DataFrame(r['items']),use_container_width=True,hide_index=True)
            with st.form(f"receipt_edit_{r['id']}"):
                c1,c2=st.columns(2); vendor=c1.text_input('Vendor',r.get('vendor','')); rdate=c2.text_input('Date',r.get('receipt_date','')); total=c1.number_input('Total ₹',value=float(r.get('total') or 0),min_value=0.0,step=10.0,key=f"receipt_total_{r['id']}"); category=c2.text_input('Category',r.get('category','')); loc=st.text_input('Location',r.get('location','Main')); save=st.form_submit_button('Save changes',type='primary')
            if save and put(f"/receipts/{r['id']}",{'vendor':vendor,'receipt_date':rdate,'total':total,'category':category,'location':loc}): st.success('Receipt updated.'); st.rerun()
            if st.button('Delete receipt',key=f"del_receipt_{r['id']}"):
                if delete(f"/receipts/{r['id']}"): st.success('Receipt deleted.'); st.rerun()

# INGREDIENTS
elif page=='Ingredients':
    st.markdown('<div class="eyebrow">Ingredient price book</div>',unsafe_allow_html=True); st.markdown('<div class="hero">Know the current cost of what you buy.</div>',unsafe_allow_html=True); st.markdown('<div class="sub">Receipt scans update these prices automatically. You can also add, edit or delete ingredients yourself.</div>',unsafe_allow_html=True)
    with st.form('add_ingredient'):
        st.markdown('**Add ingredient manually**'); a,b,c=st.columns([2,1,1]); name=a.text_input('Ingredient name'); qty=b.number_input('Reference quantity',min_value=.001,value=1.0,step=.1,key='add_ingredient_qty'); unit=c.selectbox('Unit',unit_options(),key='add_ingredient_unit'); cost=st.number_input('Current cost for that quantity ₹',min_value=0.0,step=.1,key='add_ingredient_cost'); ok=st.form_submit_button('Add ingredient',type='primary')
    if ok:
        r=post('/ingredients',json={'name':name,'quantity':qty,'unit':unit,'current_cost':cost})
        if r: st.success('Ingredient added.'); st.rerun()
    st.divider(); search=st.text_input('🔎 Search ingredients',placeholder='Chicken, tomato, bun...'); rs=get('/ingredients') or []
    if search.strip(): rs=[x for x in rs if search.lower() in x['name'].lower()]
    st.markdown(f'**{len(rs)} ingredient(s)**')
    for r in rs:
        change=r.get('change_pct') or 0; change_text=f" • {'↑' if change>0 else '↓'} {abs(change):.1f}%" if change else ''
        with st.expander(f"{r['name']} • {money(r['current_cost'])}/{r['unit']}{change_text}"):
            c1,c2=st.columns(2)
            with st.form(f"ingredient_edit_{r['id']}"):
                n=c1.text_input('Ingredient name',r['name']); q=c1.number_input('Reference quantity',value=float(r['quantity']),min_value=.001,step=.1,key=f"ingredient_qty_{r['id']}"); u=c2.selectbox('Unit',unit_options(),index=unit_options().index(r['unit']) if r['unit'] in unit_options() else 4,key=f'ingredient_unit_{r["id"]}'); cc=c2.number_input('Current cost ₹',value=float(r['current_cost']),min_value=0.0,step=.1,key=f"ingredient_cost_{r['id']}"); save=st.form_submit_button('Save changes',type='primary')
            if save and put(f"/ingredients/{r['id']}",json={'name':n,'quantity':q,'unit':u,'current_cost':cc}): st.success('Ingredient updated.'); st.rerun()
            if st.button('Delete ingredient',key=f"del_ing_{r['id']}"):
                if delete(f"/ingredients/{r['id']}"): st.success('Ingredient deleted.'); st.rerun()
            hist=get(f"/ingredients/{r['id']}/history") or []
            if hist:
                st.markdown('**Price history**'); st.dataframe(pd.DataFrame(hist)[['recorded_at','cost','unit','vendor','receipt_date']].rename(columns={'recorded_at':'Recorded','cost':'Cost','unit':'Unit','vendor':'Vendor','receipt_date':'Receipt date'}),use_container_width=True,hide_index=True)

# CASHOUT
elif page=='Shift Cashout':
    st.markdown('<div class="eyebrow">P0 • Core feature</div>',unsafe_allow_html=True); st.markdown('<div class="hero">Close your shift in 30 seconds.</div>',unsafe_allow_html=True); st.markdown('<div class="sub">Enter cash, UPI/POS and COGS. LedgerBite calculates the shift result.</div>',unsafe_allow_html=True)
    with st.form('cash'):
        d=st.date_input('Business date',date.today()); a,b,c=st.columns(3); cash=a.number_input('Cash collected ₹',min_value=0.,step=100.,key='new_cashout_cash'); digital=b.number_input('UPI / POS ₹',min_value=0.,step=100.,key='new_cashout_digital'); other=c.number_input('Other sales ₹',min_value=0.,step=100.,key='new_cashout_other'); cogs=st.number_input('COGS ₹',min_value=0.,step=100.,key='new_cashout_cogs'); notes=st.text_input('Shift note'); ok=st.form_submit_button('Close shift',type='primary',use_container_width=True)
    if ok:
        r=post('/cashouts',data={'cash_date':str(d),'cash_sales':cash,'digital_sales':digital,'other_sales':other,'cogs':cogs,'notes':notes,'location':location})
        if r:
            st.success('Shift saved successfully.'); cs=st.columns(3)
            for col,label,val,accent in zip(cs,['Total sales','COGS','Gross profit'],[cash+digital+other,cogs,cash+digital+other-cogs],[False,False,True]):
                with col:kpi(label,money(val),accent)
    st.divider(); rs=get('/cashouts') or []
    for r in rs:
        with st.expander(f"{r['cash_date']} • {money(float(r['cash_sales'])+float(r['digital_sales'])+float(r['other_sales']))} sales"):
            with st.form(f"cash_edit_{r['id']}"):
                c1,c2=st.columns(2); rd=c1.text_input('Date',r['cash_date']); rc=c1.number_input('Cash ₹',value=float(r['cash_sales']),min_value=0.0,step=100.0,key=f"cashout_cash_{r['id']}"); rdigital=c2.number_input('Digital ₹',value=float(r['digital_sales']),min_value=0.0,step=100.0,key=f"cashout_digital_{r['id']}"); rother=c2.number_input('Other ₹',value=float(r['other_sales']),min_value=0.0,step=100.0,key=f"cashout_other_{r['id']}"); rcogs=c1.number_input('COGS ₹',value=float(r['cogs']),min_value=0.0,step=100.0,key=f"cashout_cogs_{r['id']}"); rnotes=c2.text_input('Notes',r.get('notes','')); rloc=st.text_input('Location',r.get('location','Main'),key=f"recipe_location_{r['id']}"); save=st.form_submit_button('Save changes',type='primary')
            if save and put(f"/cashouts/{r['id']}",{'cash_date':rd,'cash_sales':rc,'digital_sales':rdigital,'other_sales':rother,'cogs':rcogs,'notes':rnotes,'location':rloc}): st.success('Cashout updated.'); st.rerun()
            if st.button('Delete cashout',key=f"del_cash_{r['id']}"):
                if delete(f"/cashouts/{r['id']}"): st.success('Cashout deleted.'); st.rerun()

# EXPENSES
elif page=='Expenses':
    st.markdown('<div class="eyebrow">Fast operational logging</div>',unsafe_allow_html=True); st.markdown('<div class="hero">Log an expense before you forget it.</div>',unsafe_allow_html=True); st.markdown('<div class="sub">Shift cashout and expense tracking stay simple.</div>',unsafe_allow_html=True)
    with st.form('expense'):
        d=st.date_input('Date',date.today()); desc=st.text_input('What did you pay for?',placeholder='Ice delivery'); amt=st.number_input('Amount ₹',min_value=0.,step=10.,key='new_expense_amount'); cat=st.selectbox('Category',['Produce','Dairy','Meat','Packaging','Beverages','Utilities','Transport','Other'],key='new_expense_category'); ok=st.form_submit_button('Save expense',type='primary',use_container_width=True)
    if ok:
        if not desc.strip() or amt<=0: st.warning('Enter a description and a positive amount.')
        else:
            r=post('/expenses',data={'expense_date':str(d),'description':desc,'amount':amt,'category':cat,'location':location})
            if r: st.success('Expense saved.'); st.rerun()
    st.divider(); rs=get('/expenses') or []
    for r in rs:
        with st.expander(f"#{r['id']} • {r['description']} • {money(r['amount'])}"):
            with st.form(f"expense_edit_{r['id']}"):
                c1,c2=st.columns(2); rd=c1.text_input('Date',r['expense_date']); rdesc=c1.text_input('Description',r['description']); ramt=c2.number_input('Amount ₹',value=float(r['amount']),min_value=0.0,step=10.0,key=f"expense_amount_{r['id']}"); cats=['Produce','Dairy','Meat','Packaging','Beverages','Utilities','Transport','Other']; rcat=c2.selectbox('Category',cats,index=cats.index(r['category']) if r.get('category') in cats else len(cats)-1,key=f'expense_category_{r["id"]}'); rloc=st.text_input('Location',r.get('location','Main'),key=f"recipe_location_{r['id']}"); save=st.form_submit_button('Save changes',type='primary')
            if save and put(f"/expenses/{r['id']}",{'expense_date':rd,'description':rdesc,'amount':ramt,'category':rcat,'location':rloc}): st.success('Expense updated.'); st.rerun()
            if st.button('Delete expense',key=f"del_exp_{r['id']}"):
                if delete(f"/expenses/{r['id']}"): st.success('Expense deleted.'); st.rerun()

# RECIPES
elif page=='Recipe Costing':
    st.markdown('<div class="eyebrow">P0 • Main intelligence feature</div>',unsafe_allow_html=True); st.markdown('<div class="hero">Know what every dish really costs.</div>',unsafe_allow_html=True); st.markdown('<div class="sub">Select ingredients from your saved price book, enter the quantity used, and LedgerBite calculates cost, profit, margin and pricing insights.</div>',unsafe_allow_html=True)
    ingredients=get('/ingredients') or []; ing_map={x['id']:x for x in ingredients}; names=[x['name'] for x in ingredients]
    with st.form('recipe_new'):
        name=st.text_input('Dish name',placeholder='Chicken Burger'); price=st.number_input('Selling price ₹',min_value=0.,step=5.,key='new_recipe_price')
        st.markdown('**Ingredients**')
        items=[]
        for i in range(8):
            a,b,c,d=st.columns([2.3,1,1,1.1]); options=['— Select ingredient —']+names+['✏️ Manual ingredient']
            choice=a.selectbox('Ingredient',options,key=f'ri_name_{i}'); qty=b.number_input('Quantity',min_value=0.,step=.1,key=f'ri_qty_{i}'); unit=c.selectbox('Used unit',unit_options(),key=f'ri_unit_{i}')
            if choice=='✏️ Manual ingredient': manual=d.text_input('Manual name',key=f'ri_manual_{i}'); manual_cost=d.number_input('Cost/unit ₹',min_value=0.,step=.1,key=f'ri_cost_{i}');
            else: manual=''; manual_cost=0
            if choice not in ('— Select ingredient —','✏️ Manual ingredient') and qty>0:
                selected=next(x for x in ingredients if x['name']==choice); items.append({'ingredient_id':selected['id'],'ingredient_name':selected['name'],'quantity':qty,'unit':unit,'source':'ingredient'})
            elif choice=='✏️ Manual ingredient' and manual.strip() and qty>0:
                items.append({'ingredient_name':manual.strip(),'quantity':qty,'unit':unit,'unit_cost':manual_cost,'source':'manual'})
        ok=st.form_submit_button('Calculate & save recipe',type='primary',use_container_width=True)
    if ok:
        if not name.strip() or price<=0: st.warning('Enter a dish name and selling price.')
        elif not items: st.warning('Add at least one ingredient.')
        else:
            r=post('/recipes',json={'name':name,'selling_price':price,'items':items,'location':location})
            if r: st.success('Recipe saved.'); st.rerun()
    st.divider(); recipes=get('/recipes') or []
    for r in recipes:
        status=r['status']; icon='🔴' if status=='loss' else ('🟡' if status=='low' else '🟢')
        with st.expander(f"{icon} {r['name']} • Cost {money(r['cost'])} • Profit {money(r['margin'])} • {r['margin_pct']:.1f}%"):
            if status=='loss': st.markdown(f'<div class="alert-red"><b>Loss-making dish.</b> Selling price {money(r["selling_price"])} is below ingredient cost {money(r["cost"])} by {money(abs(r["margin"]))}.</div>',unsafe_allow_html=True)
            elif status=='low': st.markdown(f'<div class="alert-yellow"><b>Low margin.</b> Current gross margin is only {r["margin_pct"]:.1f}%.</div>',unsafe_allow_html=True)
            else: st.markdown(f'<div class="alert-green"><b>Profitable.</b> Gross profit is {money(r["margin"])} per dish.</div>',unsafe_allow_html=True)
            st.dataframe(pd.DataFrame(r['items'])[['ingredient_name','quantity','unit','unit_cost','source']].rename(columns={'ingredient_name':'Ingredient','quantity':'Qty','unit':'Unit','unit_cost':'Cost / used unit','source':'Source'}),use_container_width=True,hide_index=True)
            suggested=r['cost']/0.5 if r['cost'] else 0
            st.info(f'💡 Pricing insight: a 50% gross margin would require a selling price of about {money(suggested)}.' if suggested else '💡 Add ingredient costs to get a pricing recommendation.')
            with st.form(f"recipe_edit_{r['id']}"):
                rn=st.text_input('Dish name',r['name'],key=f"recipe_name_{r['id']}"); rp=st.number_input('Selling price ₹',value=float(r['selling_price']),min_value=0.0,step=5.0,key=f"recipe_price_{r['id']}"); rloc=st.text_input('Location',r.get('location','Main'),key=f"recipe_location_{r['id']}"); edit_items=[]; old=r.get('items',[])
                for i in range(8):
                    oi=old[i] if i<len(old) else {}; opts=['— Remove row —']+names+['✏️ Manual ingredient']; current_name=oi.get('ingredient_name',''); default=current_name if current_name in names else ('✏️ Manual ingredient' if oi.get('source')=='manual' else '— Remove row —'); idx=opts.index(default) if default in opts else 0
                    a,b,c,d=st.columns([2.3,1,1,1.1]); choice=a.selectbox('Ingredient',opts,index=idx,key=f"eri_name_{r['id']}_{i}"); qty=b.number_input('Qty',value=float(oi.get('quantity',0)),min_value=0.,step=.1,key=f"eri_qty_{r['id']}_{i}"); unit=c.selectbox('Used unit',unit_options(),index=unit_options().index(oi.get('unit','pcs')) if oi.get('unit') in unit_options() else 4,key=f"eri_unit_{r['id']}_{i}")
                    if choice=='✏️ Manual ingredient': mn=d.text_input('Manual name',value=current_name,key=f"eri_manual_{r['id']}_{i}"); mc=d.number_input('Cost/unit ₹',value=float(oi.get('unit_cost',0)),min_value=0.,step=.1,key=f"eri_cost_{r['id']}_{i}")
                    else: mn=''; mc=0
                    if choice not in ('— Remove row —','✏️ Manual ingredient') and qty>0:
                        selected=next(x for x in ingredients if x['name']==choice); edit_items.append({'ingredient_id':selected['id'],'ingredient_name':selected['name'],'quantity':qty,'unit':unit,'source':'ingredient'})
                    elif choice=='✏️ Manual ingredient' and mn.strip() and qty>0: edit_items.append({'ingredient_name':mn.strip(),'quantity':qty,'unit':unit,'unit_cost':mc,'source':'manual'})
                save=st.form_submit_button('Save recipe changes',type='primary')
            if save and put(f"/recipes/{r['id']}",json={'name':rn,'selling_price':rp,'items':edit_items,'location':rloc}): st.success('Recipe updated.'); st.rerun()
            if st.button('Delete recipe',key=f"del_recipe_{r['id']}"):
                if delete(f"/recipes/{r['id']}"): st.success('Recipe deleted.'); st.rerun()

# REPORTS
elif page=='Reports':
    st.markdown('<div class="eyebrow">P1 • Reporting</div>',unsafe_allow_html=True); st.markdown('<div class="hero">Your numbers, ready to share.</div>',unsafe_allow_html=True); st.markdown('<div class="sub">Download dish costing, ingredient prices, expenses and shift cashouts.</div>',unsafe_allow_html=True)
    start=st.date_input('From',date.today()-timedelta(days=6)); end=st.date_input('To',date.today()); d=get('/dashboard',{'start':str(start),'end':str(end),'location':location}); recipes=get('/recipes') or []
    if d:
        st.markdown('### Dish profitability')
        if recipes:
            table=pd.DataFrame([{'Dish':r['name'],'Selling Price':r['selling_price'],'Cost to Make':r['cost'],'Gross Profit':r['margin'],'Margin %':r['margin_pct']} for r in recipes]); st.dataframe(table.style.format({'Selling Price':'₹{:,.2f}','Cost to Make':'₹{:,.2f}','Gross Profit':'₹{:,.2f}','Margin %':'{:.1f}%'}),use_container_width=True,hide_index=True)
        else: st.info('No recipes yet.')
        b=io.BytesIO(); pdf=canvas.Canvas(b,pagesize=A4); w,h=A4; pdf.setFillColorRGB(.23,.15,.09); pdf.setFont('Helvetica-Bold',22); pdf.drawString(42,h-55,'LedgerBite'); pdf.setFillColorRGB(.84,.37,.20); pdf.setFont('Helvetica-Bold',10); pdf.drawString(42,h-75,'BUSINESS & RECIPE REPORT'); pdf.setFillColorRGB(.25,.23,.21); pdf.setFont('Helvetica',10); pdf.drawString(42,h-98,f'Period: {start} to {end}'); y=h-135
        for label,val in [('Sales',d['sales']),('COGS',d['cogs']),('Expenses',d['expenses']),('Net Profit',d['net_profit'])]: pdf.setFont('Helvetica-Bold',11); pdf.drawString(42,y,label); pdf.setFont('Helvetica',11); pdf.drawRightString(w-42,y,pdf_money(val)); y-=22
        y-=8; pdf.setFont('Helvetica-Bold',12); pdf.drawString(42,y,'Dish Costing'); y-=20; pdf.setFont('Helvetica',9)
        for r in recipes[:20]:
            line=f"{r['name'][:28]} | Sell {pdf_money(r['selling_price'])} | Cost {pdf_money(r['cost'])} | Profit {pdf_money(r['margin'])} | {r['margin_pct']:.1f}%"; pdf.drawString(42,y,line); y-=15
            if y<60: pdf.showPage(); y=h-55
        pdf.save(); b.seek(0)
        c1,c2,c3=st.columns(3); c1.download_button('Download PDF report',b.getvalue(),'ledgerbite_report.pdf','application/pdf',use_container_width=True)
        def download(path,name,label):
            try:
                rr=requests.get(API+path,headers=headers(),timeout=30); rr.raise_for_status(); st.download_button(label,rr.content,name,'text/csv',use_container_width=True)
            except Exception: st.error('Could not generate '+label)
        with c2: download('/export/recipes.csv','ledgerbite_recipe_costing.csv','Download dish costing CSV')
        with c3: download('/export/full.csv','ledgerbite_full.csv','Download full CSV')
        c4,c5=st.columns(2)
        with c4: download('/export/expenses.csv','ledgerbite_expenses.csv','Download expenses CSV')
        with c5: download('/export/cashouts.csv','ledgerbite_cashouts.csv','Download shift cashouts CSV')
        st.divider(); cs=st.columns(4)
        for col,label,val,acc in zip(cs,['Sales','COGS','Expenses','Net profit'],[d['sales'],d['cogs'],d['expenses'],d['net_profit']],[0,0,0,1]):
            with col:kpi(label,money(val),bool(acc))
