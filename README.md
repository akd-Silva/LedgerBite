# LedgerBite MVP — Receipt-to-Recipe Profit Intelligence

LedgerBite is a mobile-first micro-accounting prototype for independent food operators. Its core workflow is:

**Scan what you buy → save ingredient prices → cost your dishes → detect loss-making prices → understand profit → download reports.**

## Main features

- Login + registration with per-user data isolation
- Receipt OCR using local Tesseract
- Receipt line items saved into an ingredient database
- Repeated ingredients update to the latest scanned cost
- Ingredient price history
- Ingredient CRUD: add, edit, delete, search
- Recipe Costing as a main intelligence feature
- Select/search saved ingredients when building a dish
- Quantity + unit conversion (g/kg and ml/L supported)
- Manual ingredients for items not found on receipts
- Live recipe cost based on the ingredient's current saved price
- Profit, loss, food cost and gross margin calculations
- Pricing insight using a target 50% gross-margin reference
- Overview warning for dishes selling below ingredient cost
- Low-margin warnings and ingredient price-change insights
- Shift Cashout and Expenses with CRUD
- Recipe, ingredient, expense and cashout reports
- CSV downloads plus a PDF business/recipe report
- SQLite local database
- Optional AI receipt extraction hook

## Important behavior

When a receipt is scanned, LedgerBite saves detected receipt items. If an ingredient already exists for that restaurant, its current cost is updated using the newest receipt. The previous price is retained in `ingredient_price_history` so price changes can be shown.

Recipes linked to saved ingredients use the **current ingredient price** when displayed. Therefore, a new receipt or a manual ingredient-price edit can automatically change the calculated cost, margin and loss/profit warning for affected dishes.

Manual recipe ingredients remain independent of receipt prices.

## Windows setup

1. Install Python 3.10+.
2. Install Tesseract OCR.
3. Open this folder in VS Code.
4. Create and activate the virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

5. Install packages:

```powershell
pip install -r requirements.txt
```

6. Copy `.env.example` to `.env` and set the Tesseract executable path if needed:

```env
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

## Run

Open two VS Code terminals.

### Terminal 1 — FastAPI

```powershell
.venv\Scripts\Activate.ps1
uvicorn backend.main:app --reload --port 8000
```

API documentation:

`http://127.0.0.1:8000/docs`

Health/root check:

`http://127.0.0.1:8000/`

### Terminal 2 — Streamlit

```powershell
.venv\Scripts\Activate.ps1
streamlit run frontend/app.py
```

Open:

`http://localhost:8501`

## Database

The SQLite database is created automatically at `data/ledgerbite.db`.

For a clean demo/test, stop the backend and delete:

```text
data\ledgerbite.db
```

The next backend start recreates the database.

## Notes

This is an MVP/prototype and is not tax/accounting compliance software. Receipt OCR is best-effort and financial values should be reviewed after scanning.
