import csv, io, hashlib, hmac, secrets
from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException
from fastapi.responses import StreamingResponse
from PIL import Image
from .database import get_conn, init_db
from .ocr import process_receipt

app = FastAPI(title='LedgerBite API', version='2.0.0')
init_db()


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 120_000)
    return salt.hex() + ':' + digest.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split(':', 1)
        salt = bytes.fromhex(salt_hex)
        check = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 120_000).hex()
        return hmac.compare_digest(check, digest_hex)
    except Exception:
        return False


def current_user(authorization: str | None) -> dict:
    if not authorization or not authorization.lower().startswith('bearer '):
        raise HTTPException(status_code=401, detail='Please log in.')
    token = authorization.split(' ', 1)[1].strip()
    c = get_conn(); row = c.execute('''SELECT u.id,u.name,u.email FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?''',(token,)).fetchone(); c.close()
    if not row: raise HTTPException(status_code=401, detail='Session expired. Please log in again.')
    return dict(row)


def normalize_name(name):
    return ' '.join(str(name or '').strip().lower().split())


def unit_factor(unit):
    u=(unit or 'pcs').lower()
    return {'kg':1000,'g':1,'l':1000,'ml':1}.get(u,1)


def convert_unit_cost(cost, from_unit, to_unit):
    fu=(from_unit or 'pcs').lower(); tu=(to_unit or 'pcs').lower()
    if fu == tu: return float(cost)
    mass={'kg':1000,'g':1}; vol={'l':1000,'ml':1}
    if fu in mass and tu in mass:
        # cost per fu -> cost per tu
        return float(cost) * mass[tu] / mass[fu]
    if fu in vol and tu in vol:
        return float(cost) * vol[tu] / vol[fu]
    return float(cost)


def ingredient_dict(row): return dict(row)


def upsert_ingredient(c, user_id, item, receipt_id=None, source='receipt'):
    name=str(item.get('ingredient_name','')).strip()
    if not name: return None
    qty=max(float(item.get('quantity') or 1),0.000001)
    unit=str(item.get('unit') or 'pcs').lower()
    total=float(item.get('total_price') or 0)
    unit_cost=float(item.get('unit_cost') or (total/qty if qty else 0))
    norm=normalize_name(name)
    rows=c.execute('SELECT id,name,current_cost,unit FROM ingredients WHERE user_id=?',(user_id,)).fetchall()
    existing=None
    for r in rows:
        if normalize_name(r['name'])==norm: existing=r; break
    if existing:
        c.execute('UPDATE ingredients SET name=?,quantity=?,unit=?,current_cost=?,source=?,last_receipt_id=?,last_updated=CURRENT_TIMESTAMP WHERE id=?',
                  (name,qty,unit,unit_cost,source,receipt_id,existing['id']))
        iid=existing['id']
    else:
        cur=c.execute('INSERT INTO ingredients(user_id,name,quantity,unit,current_cost,source,last_receipt_id) VALUES(?,?,?,?,?,?,?)',
                      (user_id,name,qty,unit,unit_cost,source,receipt_id)); iid=cur.lastrowid
    c.execute('INSERT INTO ingredient_price_history(ingredient_id,receipt_id,cost,unit) VALUES(?,?,?,?)',(iid,receipt_id,unit_cost,unit))
    return iid


@app.get('/')
def root(): return {'product':'LedgerBite','status':'ok','docs':'/docs'}


@app.get('/health')
def health(): return {'status':'ok','product':'LedgerBite','version':'2.0.0'}


@app.post('/register')
def register(name: str=Form(...),email: str=Form(...),password: str=Form(...)):
    name,email=name.strip(),email.strip().lower()
    if not name or not email or len(password)<6: raise HTTPException(status_code=400,detail='Name, valid email and password of at least 6 characters are required.')
    c=get_conn()
    try:
        cur=c.execute('INSERT INTO users(name,email,password_hash) VALUES(?,?,?)',(name,email,hash_password(password))); uid=cur.lastrowid; token=secrets.token_urlsafe(32); c.execute('INSERT INTO sessions(token,user_id) VALUES(?,?)',(token,uid)); c.commit()
        return {'token':token,'user':{'id':uid,'name':name,'email':email}}
    except Exception as e:
        c.rollback()
        if 'UNIQUE constraint failed: users.email' in str(e): raise HTTPException(status_code=409,detail='An account with this email already exists.')
        raise HTTPException(status_code=400,detail='Could not create account.')
    finally:c.close()


