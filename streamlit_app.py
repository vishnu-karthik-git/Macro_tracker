"""
streamlit_app.py — multi-user macro tracker web app.

Run locally:   streamlit run streamlit_app.py
Deployed:      Streamlit Community Cloud points at this file (see README).

Data goes to Postgres when DATABASE_URL is set (Streamlit secret), else local SQLite.
"""

import csv
import io

import pandas as pd
import streamlit as st

import db
import auth

st.set_page_config(page_title="Macro Tracker", page_icon="🍽️", layout="wide")

# Initialise DB (create tables + seed base foods) once per process.
db.init_db()

MEALS = ["Breakfast", "Lunch", "Dinner", "Snack"]


# ------------------------------------------------------------------ AUTH GATE
def auth_screen():
    st.title("🍽️ Macro Tracker")
    st.caption("Track calories & macros. Multi-user — your log, targets and custom foods are private to your account.")

    tab_login, tab_register = st.tabs(["Log in", "Create account"])

    with tab_login:
        u = st.text_input("Username", key="login_user")
        p = st.text_input("Password", type="password", key="login_pw")
        if st.button("Log in", type="primary"):
            user_id, msg = auth.login(u, p)
            if user_id:
                st.session_state.user_id = user_id
                st.session_state.username = u.strip()
                st.rerun()
            else:
                st.error(msg)

    with tab_register:
        u = st.text_input("Choose a username (min 3 chars)", key="reg_user")
        p = st.text_input("Choose a password (min 6 chars)", type="password", key="reg_pw")
        if st.button("Create account"):
            ok, msg = auth.register(u, p)
            (st.success if ok else st.error)(msg)
            if ok:
                st.info("Now switch to the 'Log in' tab.")


# ------------------------------------------------------------------ MAIN TABS
def log_tab(user_id):
    st.subheader("Daily Log")
    targets = db.get_targets(user_id)

    col1, col2 = st.columns([1, 1])
    with col1:
        entry_date = st.date_input("Date").isoformat()
    with col2:
        meal = st.selectbox("Meal", MEALS)

    all_foods = db.list_foods(user_id)
    food_names = [f["name"] for f in all_foods]

    c1, c2, c3 = st.columns([3, 1, 1])
    with c1:
        # Streamlit selectbox is searchable by default (type to filter)
        chosen = st.selectbox("Food (type to filter)", food_names, key="log_food")
    with c2:
        amount = st.number_input("Amount (g)", min_value=1.0, value=100.0, step=10.0)
    with c3:
        st.write("")
        st.write("")
        if st.button("➕ Add", type="primary"):
            food = db.get_food_by_name(user_id, chosen)
            if food:
                db.add_log_entry(user_id, entry_date, meal, food["id"], amount)
                st.rerun()

    rows = db.log_for_date(user_id, entry_date)
    if rows:
        df = pd.DataFrame(rows)
        df_display = df[["meal", "food_name", "amount_g", "kcal", "protein", "carbs", "fat"]].copy()
        df_display.columns = ["Meal", "Food", "Amount (g)", "Kcal", "Protein", "Carbs", "Fat"]
        df_display = df_display.round(1)
        st.dataframe(df_display, use_container_width=True, hide_index=True)

        # delete control
        del_options = {f'{r["meal"]} — {r["food_name"]} ({r["amount_g"]:.0f}g)': r["id"] for r in rows}
        to_del = st.selectbox("Remove an entry", ["—"] + list(del_options.keys()))
        if to_del != "—" and st.button("Delete selected entry"):
            db.delete_log_entry(user_id, del_options[to_del])
            st.rerun()
    else:
        st.info("No entries for this date yet.")

    # totals vs targets
    totals = db.totals_for_date(user_id, entry_date)
    st.markdown("### Totals vs Targets")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Calories", f'{totals["kcal"]:.0f}', f'{totals["kcal"]-targets["calories"]:+.0f} vs {targets["calories"]:.0f}')
    m2.metric("Protein (g)", f'{totals["protein"]:.0f}', f'{totals["protein"]-targets["protein_g"]:+.0f} vs {targets["protein_g"]:.0f}')
    m3.metric("Carbs (g)", f'{totals["carbs"]:.0f}', f'target ~{targets["carbs_g"]:.0f}', delta_color="off")
    m4.metric("Fat (g)", f'{totals["fat"]:.0f}', f'target ~{targets["fat_g"]:.0f}', delta_color="off")


