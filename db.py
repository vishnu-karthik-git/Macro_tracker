"""
db.py — data layer for the multi-user macro tracker.

Uses SQLAlchemy Core so the SAME code runs on:
  - local SQLite   (for development / testing)
  - cloud Postgres (Supabase / Neon, for the deployed multi-user app)

Which one is used depends purely on the DATABASE_URL:
  - if the env var / Streamlit secret DATABASE_URL is set -> that database
  - otherwise -> a local file macro.db (SQLite)

Data model
----------
users    : one row per account (username + salted password hash)
foods    : shared base foods have user_id = NULL (everyone sees them);
           a user's custom foods have user_id = their id (only they see them)
log      : one row per logged food, scoped to a user
targets  : one row per user (bodyweight / calories / protein & fat per kg)
"""

import os
from datetime import date

from sqlalchemy import (
    create_engine, MetaData, Table, Column, Integer, String, Float,
    ForeignKey, select, func, and_, or_, insert, update, delete, UniqueConstraint,
)


# --------------------------------------------------------------------------
# Engine / connection
# --------------------------------------------------------------------------
def _resolve_database_url():
    """Prefer env var; fall back to Streamlit secrets if available."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        return url
    try:
        import streamlit as st  # optional; only present when running the web app
        if "DATABASE_URL" in st.secrets:
            return str(st.secrets["DATABASE_URL"]).strip()
    except Exception:
        pass
    return ""


def _make_engine():
    url = _resolve_database_url()
    if url:
        # Supabase/Heroku sometimes hand out "postgres://"; SQLAlchemy wants "postgresql://"
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return create_engine(url, pool_pre_ping=True)
    # local fallback
    local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "macro.db")
    return create_engine(f"sqlite:///{local_path}")


engine = _make_engine()
metadata = MetaData()

users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True),
    Column("username", String(80), unique=True, nullable=False),
    Column("pw_salt", String(64), nullable=False),
    Column("pw_hash", String(128), nullable=False),
)

foods = Table(
    "foods", metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
    Column("name", String(120), nullable=False),
    Column("kcal", Float, nullable=False),
    Column("protein", Float, nullable=False),
    Column("carbs", Float, nullable=False),
    Column("fat", Float, nullable=False),
    Column("category", String(80)),
    Column("notes", String(255)),
    UniqueConstraint("user_id", "name", name="uq_food_user_name"),
)

log = Table(
    "log", metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("entry_date", String(10), nullable=False),   # ISO yyyy-mm-dd
    Column("meal", String(20)),
    Column("food_id", Integer, ForeignKey("foods.id", ondelete="CASCADE"), nullable=False),
    Column("amount_g", Float, nullable=False),
)

targets = Table(
    "targets", metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("weight_kg", Float, nullable=False),
    Column("calories", Float, nullable=False),
    Column("protein_per_kg", Float, nullable=False),
    Column("fat_per_kg", Float, nullable=False),
)


DEFAULT_TARGETS = dict(weight_kg=63.0, calories=1950.0, protein_per_kg=2.1, fat_per_kg=0.9)

# Shared base foods (user_id = NULL). Same list as the desktop app.
BASE_FOODS = [
    ("Tofu, firm", 144, 15.5, 3.0, 8.7, "Vegan protein", "Every supermarket; press before cooking"),
    ("Tempeh", 195, 20.0, 7.7, 11.0, "Vegan protein", "Alnatura/Rewe Bio section"),
    ("Seitan", 370, 75.0, 14.0, 1.9, "Vegan protein", "Very high protein, low fat"),
    ("Edamame (shelled)", 122, 11.0, 10.0, 5.2, "Vegan protein", "Frozen, Aldi/Lidl"),
    ("Lentils, red, cooked", 116, 9.0, 20.0, 0.4, "Vegan protein/carb", "Rote Linsen"),
    ("Chickpeas, cooked", 164, 8.9, 27.4, 2.6, "Vegan protein/carb", "Kichererbsen"),
    ("Vegan mince (soy/pea based)", 170, 18.0, 6.0, 8.0, "Vegan protein", "Check label, varies by brand"),
    ("Pea protein powder", 380, 80.0, 5.0, 4.0, "Vegan protein", ""),
    ("Soy milk, unsweetened", 33, 3.3, 1.0, 1.8, "Vegan dairy swap", "Check label for added sugar"),
    ("Soy yogurt, plain", 60, 5.0, 3.0, 3.0, "Vegan dairy swap", "Alpro"),
    ("Almonds", 579, 21.0, 22.0, 50.0, "Vegan fat/protein", "Calorie-dense"),
    ("Peanut butter", 588, 25.0, 20.0, 50.0, "Vegan fat/protein", "No added sugar variety"),
    ("Chia seeds", 486, 17.0, 42.0, 31.0, "Vegan fat", ""),
    ("Oats, dry", 379, 13.5, 67.0, 6.9, "Carb", ""),
    ("Whole grain bread", 250, 9.0, 43.0, 3.5, "Carb", "Vollkornbrot"),
    ("Brown rice, cooked", 123, 2.7, 25.6, 1.0, "Carb", ""),
    ("Quinoa, cooked", 120, 4.4, 21.3, 1.9, "Carb (complete protein)", ""),
    ("Potatoes, boiled", 87, 2.0, 20.0, 0.1, "Carb", "Kartoffeln"),
    ("Banana", 89, 1.1, 22.8, 0.3, "Carb/fruit", ""),
    ("Broccoli", 34, 2.8, 6.6, 0.4, "Vegetable", ""),
    ("Spinach", 23, 2.9, 3.6, 0.4, "Vegetable", ""),
    ("Avocado", 160, 2.0, 8.5, 14.7, "Fat", ""),
    ("Olive oil", 884, 0.0, 0.0, 100.0, "Fat", "Use tablespoon (~13g) as unit"),
    ("Eggs, whole", 155, 13.0, 1.1, 11.0, "Vegetarian protein", ""),
    ("Egg whites", 52, 11.0, 0.7, 0.2, "Vegetarian protein", ""),
    ("Milk, 1.5% fat", 46, 3.4, 4.9, 1.5, "Vegetarian dairy", ""),
    ("Magerquark (skim quark)", 67, 12.0, 4.0, 0.3, "Vegetarian dairy", "Cheap, every supermarket"),
    ("Skyr", 63, 11.0, 4.0, 0.2, "Vegetarian dairy", ""),
    ("Greek yogurt, low fat", 59, 10.0, 3.6, 0.4, "Vegetarian dairy", ""),
    ("Whey protein powder", 380, 80.0, 8.0, 6.0, "Vegetarian protein", ""),
    ("Cottage cheese", 98, 11.1, 3.4, 4.3, "Vegetarian dairy", "Hüttenkäse"),
    ("Paneer", 265, 18.0, 1.2, 20.8, "Vegetarian protein", "Higher fat — portion control"),
    ("Chicken breast, cooked", 165, 31.0, 0.0, 3.6, "Meat protein", ""),
]


def init_db():
    """Create tables if missing and seed the shared base foods once."""
    metadata.create_all(engine)
    with engine.begin() as conn:
        existing = conn.execute(
            select(func.count()).select_from(foods).where(foods.c.user_id.is_(None))
        ).scalar()
        if not existing:
            conn.execute(
                insert(foods),
                [
                    dict(user_id=None, name=n, kcal=k, protein=p, carbs=c, fat=f,
                         category=cat, notes=note)
                    for (n, k, p, c, f, cat, note) in BASE_FOODS
                ],
            )


# --------------------------------------------------------------------------
# Users
# --------------------------------------------------------------------------
def create_user(username, pw_salt, pw_hash):
    with engine.begin() as conn:
        res = conn.execute(
            insert(users).values(username=username, pw_salt=pw_salt, pw_hash=pw_hash)
        )
        user_id = res.inserted_primary_key[0]
        # give the new user default targets
        conn.execute(insert(targets).values(user_id=user_id, **DEFAULT_TARGETS))
    return user_id


def get_user(username):
    with engine.connect() as conn:
        return conn.execute(
            select(users).where(users.c.username == username)
        ).mappings().first()


# --------------------------------------------------------------------------
# Foods  (shared base + this user's custom)
# --------------------------------------------------------------------------
def list_foods(user_id, search=""):
    cond = or_(foods.c.user_id.is_(None), foods.c.user_id == user_id)
    stmt = select(foods).where(cond)
    if search:
        stmt = stmt.where(foods.c.name.ilike(f"%{search}%"))
    stmt = stmt.order_by(foods.c.name)
    with engine.connect() as conn:
        return conn.execute(stmt).mappings().all()


def get_food_by_name(user_id, name):
    cond = and_(
        foods.c.name == name,
        or_(foods.c.user_id.is_(None), foods.c.user_id == user_id),
    )
    with engine.connect() as conn:
        return conn.execute(select(foods).where(cond)).mappings().first()


def add_food(user_id, name, kcal, protein, carbs, fat, category="", notes=""):
    with engine.begin() as conn:
        res = conn.execute(
            insert(foods).values(
                user_id=user_id, name=name, kcal=kcal, protein=protein,
                carbs=carbs, fat=fat, category=category, notes=notes,
            )
        )
        return res.inserted_primary_key[0]


def delete_food(user_id, food_id):
    # only allow deleting the user's OWN foods, never the shared base foods
    with engine.begin() as conn:
        conn.execute(
            delete(foods).where(and_(foods.c.id == food_id, foods.c.user_id == user_id))
        )


def import_foods_csv_rows(user_id, rows):
    """rows: iterable of dicts with keys name,kcal,protein,carbs,fat,category,notes."""
    added, skipped = 0, 0
    for row in rows:
        name = (row.get("name") or "").strip()
        if not name:
            skipped += 1
            continue
        if get_food_by_name(user_id, name):
            skipped += 1
            continue
        try:
            add_food(
                user_id, name,
                float(row.get("kcal") or 0), float(row.get("protein") or 0),
                float(row.get("carbs") or 0), float(row.get("fat") or 0),
                (row.get("category") or "").strip(), (row.get("notes") or "").strip(),
            )
            added += 1
        except Exception:
            skipped += 1
    return added, skipped


# --------------------------------------------------------------------------
# Log
# --------------------------------------------------------------------------
def add_log_entry(user_id, entry_date, meal, food_id, amount_g):
    with engine.begin() as conn:
        res = conn.execute(
            insert(log).values(user_id=user_id, entry_date=entry_date,
                               meal=meal, food_id=food_id, amount_g=amount_g)
        )
        return res.inserted_primary_key[0]


def delete_log_entry(user_id, log_id):
    with engine.begin() as conn:
        conn.execute(delete(log).where(and_(log.c.id == log_id, log.c.user_id == user_id)))


def log_for_date(user_id, entry_date):
    stmt = (
        select(
            log.c.id, log.c.meal, foods.c.name.label("food_name"), log.c.amount_g,
            (foods.c.kcal * log.c.amount_g / 100.0).label("kcal"),
            (foods.c.protein * log.c.amount_g / 100.0).label("protein"),
            (foods.c.carbs * log.c.amount_g / 100.0).label("carbs"),
            (foods.c.fat * log.c.amount_g / 100.0).label("fat"),
        )
        .select_from(log.join(foods, log.c.food_id == foods.c.id))
        .where(and_(log.c.user_id == user_id, log.c.entry_date == entry_date))
        .order_by(log.c.id)
    )
    with engine.connect() as conn:
        return conn.execute(stmt).mappings().all()


def totals_for_date(user_id, entry_date):
    totals = dict(kcal=0.0, protein=0.0, carbs=0.0, fat=0.0)
    for r in log_for_date(user_id, entry_date):
        for k in totals:
            totals[k] += r[k]
    return totals


def distinct_log_dates(user_id, limit=30):
    stmt = (
        select(log.c.entry_date)
        .where(log.c.user_id == user_id)
        .distinct()
        .order_by(log.c.entry_date.desc())
        .limit(limit)
    )
    with engine.connect() as conn:
        return [r[0] for r in conn.execute(stmt).all()]


def last_n_days_totals(user_id, n=30):
    return [(d, totals_for_date(user_id, d)) for d in distinct_log_dates(user_id, n)]


# --------------------------------------------------------------------------
# Targets
# --------------------------------------------------------------------------
def get_targets(user_id):
    with engine.connect() as conn:
        row = conn.execute(select(targets).where(targets.c.user_id == user_id)).mappings().first()
    if row is None:
        with engine.begin() as conn:
            conn.execute(insert(targets).values(user_id=user_id, **DEFAULT_TARGETS))
        return get_targets(user_id)
    weight, calories = row["weight_kg"], row["calories"]
    protein_g = weight * row["protein_per_kg"]
    fat_g = weight * row["fat_per_kg"]
    carbs_g = max((calories - protein_g * 4 - fat_g * 9) / 4.0, 0)
    return {
        "weight_kg": weight, "calories": calories,
        "protein_per_kg": row["protein_per_kg"], "fat_per_kg": row["fat_per_kg"],
        "protein_g": protein_g, "fat_g": fat_g, "carbs_g": carbs_g,
    }


def set_targets(user_id, weight_kg, calories, protein_per_kg, fat_per_kg):
    with engine.begin() as conn:
        conn.execute(
            update(targets).where(targets.c.user_id == user_id).values(
                weight_kg=weight_kg, calories=calories,
                protein_per_kg=protein_per_kg, fat_per_kg=fat_per_kg,
            )
        )


def today_str():
    return date.today().isoformat()