@app.post('/login')
def login(email: str=Form(...),password: str=Form(...)):
    c=get_conn(); row=c.execute('SELECT * FROM users WHERE email=?',(email.strip().lower(),)).fetchone()
    if not row or not verify_password(password,row['password_hash']): c.close(); raise HTTPException(status_code=401,detail='Incorrect email or password.')
    token=secrets.token_urlsafe(32); c.execute('INSERT INTO sessions(token,user_id) VALUES(?,?)',(token,row['id'])); c.commit(); c.close(); return {'token':token,'user':{'id':row['id'],'name':row['name'],'email':row['email']}}


@app.post('/logout')
def logout(authorization: str|None=Header(default=None)):
    token=(authorization or '').replace('Bearer ','').replace('bearer ','').strip()
    if token:
        c=get_conn(); c.execute('DELETE FROM sessions WHERE token=?',(token,)); c.commit(); c.close()
    return {'ok':True}


@app.get('/me')
def me(authorization: str|None=Header(default=None)): return current_user(authorization)


@app.post('/receipts')
async def receipt(file: UploadFile=File(...),location: str=Form('Main'),authorization: str|None=Header(default=None)):
    user=current_user(authorization); x=process_receipt(Image.open(file.file)); c=get_conn()
    cur=c.execute('INSERT INTO receipts(vendor,receipt_date,total,category,raw_text,location,user_id) VALUES(?,?,?,?,?,?,?)',(str(x['vendor']),str(x['date']),float(x['total'] or 0),str(x['category']),x['raw_text'],location,user['id'])); rid=cur.lastrowid
    saved_items=[]
    for item in x.get('items',[]):
        iid=upsert_ingredient(c,user['id'],item,rid,'receipt')
        if iid:
            c.execute('INSERT INTO receipt_items(receipt_id,ingredient_name,quantity,unit,total_price,unit_cost) VALUES(?,?,?,?,?,?)',(rid,item['ingredient_name'],float(item.get('quantity') or 1),item.get('unit','pcs'),float(item.get('total_price') or 0),float(item.get('unit_cost') or 0))); saved_items.append(item)
    c.commit(); r=c.execute('SELECT * FROM receipts WHERE id=?',(rid,)).fetchone(); c.close(); return {**dict(r),'items':saved_items,'source':x['source']}


@app.get('/receipts')
def receipts(authorization: str|None=Header(default=None)):
    user=current_user(authorization); c=get_conn(); rs=c.execute('SELECT * FROM receipts WHERE user_id=? ORDER BY id DESC LIMIT 100',(user['id'],)).fetchall(); out=[]
    for r in rs:
        items=c.execute('SELECT * FROM receipt_items WHERE receipt_id=?',(r['id'],)).fetchall(); out.append({**dict(r),'items':[dict(i) for i in items]})
    c.close(); return out


@app.put('/receipts/{item_id}')
def update_receipt(item_id:int,vendor:str=Form(...),receipt_date:str=Form(...),total:float=Form(...),category:str=Form(...),location:str=Form('Main'),authorization:str|None=Header(default=None)):
    user=current_user(authorization); c=get_conn(); cur=c.execute('UPDATE receipts SET vendor=?,receipt_date=?,total=?,category=?,location=? WHERE id=? AND user_id=?',(vendor,receipt_date,total,category,location,item_id,user['id']))
    if cur.rowcount==0: c.close(); raise HTTPException(status_code=404,detail='Receipt not found.')
    c.commit(); row=c.execute('SELECT * FROM receipts WHERE id=?',(item_id,)).fetchone(); c.close(); return dict(row)


@app.delete('/receipts/{item_id}')
def delete_receipt(item_id:int,authorization:str|None=Header(default=None)):
    user=current_user(authorization); c=get_conn(); cur=c.execute('DELETE FROM receipts WHERE id=? AND user_id=?',(item_id,user['id'])); c.commit(); c.close()
    if cur.rowcount==0: raise HTTPException(status_code=404,detail='Receipt not found.')
    return {'ok':True}