def food_tab(user_id):
    st.subheader("Food Database")
    st.caption("Shared base foods are visible to everyone. Foods you add are private to your account.")

    search = st.text_input("Filter foods", "")
    foods = db.list_foods(user_id, search)
    if foods:
        df = pd.DataFrame(foods)[["name", "kcal", "protein", "carbs", "fat", "category"]]
        df.columns = ["Food", "Kcal/100g", "Protein/100g", "Carbs/100g", "Fat/100g", "Category"]
        st.dataframe(df.round(1), use_container_width=True, hide_index=True)

    st.markdown("### Add a food (values per 100 g)")
    with st.form("add_food", clear_on_submit=True):
        c = st.columns(5)
        name = c[0].text_input("Name")
        kcal = c[1].number_input("Kcal", min_value=0.0, value=0.0)
        protein = c[2].number_input("Protein g", min_value=0.0, value=0.0)
        carbs = c[3].number_input("Carbs g", min_value=0.0, value=0.0)
        fat = c[4].number_input("Fat g", min_value=0.0, value=0.0)
        c2 = st.columns([1, 2])
        category = c2[0].text_input("Category")
        notes = c2[1].text_input("Notes")
        submitted = st.form_submit_button("Save food", type="primary")
        if submitted:
            if not name.strip():
                st.error("Enter a food name.")
            elif db.get_food_by_name(user_id, name.strip()):
                st.error("A food with that name already exists (base or your own).")
            else:
                db.add_food(user_id, name.strip(), kcal, protein, carbs, fat, category.strip(), notes.strip())
                st.success(f"Added {name.strip()}.")
                st.rerun()

    st.markdown("### Bulk import from CSV")
    st.caption("CSV header must be: name,kcal,protein,carbs,fat,category,notes")
    up = st.file_uploader("Upload CSV", type=["csv"])
    if up is not None and st.button("Import uploaded CSV"):
        text = io.StringIO(up.getvalue().decode("utf-8-sig"))
        rows = list(csv.DictReader(text))
        added, skipped = db.import_foods_csv_rows(user_id, rows)
        st.success(f"Added {added}, skipped {skipped} (duplicates or bad rows).")
        st.rerun()

    st.markdown("### Remove one of your own foods")
    own = [f for f in db.list_foods(user_id) if f["user_id"] == user_id]
    if own:
        opts = {f["name"]: f["id"] for f in own}
        pick = st.selectbox("Your custom foods", ["—"] + list(opts.keys()))
        if pick != "—" and st.button("Delete this food"):
            db.delete_food(user_id, opts[pick])
            st.rerun()
    else:
        st.caption("You haven't added any custom foods yet.")


def targets_tab(user_id):
    st.subheader("Targets")
    t = db.get_targets(user_id)
    with st.form("targets"):
        weight = st.number_input("Bodyweight (kg)", min_value=1.0, value=float(t["weight_kg"]))
        calories = st.number_input("Target daily calories", min_value=500.0, value=float(t["calories"]), step=50.0)
        protein_kg = st.number_input("Protein (g per kg bodyweight)", min_value=0.0, value=float(t["protein_per_kg"]), step=0.1)
        fat_kg = st.number_input("Fat (g per kg bodyweight)", min_value=0.0, value=float(t["fat_per_kg"]), step=0.1)
        if st.form_submit_button("Save targets", type="primary"):
            db.set_targets(user_id, weight, calories, protein_kg, fat_kg)
            st.success("Targets saved.")
            st.rerun()

    st.markdown("### Computed daily targets")
    t = db.get_targets(user_id)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Calories", f'{t["calories"]:.0f}')
    c2.metric("Protein (g)", f'{t["protein_g"]:.0f}')
    c3.metric("Carbs (g)", f'{t["carbs_g"]:.0f}')
    c4.metric("Fat (g)", f'{t["fat_g"]:.0f}')


def history_tab(user_id):
    st.subheader("History")
    data = db.last_n_days_totals(user_id, 30)
    if not data:
        st.info("No logged days yet.")
        return
    df = pd.DataFrame(
        [{"Date": d, "Kcal": t["kcal"], "Protein (g)": t["protein"],
          "Carbs (g)": t["carbs"], "Fat (g)": t["fat"]} for d, t in data]
    ).round(1)
    st.dataframe(df, use_container_width=True, hide_index=True)
    chart_df = df.set_index("Date").sort_index()[["Kcal"]]
    st.line_chart(chart_df)


def main_app():
    with st.sidebar:
        st.write(f"Signed in as **{st.session_state.username}**")
        if st.button("Log out"):
            for k in ("user_id", "username"):
                st.session_state.pop(k, None)
            st.rerun()

    st.title("🍽️ Macro Tracker")
    user_id = st.session_state.user_id
    t1, t2, t3, t4 = st.tabs(["Log", "Food Database", "Targets", "History"])
    with t1:
        log_tab(user_id)
    with t2:
        food_tab(user_id)
    with t3:
        targets_tab(user_id)
    with t4:
        history_tab(user_id)


if "user_id" not in st.session_state:
    auth_screen()
else:
    main_app()