# ---------------- INGREDIENTS ----------------
@app.get('/ingredients')
def ingredients(authorization:str|None=Header(default=None)):
    user=current_user(authorization); c=get_conn(); rs=c.execute('SELECT * FROM ingredients WHERE user_id=? ORDER BY name',(user['id'],)).fetchall(); out=[]
    for r in rs:
        prev=c.execute('SELECT cost FROM ingredient_price_history WHERE ingredient_id=? ORDER BY id DESC LIMIT 2',(r['id'],)).fetchall(); d=dict(r); d['previous_cost']=float(prev[1]['cost']) if len(prev)>1 else None; d['change_pct']=((d['current_cost']-d['previous_cost'])/d['previous_cost']*100) if d['previous_cost'] else 0; out.append(d)
    c.close(); return out


@app.post('/ingredients')
def add_ingredient(payload:dict,authorization:str|None=Header(default=None)):
    user=current_user(authorization); name=str(payload.get('name','')).strip(); cost=float(payload.get('current_cost',0)); qty=float(payload.get('quantity',1)); unit=payload.get('unit','pcs')
    if not name or cost<0 or qty<=0: raise HTTPException(status_code=400,detail='Ingredient name, positive quantity and non-negative cost are required.')
    c=get_conn()
    try:
        iid=upsert_ingredient(c,user['id'],{'ingredient_name':name,'quantity':qty,'unit':unit,'total_price':cost*qty,'unit_cost':cost},None,'manual'); c.commit(); row=c.execute('SELECT * FROM ingredients WHERE id=?',(iid,)).fetchone(); return dict(row)
    except Exception as e:
        c.rollback(); raise HTTPException(status_code=400,detail='Could not save ingredient. It may already exist.')
    finally:c.close()


@app.put('/ingredients/{item_id}')
def update_ingredient(item_id:int,payload:dict,authorization:str|None=Header(default=None)):
    user=current_user(authorization); name=str(payload.get('name','')).strip(); cost=float(payload.get('current_cost',0)); qty=float(payload.get('quantity',1)); unit=payload.get('unit','pcs')
    if not name or cost<0 or qty<=0: raise HTTPException(status_code=400,detail='Ingredient name, positive quantity and non-negative cost are required.')
    c=get_conn(); row=c.execute('SELECT * FROM ingredients WHERE id=? AND user_id=?',(item_id,user['id'])).fetchone()
    if not row: c.close(); raise HTTPException(status_code=404,detail='Ingredient not found.')
    c.execute('UPDATE ingredients SET name=?,quantity=?,unit=?,current_cost=?,source=?,last_updated=CURRENT_TIMESTAMP WHERE id=? AND user_id=?',(name,qty,unit,cost,'manual',item_id,user['id']))
    c.execute('INSERT INTO ingredient_price_history(ingredient_id,receipt_id,cost,unit) VALUES(?,?,?,?)',(item_id,None,cost,unit)); c.commit(); row=c.execute('SELECT * FROM ingredients WHERE id=?',(item_id,)).fetchone(); c.close(); return dict(row)


@app.delete('/ingredients/{item_id}')
def delete_ingredient(item_id:int,authorization:str|None=Header(default=None)):
    user=current_user(authorization); c=get_conn(); cur=c.execute('DELETE FROM ingredients WHERE id=? AND user_id=?',(item_id,user['id'])); c.commit(); c.close()
    if cur.rowcount==0: raise HTTPException(status_code=404,detail='Ingredient not found.')
    return {'ok':True}


@app.get('/ingredients/{item_id}/history')
def ingredient_history(item_id:int,authorization:str|None=Header(default=None)):
    user=current_user(authorization); c=get_conn(); owner=c.execute('SELECT id FROM ingredients WHERE id=? AND user_id=?',(item_id,user['id'])).fetchone()
    if not owner: c.close(); raise HTTPException(status_code=404,detail='Ingredient not found.')
    rs=c.execute('SELECT h.*,r.vendor,r.receipt_date FROM ingredient_price_history h LEFT JOIN receipts r ON r.id=h.receipt_id WHERE h.ingredient_id=? ORDER BY h.id DESC',(item_id,)).fetchall(); c.close(); return [dict(x) for x in rs]


# ---------------- EXPENSES / CASHOUTS ----------------
@app.post('/expenses')
def expense(expense_date:str=Form(...),description:str=Form(...),amount:float=Form(...),category:str=Form('Other'),location:str=Form('Main'),authorization:str|None=Header(default=None)):
    user=current_user(authorization)
    if amount<=0 or not description.strip(): raise HTTPException(status_code=400,detail='Description and a positive amount are required.')
    c=get_conn(); cur=c.execute('INSERT INTO expenses(expense_date,description,amount,category,location,user_id) VALUES(?,?,?,?,?,?)',(expense_date,description.strip(),amount,category,location,user['id'])); c.commit(); r=c.execute('SELECT * FROM expenses WHERE id=?',(cur.lastrowid,)).fetchone(); c.close(); return dict(r)

@app.get('/expenses')
def expenses(authorization:str|None=Header(default=None)):
    user=current_user(authorization); c=get_conn(); r=c.execute('SELECT * FROM expenses WHERE user_id=? ORDER BY expense_date DESC,id DESC LIMIT 200',(user['id'],)).fetchall(); c.close(); return [dict(x) for x in r]

@app.put('/expenses/{item_id}')
def update_expense(item_id:int,expense_date:str=Form(...),description:str=Form(...),amount:float=Form(...),category:str=Form(...),location:str=Form('Main'),authorization:str|None=Header(default=None)):
    user=current_user(authorization)
    if amount<=0 or not description.strip(): raise HTTPException(status_code=400,detail='Description and a positive amount are required.')
    c=get_conn(); cur=c.execute('UPDATE expenses SET expense_date=?,description=?,amount=?,category=?,location=? WHERE id=? AND user_id=?',(expense_date,description.strip(),amount,category,location,item_id,user['id']))
    if cur.rowcount==0: c.close(); raise HTTPException(status_code=404,detail='Expense not found.')
    c.commit(); row=c.execute('SELECT * FROM expenses WHERE id=?',(item_id,)).fetchone(); c.close(); return dict(row)

@app.delete('/expenses/{item_id}')
def delete_expense(item_id:int,authorization:str|None=Header(default=None)):
    user=current_user(authorization); c=get_conn(); cur=c.execute('DELETE FROM expenses WHERE id=? AND user_id=?',(item_id,user['id'])); c.commit(); c.close()
    if cur.rowcount==0: raise HTTPException(status_code=404,detail='Expense not found.')
    return {'ok':True}

@app.post('/cashouts')
def cashout(cash_date:str=Form(...),cash_sales:float=Form(0),digital_sales:float=Form(0),other_sales:float=Form(0),cogs:float=Form(0),notes:str=Form(''),location:str=Form('Main'),authorization:str|None=Header(default=None)):
    user=current_user(authorization)
    if min(cash_sales,digital_sales,other_sales,cogs)<0: raise HTTPException(status_code=400,detail='Amounts cannot be negative.')
    c=get_conn(); c.execute('''INSERT INTO cashouts(cash_date,cash_sales,digital_sales,other_sales,cogs,notes,location,user_id) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(cash_date,location,user_id) DO UPDATE SET cash_sales=excluded.cash_sales,digital_sales=excluded.digital_sales,other_sales=excluded.other_sales,cogs=excluded.cogs,notes=excluded.notes''',(cash_date,cash_sales,digital_sales,other_sales,cogs,notes,location,user['id'])); c.commit(); r=c.execute('SELECT * FROM cashouts WHERE cash_date=? AND location=? AND user_id=?',(cash_date,location,user['id'])).fetchone(); c.close(); return dict(r)

@app.get('/cashouts')
def cashouts(authorization:str|None=Header(default=None)):
    user=current_user(authorization); c=get_conn(); r=c.execute('SELECT * FROM cashouts WHERE user_id=? ORDER BY cash_date DESC,id DESC LIMIT 200',(user['id'],)).fetchall(); c.close(); return [dict(x) for x in r]

@app.put('/cashouts/{item_id}')
def update_cashout(item_id:int,cash_date:str=Form(...),cash_sales:float=Form(0),digital_sales:float=Form(0),other_sales:float=Form(0),cogs:float=Form(0),notes:str=Form(''),location:str=Form('Main'),authorization:str|None=Header(default=None)):
    user=current_user(authorization)
    if min(cash_sales,digital_sales,other_sales,cogs)<0: raise HTTPException(status_code=400,detail='Amounts cannot be negative.')
    c=get_conn(); cur=c.execute('UPDATE cashouts SET cash_date=?,cash_sales=?,digital_sales=?,other_sales=?,cogs=?,notes=?,location=? WHERE id=? AND user_id=?',(cash_date,cash_sales,digital_sales,other_sales,cogs,notes,location,item_id,user['id']))
    if cur.rowcount==0: c.close(); raise HTTPException(status_code=404,detail='Cashout not found.')
    c.commit(); row=c.execute('SELECT * FROM cashouts WHERE id=?',(item_id,)).fetchone(); c.close(); return dict(row)

@app.delete('/cashouts/{item_id}')
def delete_cashout(item_id:int,authorization:str|None=Header(default=None)):
    user=current_user(authorization); c=get_conn(); cur=c.execute('DELETE FROM cashouts WHERE id=? AND user_id=?',(item_id,user['id'])); c.commit(); c.close()
    if cur.rowcount==0: raise HTTPException(status_code=404,detail='Cashout not found.')
    return {'ok':True}


# ---------------- RECIPES ----------------
def recipe_payload_items(c,user_id,items):
    out=[]
    for i in items or []:
        name=str(i.get('ingredient_name') or '').strip(); qty=float(i.get('quantity') or 0); unit=str(i.get('unit') or 'pcs'); iid=i.get('ingredient_id'); source=i.get('source','ingredient')
        if not name or qty<=0: continue
        if iid:
            row=c.execute('SELECT * FROM ingredients WHERE id=? AND user_id=?',(int(iid),user_id)).fetchone()
        else: row=None
        if row:
            # Current price is used at recipe creation/update time; recipe stores a snapshot for historical reporting.
            uc=convert_unit_cost(float(row['current_cost']), row['unit'], unit); source='ingredient'; iid=row['id']; name=row['name']
        else:
            uc=float(i.get('unit_cost') or 0); iid=None; source='manual'
        out.append({'ingredient_id':iid,'ingredient_name':name,'quantity':qty,'unit':unit,'unit_cost':uc,'source':source})
    return out

@app.post('/recipes')
def recipe(payload:dict,authorization:str|None=Header(default=None)):
    user=current_user(authorization); price=float(payload.get('selling_price',0)); name=str(payload.get('name','')).strip()
    if not name or price<=0: raise HTTPException(status_code=400,detail='Dish name and positive selling price are required.')
    c=get_conn(); cur=c.execute('INSERT INTO recipes(name,selling_price,location,user_id) VALUES(?,?,?,?)',(name,price,payload.get('location','Main'),user['id'])); rid=cur.lastrowid
    for i in recipe_payload_items(c,user['id'],payload.get('items',[])):
        c.execute('INSERT INTO recipe_items(recipe_id,ingredient_id,ingredient_name,quantity,unit,unit_cost,source) VALUES(?,?,?,?,?,?,?)',(rid,i['ingredient_id'],i['ingredient_name'],i['quantity'],i['unit'],i['unit_cost'],i['source']))
    c.commit(); c.close(); return {'id':rid}

@app.get('/recipes')
def recipes(authorization:str|None=Header(default=None)):
    user=current_user(authorization); c=get_conn(); rs=c.execute('SELECT * FROM recipes WHERE user_id=? ORDER BY name',(user['id'],)).fetchall(); out=[]
    for r in rs:
        raw_items=c.execute('SELECT ri.*,ing.current_cost AS live_cost,ing.unit AS live_unit FROM recipe_items ri LEFT JOIN ingredients ing ON ing.id=ri.ingredient_id WHERE ri.recipe_id=?',(r['id'],)).fetchall(); items=[]; cost=0
        for raw in raw_items:
            i=dict(raw); uc=float(raw['live_cost']) if raw['live_cost'] is not None else float(raw['unit_cost']);
            if raw['live_cost'] is not None: uc=convert_unit_cost(uc,raw['live_unit'],raw['unit'])
            i['unit_cost']=uc; i.pop('live_cost',None); i.pop('live_unit',None); items.append(i); cost += float(i['quantity'])*uc
        price=float(r['selling_price']); margin=price-cost
        out.append({**dict(r),'cost':cost,'margin':margin,'margin_pct':margin/price*100 if price else 0,'status':'loss' if margin<0 else ('low' if price and margin/price*100<20 else 'profit'),'items':items})
    c.close(); return out

@app.put('/recipes/{item_id}')
def update_recipe(item_id:int,payload:dict,authorization:str|None=Header(default=None)):
    user=current_user(authorization); c=get_conn(); cur=c.execute('UPDATE recipes SET name=?,selling_price=?,location=? WHERE id=? AND user_id=?',(payload.get('name','Unnamed'),float(payload.get('selling_price',0)),payload.get('location','Main'),item_id,user['id']))
    if cur.rowcount==0: c.close(); raise HTTPException(status_code=404,detail='Recipe not found.')
    c.execute('DELETE FROM recipe_items WHERE recipe_id=?',(item_id,))
    for i in recipe_payload_items(c,user['id'],payload.get('items',[])):
        c.execute('INSERT INTO recipe_items(recipe_id,ingredient_id,ingredient_name,quantity,unit,unit_cost,source) VALUES(?,?,?,?,?,?,?)',(item_id,i['ingredient_id'],i['ingredient_name'],i['quantity'],i['unit'],i['unit_cost'],i['source']))
    c.commit(); c.close(); return {'ok':True}

@app.delete('/recipes/{item_id}')
def delete_recipe(item_id:int,authorization:str|None=Header(default=None)):
    user=current_user(authorization); c=get_conn(); cur=c.execute('DELETE FROM recipes WHERE id=? AND user_id=?',(item_id,user['id'])); c.commit(); c.close()
    if cur.rowcount==0: raise HTTPException(status_code=404,detail='Recipe not found.')
    return {'ok':True}


# ---------------- DASHBOARD / REPORTS ----------------
@app.get('/dashboard')
def dashboard(start='2000-01-01',end='2999-12-31',location='All',authorization:str|None=Header(default=None)):
    user=current_user(authorization); c=get_conn(); loc='' if location=='All' else ' AND location=?'; a=[start,end,user['id']] if location=='All' else [start,end,location,user['id']]
    s=c.execute(f'SELECT COALESCE(SUM(cash_sales+digital_sales+other_sales),0) sales,COALESCE(SUM(cogs),0) cogs FROM cashouts WHERE cash_date BETWEEN ? AND ?{loc} AND user_id=?',a).fetchone()
    e=c.execute(f'SELECT COALESCE(SUM(amount),0) expenses FROM expenses WHERE expense_date BETWEEN ? AND ?{loc} AND user_id=?',a).fetchone()
    trend=c.execute(f'SELECT cash_date,SUM(cash_sales+digital_sales+other_sales) sales,SUM(cogs) cogs FROM cashouts WHERE cash_date BETWEEN ? AND ?{loc} AND user_id=? GROUP BY cash_date ORDER BY cash_date',a).fetchall()
    cats=c.execute(f'SELECT category,SUM(amount) amount FROM expenses WHERE expense_date BETWEEN ? AND ?{loc} AND user_id=? GROUP BY category ORDER BY amount DESC',a).fetchall()
    recipes= c.execute('SELECT * FROM recipes WHERE user_id=? ORDER BY name',(user['id'],)).fetchall(); recipe_out=[]; loss_count=0
    for r in recipes:
        its=c.execute('SELECT ri.quantity,ri.unit,ri.unit_cost,ing.current_cost,ing.unit AS ingredient_unit FROM recipe_items ri LEFT JOIN ingredients ing ON ing.id=ri.ingredient_id WHERE ri.recipe_id=?',(r['id'],)).fetchall(); cost=0
        for i in its:
            uc=convert_unit_cost(float(i['current_cost']),i['ingredient_unit'],i['unit']) if i['current_cost'] is not None else float(i['unit_cost']); cost += float(i['quantity'])*uc
        price=float(r['selling_price']); margin=price-cost; pct=margin/price*100 if price else 0
        status='loss' if margin<0 else ('low' if pct<20 else 'profit'); loss_count += status=='loss'; recipe_out.append({'id':r['id'],'name':r['name'],'selling_price':price,'cost':cost,'profit':margin,'margin_pct':pct,'status':status})
    # Ingredient price alerts
    changed=[]
    for ing in c.execute('SELECT * FROM ingredients WHERE user_id=? ORDER BY name',(user['id'],)).fetchall():
        hist=c.execute('SELECT cost FROM ingredient_price_history WHERE ingredient_id=? ORDER BY id DESC LIMIT 2',(ing['id'],)).fetchall()
        if len(hist)>1 and float(hist[1]['cost'])!=0:
            pct=(float(hist[0]['cost'])-float(hist[1]['cost']))/float(hist[1]['cost'])*100
            if abs(pct)>=5: changed.append({'name':ing['name'],'current_cost':ing['current_cost'],'previous_cost':hist[1]['cost'],'change_pct':pct})
    c.close(); sales=float(s['sales']); cogs=float(s['cogs']); exp=float(e['expenses']); profit=sales-cogs-exp
    return {'sales':sales,'cogs':cogs,'expenses':exp,'net_profit':profit,'cogs_pct':(cogs/sales*100 if sales else 0),'trend':[dict(x) for x in trend],'expense_categories':[dict(x) for x in cats],'recipes':recipe_out,'loss_count':loss_count,'price_alerts':changed}


def csv_response(name,head,rows):
    o=io.StringIO(); w=csv.writer(o); w.writerow(head); w.writerows(rows); return StreamingResponse(iter([o.getvalue()]),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename={name}'})

@app.get('/export/expenses.csv')
def expcsv(authorization:str|None=Header(default=None)):
    user=current_user(authorization); c=get_conn(); r=c.execute('SELECT id,expense_date,description,amount,category,location FROM expenses WHERE user_id=? ORDER BY expense_date DESC',(user['id'],)).fetchall(); c.close(); return csv_response('ledgerbite_expenses.csv',['ID','Date','Description','Amount','Category','Location'],[[x[k] for k in ['id','expense_date','description','amount','category','location']] for x in r])

@app.get('/export/cashouts.csv')
def cashcsv(authorization:str|None=Header(default=None)):
    user=current_user(authorization); c=get_conn(); r=c.execute('SELECT cash_date,cash_sales,digital_sales,other_sales,cogs,location,notes FROM cashouts WHERE user_id=? ORDER BY cash_date DESC',(user['id'],)).fetchall(); c.close(); return csv_response('ledgerbite_cashouts.csv',['Date','Cash Sales','Digital Sales','Other Sales','COGS','Location','Notes'],[[x[k] for k in ['cash_date','cash_sales','digital_sales','other_sales','cogs','location','notes']] for x in r])

@app.get('/export/recipes.csv')
def recipecsv(authorization:str|None=Header(default=None)):
    user=current_user(authorization); c=get_conn(); rs=c.execute('SELECT * FROM recipes WHERE user_id=? ORDER BY name',(user['id'],)).fetchall(); rows=[]
    for r in rs:
        its=c.execute('SELECT ri.ingredient_name,ri.quantity,ri.unit,ri.unit_cost,ing.current_cost,ing.unit AS ingredient_unit FROM recipe_items ri LEFT JOIN ingredients ing ON ing.id=ri.ingredient_id WHERE ri.recipe_id=?',(r['id'],)).fetchall(); cost=0; computed=[]
        for i in its:
            uc=convert_unit_cost(float(i['current_cost']),i['ingredient_unit'],i['unit']) if i['current_cost'] is not None else float(i['unit_cost']); cost += float(i['quantity'])*uc; computed.append((i,uc))
        price=float(r['selling_price']); profit=price-cost; pct=profit/price*100 if price else 0
        for i,uc in computed: rows.append([r['name'],price,i['ingredient_name'],i['quantity'],i['unit'],uc,cost,profit,pct])
        if not its: rows.append([r['name'],price,'', '', '', '',cost,profit,pct])
    c.close(); return csv_response('ledgerbite_recipe_costing.csv',['Dish','Selling Price','Ingredient','Quantity','Unit','Ingredient Unit Cost','Total Dish Cost','Gross Profit','Margin %'],rows)

@app.get('/export/full.csv')
def fullcsv(authorization:str|None=Header(default=None)):
    user=current_user(authorization); c=get_conn(); out=[]
    for r in c.execute('SELECT * FROM receipts WHERE user_id=? ORDER BY id DESC',(user['id'],)).fetchall(): out.append(['Receipt',r['receipt_date'],r['vendor'],r['total'],r['category']])
    for r in c.execute('SELECT * FROM ingredients WHERE user_id=? ORDER BY name',(user['id'],)).fetchall(): out.append(['Ingredient',r['last_updated'],r['name'],r['current_cost'],r['unit']])
    for r in c.execute('SELECT * FROM expenses WHERE user_id=? ORDER BY expense_date DESC',(user['id'],)).fetchall(): out.append(['Expense',r['expense_date'],r['description'],r['amount'],r['category']])
    for r in c.execute('SELECT * FROM cashouts WHERE user_id=? ORDER BY cash_date DESC',(user['id'],)).fetchall(): out.append(['Cashout',r['cash_date'],'Sales',float(r['cash_sales'])+float(r['digital_sales'])+float(r['other_sales']),r['location']])
    c.close(); return csv_response('ledgerbite_full.csv',['Type','Date','Name','Amount','Category/Unit/Location'],out)
