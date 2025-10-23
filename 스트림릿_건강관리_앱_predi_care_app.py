# PrediCare: 스트림릿 개인 체중·혈당 관리 앱 (이미지 식단 기록 + 걷기 중심 운동)
# --------------------------------------------------------------
# 변경 내역 (2025-10-23)
# - ✅ API 없이도 동작하는 "내장 음식 DB 기반 자동 칼로리/탄수화물 계산" 추가
# - ✅ "식단 템플릿 불러오기" 버튼(가이드 식단표 바로 채우기)
# - ✅ 섭취 시간: 선택(time_input) + 직접 입력(HH:MM) 모두 지원
# - ⚠️ 사진만으로 자동 인식은 외부 AI/비전 API 없이는 불가 → 대신 사진 첨부 + 음식 선택으로 계산
# --------------------------------------------------------------

import os
import io
import math
import base64
from datetime import datetime, date, time, timedelta
from typing import List, Tuple, Optional, Dict

import pandas as pd
import numpy as np
import streamlit as st
import altair as alt
import sqlite3

APP_NAME = "PrediCare"
DB_PATH = "data/health.db"
IMG_DIR = "data/meal_photos"

# ----------------------------- 유틸 & 초기화 ----------------------------- #

def ensure_dirs():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    os.makedirs(IMG_DIR, exist_ok=True)


def get_conn():
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS profile (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            birth_year INTEGER,
            sex TEXT,
            height_cm REAL,
            weight_kg REAL,
            target_weight_kg REAL,
            daily_calorie_target INTEGER,
            daily_carb_target_g INTEGER,
            knee_care INTEGER DEFAULT 1
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dt TEXT,
            label TEXT,
            items TEXT,
            calories REAL,
            carbs_g REAL,
            photo_path TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dt TEXT,
            kind TEXT,
            minutes REAL,
            steps INTEGER,
            distance_km REAL,
            pace_kmh REAL,
            calories REAL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS weights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            d TEXT,
            weight_kg REAL
        )
        """
    )
    conn.commit()


@st.cache_data(show_spinner=False)
def load_df(table: str) -> pd.DataFrame:
    conn = get_conn()
    return pd.read_sql_query(f"SELECT * FROM {table}", conn)


def refresh_cache():
    load_df.clear()


# ----------------------------- 계산 로직 ----------------------------- #

def bmr_mifflin(weight_kg: float, height_cm: float, age: int, sex: str) -> float:
    s = 5 if sex.lower().startswith("m") else -161
    return 10 * weight_kg + 6.25 * height_cm - 5 * age + s


def tdee_from_activity(bmr: float, activity_level: str) -> float:
    factors = {"낮음": 1.2, "보통": 1.375, "활동적": 1.55, "매우 활동적": 1.725}
    return bmr * factors.get(activity_level, 1.375)


def walking_met(pace_kmh: float) -> float:
    if pace_kmh <= 3.5: return 3.0
    if pace_kmh <= 4.5: return 3.8
    if pace_kmh <= 5.5: return 4.8
    if pace_kmh <= 6.4: return 6.0
    return 6.5


def kcal_from_met(met: float, weight_kg: float, minutes: float) -> float:
    return met * 3.5 * weight_kg / 200 * minutes


# ----------------------------- 내장 음식 DB (API 없이 계산) ----------------------------- #
# 1인분 기준 칼로리/탄수화물(g) 간이치. 필요시 자유롭게 확장하세요.
FOOD_DB: Dict[str, Dict[str, float]] = {
    # 곡류/밥
    "현미밥 1/2공기(100g)": {"kcal": 150, "carb": 33},
    "현미밥 1공기(200g)": {"kcal": 300, "carb": 66},
    "잡곡밥 1공기": {"kcal": 320, "carb": 68},
    "곤약밥 1공기": {"kcal": 180, "carb": 40},
    # 단백질
    "닭가슴살 100g": {"kcal": 165, "carb": 0},
    "두부 100g": {"kcal": 80, "carb": 2},
    "계란 1개": {"kcal": 70, "carb": 0.6},
    "연어 120g": {"kcal": 240, "carb": 0},
    "고등어 120g": {"kcal": 250, "carb": 0},
    # 채소/샐러드
    "샐러드(채소) 1접시": {"kcal": 60, "carb": 8},
    "찐브로콜리 1접시": {"kcal": 55, "carb": 11},
    "시금치나물 1접시": {"kcal": 70, "carb": 7},
    # 곡/면 대체
    "곤약면 1인분": {"kcal": 25, "carb": 2},
    "현미국수 1인분": {"kcal": 380, "carb": 78},
    # 간식/유제품/견과
    "플레인 요거트 150g": {"kcal": 95, "carb": 11},
    "아몬드 25g": {"kcal": 145, "carb": 5},
    "방울토마토 10개": {"kcal": 30, "carb": 7},
    # 과일(소량)
    "사과 1/2개": {"kcal": 50, "carb": 14},
    "바나나 1/2개": {"kcal": 45, "carb": 12},
    # 조미/지방(선택)
    "올리브오일 1작은술": {"kcal": 40, "carb": 0},
}

TEMPLATES = {
    "아침(예시)": ["현미밥 1/2공기(100g)", "계란 1개", "샐러드(채소) 1접시", "두부 100g"],
    "점심(예시)": ["곤약면 1인분", "닭가슴살 100g", "샐러드(채소) 1접시", "올리브오일 1작은술"],
    "저녁(예시)": ["연어 120g", "찐브로콜리 1접시", "두부 100g"],
    "간식(예시)": ["플레인 요거트 150g", "아몬드 25g"],
}


def compute_nutrition(selected: List[str], servings: Dict[str, float]) -> Tuple[float, float]:
    kcal = 0.0
    carb = 0.0
    for item in selected:
        base = FOOD_DB.get(item, {"kcal": 0, "carb": 0})
        s = servings.get(item, 1.0)
        kcal += base["kcal"] * s
        carb += base["carb"] * s
    return kcal, carb


# ----------------------------- DB 헬퍼 ----------------------------- #

def upsert_profile(**kwargs):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM profile WHERE id = 1")
    exists = cur.fetchone() is not None
    cols = [k for k in kwargs.keys()]
    vals = [kwargs[k] for k in cols]
    if exists:
        set_clause = ", ".join([f"{c} = ?" for c in cols])
        cur.execute(f"UPDATE profile SET {set_clause} WHERE id = 1", vals)
    else:
        col_clause = ", ".join(cols)
        q = ",".join(["?"] * len(cols))
        cur.execute(f"INSERT INTO profile(id, {col_clause}) VALUES (1, {q})", vals)
    conn.commit()
    refresh_cache()


def insert_meal(dt: datetime, label: str, items: str, calories: float, carbs_g: float, photo_path: Optional[str]):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO meals(dt, label, items, calories, carbs_g, photo_path) VALUES (?,?,?,?,?,?)",
        (dt.isoformat(), label, items, calories, carbs_g, photo_path),
    )
    conn.commit()
    refresh_cache()


def insert_activity(dt: datetime, kind: str, minutes: float, steps: Optional[int], distance_km: Optional[float], pace_kmh: Optional[float], calories: float):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO activities(dt, kind, minutes, steps, distance_km, pace_kmh, calories) VALUES (?,?,?,?,?,?,?)",
        (dt.isoformat(), kind, minutes, steps, distance_km, pace_kmh, calories),
    )
    conn.commit()
    refresh_cache()


def insert_weight(d: date, weight_kg: float):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO weights(d, weight_kg) VALUES (?,?)", (d.isoformat(), weight_kg))
    conn.commit()
    refresh_cache()


# ----------------------------- 스트림릿 UI ----------------------------- #

st.set_page_config(page_title=f"{APP_NAME}", page_icon="🍎", layout="wide")
init_db()

st.title("🍎 PrediCare — 걷기 기반 당뇨 전단계 체중 관리")
st.caption("*개인 건강 참고용 도구입니다. 의학적 진단/치료를 대체하지 않습니다.*")

with st.sidebar:
    st.header("프로필 & 목표")
    today = date.today()
    default_birth_year = today.year - 52

    col1, col2 = st.columns(2)
    with col1:
        birth_year = st.number_input("출생연도", min_value=1930, max_value=today.year, value=default_birth_year, step=1)
    with col2:
        sex = st.selectbox("성별", ["여성", "남성"], index=0)

    height_cm = st.number_input("키 (cm)", min_value=120.0, max_value=210.0, value=160.0, step=0.5)
    weight_kg = st.number_input("현재 체중 (kg)", min_value=35.0, max_value=200.0, value=65.0, step=0.1)
    target_weight_kg = st.number_input("목표 체중 (kg)", min_value=35.0, max_value=200.0, value=60.0, step=0.1)

    activity_level = st.select_slider("평소 활동량", options=["낮음", "보통", "활동적", "매우 활동적"], value="보통")
    knee_care = st.checkbox("무릎 보호 모드 (전방십자인대 수술 이력)", value=True)

    age = today.year - int(birth_year)
    bmr = bmr_mifflin(weight_kg, height_cm, age, sex)
    tdee = tdee_from_activity(bmr, activity_level)

    st.write(f"BMR(기초대사량): **{int(bmr)}** kcal/일")
    st.write(f"TDEE(유지 칼로리): **{int(tdee)}** kcal/일")

    deficit = 300
    daily_calorie_target = int(max(1200, tdee - deficit))
    daily_carb_target_g = 150

    st.write(f"권장 섭취열량: **{daily_calorie_target} kcal/일** (약 -{deficit} kcal)")
    st.write(f"권장 탄수화물: **{daily_carb_target_g} g/일**")

    if st.button("목표 저장/업데이트"):
        upsert_profile(
            birth_year=birth_year,
            sex=sex,
            height_cm=height_cm,
            weight_kg=weight_kg,
            target_weight_kg=target_weight_kg,
            daily_calorie_target=daily_calorie_target,
            daily_carb_target_g=daily_carb_target_g,
            knee_care=1 if knee_care else 0,
        )
        st.success("프로필이 저장되었습니다.")

# 탭 구성
TAB1, TAB2, TAB3 = st.tabs(["오늘 기록", "통계", "가이드"])

# ----------------------------- 탭: 오늘 기록 ----------------------------- #
with TAB1:
    st.subheader("📸 식단 기록 (사진 업로드 / 내장 DB 자동계산 / 수동 입력)")

    col_a, col_b = st.columns([1, 1])
    with col_a:
        meal_label = st.selectbox("식사 구분", ["아침", "점심", "저녁", "간식"])

        # 시간: 선택 + 직접 입력(HH:MM)
        meal_time_select = st.time_input("섭취 시간(선택)", value=datetime.now().time())
        meal_time_text = st.text_input("섭취 시간 직접 입력(HH:MM)", value="")
        def _parse_time(txt: str) -> Optional[time]:
            try:
                if not txt: return None
                hh, mm = txt.strip().split(":")
                return time(hour=int(hh), minute=int(mm))
            except Exception:
                return None
        meal_time = _parse_time(meal_time_text) or meal_time_select

        uploaded = st.file_uploader("음식 사진 업로드 (선택)", type=["jpg", "jpeg", "png"], help="사진은 기록/미리보기 용도입니다. API 없이 자동 인식은 불가합니다.")

        st.markdown("**방법 A. 내장 음식 DB로 자동 계산(권장, API 불필요)**")
        selected_items = st.multiselect("음식 선택", options=sorted(FOOD_DB.keys()))

        servings = {}
        if selected_items:
            st.write("인분/분량 조정")
            for it in selected_items:
                servings[it] = st.number_input(f"{it} x", min_value=0.0, max_value=10.0, value=1.0, step=0.25, key=f"srv_{it}")
        kcal_auto, carb_auto = compute_nutrition(selected_items, servings)
        st.info(f"자동 계산 결과 → 칼로리: **{int(kcal_auto)} kcal**, 탄수화물: **{int(carb_auto)} g**")

        st.markdown("**방법 B. 직접 입력(라벨/앱 참조값)**")
        items_text = st.text_area("음식 항목 (쉼표로 구분)", placeholder="예: 현미밥 1/2공기, 닭가슴살 100g, 샐러드, 두부 100g")
        calories = st.number_input("총 칼로리(kcal)", min_value=0.0, max_value=5000.0, value=float(kcal_auto), step=10.0)
        carbs_g = st.number_input("총 탄수화물(g)", min_value=0.0, max_value=1000.0, value=float(carb_auto), step=1.0)

        # 템플릿 불러오기
        st.markdown("**빠른 입력: 예시 식단 템플릿**")
        tcol1, tcol2, tcol3, tcol4 = st.columns(4)
        if tcol1.button("아침(예시) 불러오기"):
            items_text = ", ".join(TEMPLATES["아침(예시)"])
            st.session_state["_tmp_items_text"] = items_text
        if tcol2.button("점심(예시) 불러오기"):
            items_text = ", ".join(TEMPLATES["점심(예시)"])
            st.session_state["_tmp_items_text"] = items_text
        if tcol3.button("저녁(예시) 불러오기"):
            items_text = ", ".join(TEMPLATES["저녁(예시)"])
            st.session_state["_tmp_items_text"] = items_text
        if tcol4.button("간식(예시) 불러오기"):
            items_text = ", ".join(TEMPLATES["간식(예시)"])
            st.session_state["_tmp_items_text"] = items_text
        # 버튼으로 채운 텍스트 반영
        if st.session_state.get("_tmp_items_text"):
            items_text = st.session_state["_tmp_items_text"]
            st.text_area("템플릿 적용됨", items_text, key="items_text_applied")
            # 템플릿 영양 자동 계산
            servings_tmp = {it:1.0 for it in items_text.split(", ") if it in FOOD_DB}
            kcal_t, carb_t = compute_nutrition(list(servings_tmp.keys()), servings_tmp)
            calories = kcal_t
            carbs_g = carb_t
            st.info(f"템플릿 자동 계산 → {int(kcal_t)} kcal / {int(carb_t)} g")

        if st.button("식단 저장"):
            # 이미지 저장
            photo_path = None
            if uploaded is not None:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                ext = os.path.splitext(uploaded.name)[1].lower()
                photo_path = os.path.join(IMG_DIR, f"meal_{ts}{ext}")
                with open(photo_path, "wb") as f:
                    f.write(uploaded.getvalue())

            # 저장할 항목 문자열 구성(선택+수동 합침)
            auto_items_str = ", ".join([f"{k} x{servings.get(k,1)}" for k in selected_items])
            items_final = ", ".join([s for s in [auto_items_str, items_text.strip()] if s])
            # 시간 합성
            dt = datetime.combine(date.today(), meal_time)
            insert_meal(dt, meal_label, items_final, float(calories), float(carbs_g), photo_path)
            st.success("식단이 저장되었습니다.")

    with col_b:
        st.write("오늘 입력된 식단")
        meals_df = load_df("meals")
        if not meals_df.empty:
            meals_df["date"] = pd.to_datetime(meals_df["dt"]).dt.date
            today_df = meals_df[meals_df["date"] == date.today()]
            if today_df.empty:
                st.info("아직 오늘 식단 기록이 없습니다.")
            else:
                st.dataframe(
                    today_df[["dt", "label", "items", "calories", "carbs_g"]]
                    .rename(columns={"dt": "시간", "label": "구분", "items": "항목", "calories": "kcal", "carbs_g": "탄수(g)"})
                    .sort_values("시간"),
                    use_container_width=True,
                )
        else:
            st.info("아직 식단 데이터가 없습니다.")

    st.markdown("---")
    st.subheader("🚶 걷기 기록")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        minutes = st.number_input("운동 시간(분)", min_value=0.0, max_value=600.0, value=30.0, step=5.0)
    with col2:
        distance_km = st.number_input("거리(km) (선택)", min_value=0.0, max_value=50.0, value=0.0, step=0.1)
    with col3:
        steps = st.number_input("걸음수 (선택)", min_value=0, max_value=100000, value=0, step=100)
    with col4:
        pace_kmh = st.number_input("평균 속도(km/h) (선택)", min_value=0.0, max_value=12.0, value=4.5, step=0.1)

    if pace_kmh and minutes and distance_km == 0:
        distance_km = pace_kmh * (minutes / 60)
    if distance_km and minutes and pace_kmh == 0:
        pace_kmh = (distance_km / (minutes / 60)) if minutes > 0 else 0

    met = walking_met(pace_kmh if pace_kmh > 0 else 4.0)
    kcal = kcal_from_met(met, weight_kg, minutes)
    st.write(f"예상 소모 칼로리: **{int(kcal)} kcal** (MET {met:.1f})")

    if st.button("걷기 저장"):
        dt = datetime.now()
        insert_activity(dt, "걷기", float(minutes), int(steps) if steps else None, float(distance_km) if distance_km else None, float(pace_kmh) if pace_kmh else None, float(kcal))
        st.success("운동이 저장되었습니다.")

    st.markdown("---")
    st.subheader("⚖️ 체중 기록")
    wcol1, wcol2 = st.columns([1,1])
    with wcol1:
        weight_input = st.number_input("오늘 체중 (kg)", min_value=30.0, max_value=250.0, value=float(weight_kg), step=0.1)
    with wcol2:
        if st.button("체중 저장"):
            insert_weight(date.today(), float(weight_input))
            st.success("체중이 저장되었습니다.")

# ----------------------------- 탭: 통계 ----------------------------- #
with TAB2:
    st.subheader("📈 추이 시각화")
    meals_df = load_df("meals")
    acts_df = load_df("activities")
    w_df = load_df("weights")

    if not meals_df.empty:
        meals_df["d"] = pd.to_datetime(meals_df["dt"]).dt.date
        kcal_by_day = meals_df.groupby("d")["calories"].sum().reset_index().rename(columns={"calories": "intake_kcal"})
        carb_by_day = meals_df.groupby("d")["carbs_g"].sum().reset_index().rename(columns={"carbs_g": "carb_g"})
    else:
        kcal_by_day = pd.DataFrame(columns=["d", "intake_kcal"]) 
        carb_by_day = pd.DataFrame(columns=["d", "carb_g"]) 

    if not acts_df.empty:
        acts_df["d"] = pd.to_datetime(acts_df["dt"]).dt.date
        out_kcal = acts_df.groupby("d")["calories"].sum().reset_index().rename(columns={"calories": "burn_kcal"})
        steps_by_day = acts_df.groupby("d")["steps"].sum(min_count=1).reset_index().rename(columns={"steps": "steps"})
    else:
        out_kcal = pd.DataFrame(columns=["d", "burn_kcal"]) 
        steps_by_day = pd.DataFrame(columns=["d", "steps"]) 

    daily = pd.merge(kcal_by_day, out_kcal, on="d", how="outer")
    daily = pd.merge(daily, carb_by_day, on="d", how="outer")
    if not w_df.empty:
        w_df["d"] = pd.to_datetime(w_df["d"]).dt.date
        daily = pd.merge(daily, w_df[["d", "weight_kg"]], on="d", how="outer")

    daily = daily.sort_values("d")
    daily_calorie_target_line = load_df("profile")["daily_calorie_target"].iloc[0] if not load_df("profile").empty else 0
    daily_carb_target_line = load_df("profile")["daily_carb_target_g"].iloc[0] if not load_df("profile").empty else 0

    daily_fill = daily.fillna({"intake_kcal":0, "burn_kcal":0, "carb_g":0})

    if daily_fill.empty:
        st.info("아직 통계에 표시할 데이터가 없습니다. '오늘 기록'에서 식단/운동/체중을 입력해 주세요.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.write("체중 추이 (kg)")
            if "weight_kg" in daily_fill.columns and daily_fill["weight_kg"].notna().any():
                chart_w = alt.Chart(daily_fill.dropna(subset=["weight_kg"])) \
                    .mark_line(point=True) \
                    .encode(x=alt.X("d:T", title="날짜"), y=alt.Y("weight_kg:Q", title="체중(kg)"))
                st.altair_chart(chart_w, use_container_width=True)
            else:
                st.info("체중 데이터가 아직 없습니다.")

        with c2:
            st.write("칼로리 섭취/소모")
            melt = daily_fill.melt(id_vars=["d"], value_vars=["intake_kcal", "burn_kcal"], var_name="type", value_name="kcal")
            chart_c = alt.Chart(melt).mark_bar().encode(
                x=alt.X("d:T", title="날짜"),
                y=alt.Y("kcal:Q", title="kcal"),
                color="type:N",
                tooltip=["d:T", "type:N", "kcal:Q"],
            )
            st.altair_chart(chart_c, use_container_width=True)

        st.write("일일 탄수화물(g)")
        chart_carbs = alt.Chart(daily_fill).mark_line(point=True).encode(
            x=alt.X("d:T", title="날짜"),
            y=alt.Y("carb_g:Q", title="탄수화물(g)"),
        )
        if daily_carb_target_line:
            rule = alt.Chart(pd.DataFrame({"y": [daily_carb_target_line]})).mark_rule().encode(y="y:Q")
            st.altair_chart(chart_carbs + rule, use_container_width=True)
        else:
            st.altair_chart(chart_carbs, use_container_width=True)

        st.write("일일 걸음수")
        if not steps_by_day.empty and steps_by_day["steps"].notna().any():
            chart_s = alt.Chart(steps_by_day.fillna({"steps":0})).mark_bar().encode(
                x=alt.X("d:T", title="날짜"),
                y=alt.Y("steps:Q", title="걸음수"),
            )
            st.altair_chart(chart_s, use_container_width=True)
        else:
            st.info("걸음수 데이터가 아직 없습니다.")

# ----------------------------- 탭: 가이드 ----------------------------- #
with TAB3:
    st.subheader("🥗 식단 가이드 (당뇨 전단계 & 갱년기 친화)")
    st.markdown(
        """
        - 하루 3끼 + 필요 시 간식 1회, 식사 간격 3~4시간 권장
        - 현미/잡곡, 채소, 단백질(생선·두부·계란·닭가슴살), 견과류 중심의 균형
        - 정제 탄수화물·설탕·달콤한 음료 최소화, 과일은 1~2회/일 소량
        - 탄수화물 목표: 약 150 g/일부터 시작해 반응(공복/식후 혈당, 체중)에 맞춰 조정

        **예시 식단표** (각 400~600 kcal 범위에서 조정)
        - 아침: 현미밥 1/2공기 + 달걀 1개 + 샐러드 + 두부 100g
        - 점심: 곤약/현미국수 + 닭가슴살 100~120g + 샐러드 + 올리브오일 드레싱
        - 저녁: 생선(연어/고등어) 120g + 찐브로콜리/시금치 + 두부/콩류 소량
        - 간식(선택): 플레인 요거트 + 아몬드 한 줌(20~25g) 또는 방울토마토

        💡 외식/반찬 팁: 밥 양 반공기부터, 국물은 건더기 위주, 튀김/전은 적게, 소스는 따로.
        """
    )

    st.subheader("🚶 걷기 운동 가이드 (무릎 친화)")
    st.markdown(
        """
        - 목표: 주 5일, 회당 30~45분 빠른 걷기(평지 위주). 통증 3/10 이하 유지.
        - 속도: 편안한 대화가 가능한 4.0~5.0 km/h부터 시작, 점진적 증가.
        - 신발: 쿠셔닝 좋은 워킹화, 경사/계단/러닝/스쿼트 회피.
        - 보강: 2~3일/주 둔근·햄스트링·종아리 가벼운 근지구력(통증 없는 범위, 밴드/체중 저항)
        - 준비/마무리: 5~10분 워밍업/쿨다운 + 종아리/햄스트링 스트레칭.
        """
    )

    st.info("혈당·체중 반응은 개인차가 큽니다. 이상 증상 시 전문의와 상의하세요.")

# ----------------------------- 추가: 내보내기/가져오기 ----------------------------- #
with st.expander("데이터 내보내기/가져오기"):
    export_btn = st.button("CSV로 내보내기(zip)")
    if export_btn:
        meals = load_df("meals")
        acts = load_df("activities")
        weights = load_df("weights")
        from zipfile import ZipFile
        zip_path = "data/export_predicare.zip"
        with ZipFile(zip_path, 'w') as zf:
            meals.to_csv("data/meals.csv", index=False)
            acts.to_csv("data/activities.csv", index=False)
            weights.to_csv("data/weights.csv", index=False)
            zf.write("data/meals.csv", arcname="meals.csv")
            zf.write("data/activities.csv", arcname="activities.csv")
            zf.write("data/weights.csv", arcname="weights.csv")
        with open(zip_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        href = f'<a download="predicare_export.zip" href="data:file/zip;base64,{b64}">ZIP 다운로드</a>'
        st.markdown(href, unsafe_allow_html=True)

    st.markdown("**주의**: 브라우저/실행 환경에 따라 파일 저장 경로가 달라질 수 있습니다.")

# ----------------------------- requirements 안내 ----------------------------- #
with st.expander("requirements.txt 예시"):
    st.code(
        """
        streamlit
        altair
        pandas
        numpy
        pillow
        """.strip(), language="text")
# PrediCare: 스트림릿 개인 체중·혈당 관리 앱 (이미지 식단 기록 + 걷기 중심 운동)
# --------------------------------------------------------------
# 변경 내역 (2025-10-23)
# - ✅ API 없이도 동작하는 "내장 음식 DB 기반 자동 칼로리/탄수화물 계산" 추가
# - ✅ "식단 템플릿 불러오기" 버튼(가이드 식단표 바로 채우기)
# - ✅ 섭취 시간: 선택(time_input) + 직접 입력(HH:MM) 모두 지원
# - ⚠️ 사진만으로 자동 인식은 외부 AI/비전 API 없이는 불가 → 대신 사진 첨부 + 음식 선택으로 계산
# --------------------------------------------------------------

import os
import io
import math
import base64
from datetime import datetime, date, time, timedelta
from typing import List, Tuple, Optional, Dict

import pandas as pd
import numpy as np
import streamlit as st
import altair as alt
import sqlite3

APP_NAME = "PrediCare"
DB_PATH = "data/health.db"
IMG_DIR = "data/meal_photos"

# ----------------------------- 유틸 & 초기화 ----------------------------- #

def ensure_dirs():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    os.makedirs(IMG_DIR, exist_ok=True)


def get_conn():
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS profile (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            birth_year INTEGER,
            sex TEXT,
            height_cm REAL,
            weight_kg REAL,
            target_weight_kg REAL,
            daily_calorie_target INTEGER,
            daily_carb_target_g INTEGER,
            knee_care INTEGER DEFAULT 1
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dt TEXT,
            label TEXT,
            items TEXT,
            calories REAL,
            carbs_g REAL,
            photo_path TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dt TEXT,
            kind TEXT,
            minutes REAL,
            steps INTEGER,
            distance_km REAL,
            pace_kmh REAL,
            calories REAL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS weights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            d TEXT,
            weight_kg REAL
        )
        """
    )
    conn.commit()


@st.cache_data(show_spinner=False)
def load_df(table: str) -> pd.DataFrame:
    conn = get_conn()
    return pd.read_sql_query(f"SELECT * FROM {table}", conn)


def refresh_cache():
    load_df.clear()


# ----------------------------- 계산 로직 ----------------------------- #

def bmr_mifflin(weight_kg: float, height_cm: float, age: int, sex: str) -> float:
    s = 5 if sex.lower().startswith("m") else -161
    return 10 * weight_kg + 6.25 * height_cm - 5 * age + s


def tdee_from_activity(bmr: float, activity_level: str) -> float:
    factors = {"낮음": 1.2, "보통": 1.375, "활동적": 1.55, "매우 활동적": 1.725}
    return bmr * factors.get(activity_level, 1.375)


def walking_met(pace_kmh: float) -> float:
    if pace_kmh <= 3.5: return 3.0
    if pace_kmh <= 4.5: return 3.8
    if pace_kmh <= 5.5: return 4.8
    if pace_kmh <= 6.4: return 6.0
    return 6.5


def kcal_from_met(met: float, weight_kg: float, minutes: float) -> float:
    return met * 3.5 * weight_kg / 200 * minutes


# ----------------------------- 내장 음식 DB (API 없이 계산) ----------------------------- #
# 1인분 기준 칼로리/탄수화물(g) 간이치. 필요시 자유롭게 확장하세요.
FOOD_DB: Dict[str, Dict[str, float]] = {
    # 곡류/밥
    "현미밥 1/2공기(100g)": {"kcal": 150, "carb": 33},
    "현미밥 1공기(200g)": {"kcal": 300, "carb": 66},
    "잡곡밥 1공기": {"kcal": 320, "carb": 68},
    "곤약밥 1공기": {"kcal": 180, "carb": 40},
    # 단백질
    "닭가슴살 100g": {"kcal": 165, "carb": 0},
    "두부 100g": {"kcal": 80, "carb": 2},
    "계란 1개": {"kcal": 70, "carb": 0.6},
    "연어 120g": {"kcal": 240, "carb": 0},
    "고등어 120g": {"kcal": 250, "carb": 0},
    # 채소/샐러드
    "샐러드(채소) 1접시": {"kcal": 60, "carb": 8},
    "찐브로콜리 1접시": {"kcal": 55, "carb": 11},
    "시금치나물 1접시": {"kcal": 70, "carb": 7},
    # 곡/면 대체
    "곤약면 1인분": {"kcal": 25, "carb": 2},
    "현미국수 1인분": {"kcal": 380, "carb": 78},
    # 간식/유제품/견과
    "플레인 요거트 150g": {"kcal": 95, "carb": 11},
    "아몬드 25g": {"kcal": 145, "carb": 5},
    "방울토마토 10개": {"kcal": 30, "carb": 7},
    # 과일(소량)
    "사과 1/2개": {"kcal": 50, "carb": 14},
    "바나나 1/2개": {"kcal": 45, "carb": 12},
    # 조미/지방(선택)
    "올리브오일 1작은술": {"kcal": 40, "carb": 0},
}

TEMPLATES = {
    "아침(예시)": ["현미밥 1/2공기(100g)", "계란 1개", "샐러드(채소) 1접시", "두부 100g"],
    "점심(예시)": ["곤약면 1인분", "닭가슴살 100g", "샐러드(채소) 1접시", "올리브오일 1작은술"],
    "저녁(예시)": ["연어 120g", "찐브로콜리 1접시", "두부 100g"],
    "간식(예시)": ["플레인 요거트 150g", "아몬드 25g"],
}


def compute_nutrition(selected: List[str], servings: Dict[str, float]) -> Tuple[float, float]:
    kcal = 0.0
    carb = 0.0
    for item in selected:
        base = FOOD_DB.get(item, {"kcal": 0, "carb": 0})
        s = servings.get(item, 1.0)
        kcal += base["kcal"] * s
        carb += base["carb"] * s
    return kcal, carb


# ----------------------------- DB 헬퍼 ----------------------------- #

def upsert_profile(**kwargs):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id FROM profile WHERE id = 1")
    exists = cur.fetchone() is not None
    cols = [k for k in kwargs.keys()]
    vals = [kwargs[k] for k in cols]
    if exists:
        set_clause = ", ".join([f"{c} = ?" for c in cols])
        cur.execute(f"UPDATE profile SET {set_clause} WHERE id = 1", vals)
    else:
        col_clause = ", ".join(cols)
        q = ",".join(["?"] * len(cols))
        cur.execute(f"INSERT INTO profile(id, {col_clause}) VALUES (1, {q})", vals)
    conn.commit()
    refresh_cache()


def insert_meal(dt: datetime, label: str, items: str, calories: float, carbs_g: float, photo_path: Optional[str]):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO meals(dt, label, items, calories, carbs_g, photo_path) VALUES (?,?,?,?,?,?)",
        (dt.isoformat(), label, items, calories, carbs_g, photo_path),
    )
    conn.commit()
    refresh_cache()


def insert_activity(dt: datetime, kind: str, minutes: float, steps: Optional[int], distance_km: Optional[float], pace_kmh: Optional[float], calories: float):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO activities(dt, kind, minutes, steps, distance_km, pace_kmh, calories) VALUES (?,?,?,?,?,?,?)",
        (dt.isoformat(), kind, minutes, steps, distance_km, pace_kmh, calories),
    )
    conn.commit()
    refresh_cache()


def insert_weight(d: date, weight_kg: float):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO weights(d, weight_kg) VALUES (?,?)", (d.isoformat(), weight_kg))
    conn.commit()
    refresh_cache()


# ----------------------------- 스트림릿 UI ----------------------------- #

st.set_page_config(page_title=f"{APP_NAME}", page_icon="🍎", layout="wide")
init_db()

st.title("🍎 PrediCare — 걷기 기반 당뇨 전단계 체중 관리")
st.caption("*개인 건강 참고용 도구입니다. 의학적 진단/치료를 대체하지 않습니다.*")

with st.sidebar:
    st.header("프로필 & 목표")
    today = date.today()
    default_birth_year = today.year - 52

    col1, col2 = st.columns(2)
    with col1:
        birth_year = st.number_input("출생연도", min_value=1930, max_value=today.year, value=default_birth_year, step=1)
    with col2:
        sex = st.selectbox("성별", ["여성", "남성"], index=0)

    height_cm = st.number_input("키 (cm)", min_value=120.0, max_value=210.0, value=160.0, step=0.5)
    weight_kg = st.number_input("현재 체중 (kg)", min_value=35.0, max_value=200.0, value=65.0, step=0.1)
    target_weight_kg = st.number_input("목표 체중 (kg)", min_value=35.0, max_value=200.0, value=60.0, step=0.1)

    activity_level = st.select_slider("평소 활동량", options=["낮음", "보통", "활동적", "매우 활동적"], value="보통")
    knee_care = st.checkbox("무릎 보호 모드 (전방십자인대 수술 이력)", value=True)

    age = today.year - int(birth_year)
    bmr = bmr_mifflin(weight_kg, height_cm, age, sex)
    tdee = tdee_from_activity(bmr, activity_level)

    st.write(f"BMR(기초대사량): **{int(bmr)}** kcal/일")
    st.write(f"TDEE(유지 칼로리): **{int(tdee)}** kcal/일")

    deficit = 300
    daily_calorie_target = int(max(1200, tdee - deficit))
    daily_carb_target_g = 150

    st.write(f"권장 섭취열량: **{daily_calorie_target} kcal/일** (약 -{deficit} kcal)")
    st.write(f"권장 탄수화물: **{daily_carb_target_g} g/일**")

    if st.button("목표 저장/업데이트"):
        upsert_profile(
            birth_year=birth_year,
            sex=sex,
            height_cm=height_cm,
            weight_kg=weight_kg,
            target_weight_kg=target_weight_kg,
            daily_calorie_target=daily_calorie_target,
            daily_carb_target_g=daily_carb_target_g,
            knee_care=1 if knee_care else 0,
        )
        st.success("프로필이 저장되었습니다.")

# 탭 구성
TAB1, TAB2, TAB3 = st.tabs(["오늘 기록", "통계", "가이드"])

# ----------------------------- 탭: 오늘 기록 ----------------------------- #
with TAB1:
    st.subheader("📸 식단 기록 (사진 업로드 / 내장 DB 자동계산 / 수동 입력)")

    col_a, col_b = st.columns([1, 1])
    with col_a:
        meal_label = st.selectbox("식사 구분", ["아침", "점심", "저녁", "간식"])

        # 시간: 선택 + 직접 입력(HH:MM)
        meal_time_select = st.time_input("섭취 시간(선택)", value=datetime.now().time())
        meal_time_text = st.text_input("섭취 시간 직접 입력(HH:MM)", value="")
        def _parse_time(txt: str) -> Optional[time]:
            try:
                if not txt: return None
                hh, mm = txt.strip().split(":")
                return time(hour=int(hh), minute=int(mm))
            except Exception:
                return None
        meal_time = _parse_time(meal_time_text) or meal_time_select

        uploaded = st.file_uploader("음식 사진 업로드 (선택)", type=["jpg", "jpeg", "png"], help="사진은 기록/미리보기 용도입니다. API 없이 자동 인식은 불가합니다.")

        st.markdown("**방법 A. 내장 음식 DB로 자동 계산(권장, API 불필요)**")
        selected_items = st.multiselect("음식 선택", options=sorted(FOOD_DB.keys()))

        servings = {}
        if selected_items:
            st.write("인분/분량 조정")
            for it in selected_items:
                servings[it] = st.number_input(f"{it} x", min_value=0.0, max_value=10.0, value=1.0, step=0.25, key=f"srv_{it}")
        kcal_auto, carb_auto = compute_nutrition(selected_items, servings)
        st.info(f"자동 계산 결과 → 칼로리: **{int(kcal_auto)} kcal**, 탄수화물: **{int(carb_auto)} g**")

        st.markdown("**방법 B. 직접 입력(라벨/앱 참조값)**")
        items_text = st.text_area("음식 항목 (쉼표로 구분)", placeholder="예: 현미밥 1/2공기, 닭가슴살 100g, 샐러드, 두부 100g")
        calories = st.number_input("총 칼로리(kcal)", min_value=0.0, max_value=5000.0, value=float(kcal_auto), step=10.0)
        carbs_g = st.number_input("총 탄수화물(g)", min_value=0.0, max_value=1000.0, value=float(carb_auto), step=1.0)

        # 템플릿 불러오기
        st.markdown("**빠른 입력: 예시 식단 템플릿**")
        tcol1, tcol2, tcol3, tcol4 = st.columns(4)
        if tcol1.button("아침(예시) 불러오기"):
            items_text = ", ".join(TEMPLATES["아침(예시)"])
            st.session_state["_tmp_items_text"] = items_text
        if tcol2.button("점심(예시) 불러오기"):
            items_text = ", ".join(TEMPLATES["점심(예시)"])
            st.session_state["_tmp_items_text"] = items_text
        if tcol3.button("저녁(예시) 불러오기"):
            items_text = ", ".join(TEMPLATES["저녁(예시)"])
            st.session_state["_tmp_items_text"] = items_text
        if tcol4.button("간식(예시) 불러오기"):
            items_text = ", ".join(TEMPLATES["간식(예시)"])
            st.session_state["_tmp_items_text"] = items_text
        # 버튼으로 채운 텍스트 반영
        if st.session_state.get("_tmp_items_text"):
            items_text = st.session_state["_tmp_items_text"]
            st.text_area("템플릿 적용됨", items_text, key="items_text_applied")
            # 템플릿 영양 자동 계산
            servings_tmp = {it:1.0 for it in items_text.split(", ") if it in FOOD_DB}
            kcal_t, carb_t = compute_nutrition(list(servings_tmp.keys()), servings_tmp)
            calories = kcal_t
            carbs_g = carb_t
            st.info(f"템플릿 자동 계산 → {int(kcal_t)} kcal / {int(carb_t)} g")

        if st.button("식단 저장"):
            # 이미지 저장
            photo_path = None
            if uploaded is not None:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                ext = os.path.splitext(uploaded.name)[1].lower()
                photo_path = os.path.join(IMG_DIR, f"meal_{ts}{ext}")
                with open(photo_path, "wb") as f:
                    f.write(uploaded.getvalue())

            # 저장할 항목 문자열 구성(선택+수동 합침)
            auto_items_str = ", ".join([f"{k} x{servings.get(k,1)}" for k in selected_items])
            items_final = ", ".join([s for s in [auto_items_str, items_text.strip()] if s])
            # 시간 합성
            dt = datetime.combine(date.today(), meal_time)
            insert_meal(dt, meal_label, items_final, float(calories), float(carbs_g), photo_path)
            st.success("식단이 저장되었습니다.")

    with col_b:
        st.write("오늘 입력된 식단")
        meals_df = load_df("meals")
        if not meals_df.empty:
            meals_df["date"] = pd.to_datetime(meals_df["dt"]).dt.date
            today_df = meals_df[meals_df["date"] == date.today()]
            if today_df.empty:
                st.info("아직 오늘 식단 기록이 없습니다.")
            else:
                st.dataframe(
                    today_df[["dt", "label", "items", "calories", "carbs_g"]]
                    .rename(columns={"dt": "시간", "label": "구분", "items": "항목", "calories": "kcal", "carbs_g": "탄수(g)"})
                    .sort_values("시간"),
                    use_container_width=True,
                )
        else:
            st.info("아직 식단 데이터가 없습니다.")

    st.markdown("---")
    st.subheader("🚶 걷기 기록")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        minutes = st.number_input("운동 시간(분)", min_value=0.0, max_value=600.0, value=30.0, step=5.0)
    with col2:
        distance_km = st.number_input("거리(km) (선택)", min_value=0.0, max_value=50.0, value=0.0, step=0.1)
    with col3:
        steps = st.number_input("걸음수 (선택)", min_value=0, max_value=100000, value=0, step=100)
    with col4:
        pace_kmh = st.number_input("평균 속도(km/h) (선택)", min_value=0.0, max_value=12.0, value=4.5, step=0.1)

    if pace_kmh and minutes and distance_km == 0:
        distance_km = pace_kmh * (minutes / 60)
    if distance_km and minutes and pace_kmh == 0:
        pace_kmh = (distance_km / (minutes / 60)) if minutes > 0 else 0

    met = walking_met(pace_kmh if pace_kmh > 0 else 4.0)
    kcal = kcal_from_met(met, weight_kg, minutes)
    st.write(f"예상 소모 칼로리: **{int(kcal)} kcal** (MET {met:.1f})")

    if st.button("걷기 저장"):
        dt = datetime.now()
        insert_activity(dt, "걷기", float(minutes), int(steps) if steps else None, float(distance_km) if distance_km else None, float(pace_kmh) if pace_kmh else None, float(kcal))
        st.success("운동이 저장되었습니다.")

    st.markdown("---")
    st.subheader("⚖️ 체중 기록")
    wcol1, wcol2 = st.columns([1,1])
    with wcol1:
        weight_input = st.number_input("오늘 체중 (kg)", min_value=30.0, max_value=250.0, value=float(weight_kg), step=0.1)
    with wcol2:
        if st.button("체중 저장"):
            insert_weight(date.today(), float(weight_input))
            st.success("체중이 저장되었습니다.")

# ----------------------------- 탭: 통계 ----------------------------- #
with TAB2:
    st.subheader("📈 추이 시각화")
    meals_df = load_df("meals")
    acts_df = load_df("activities")
    w_df = load_df("weights")

    if not meals_df.empty:
        meals_df["d"] = pd.to_datetime(meals_df["dt"]).dt.date
        kcal_by_day = meals_df.groupby("d")["calories"].sum().reset_index().rename(columns={"calories": "intake_kcal"})
        carb_by_day = meals_df.groupby("d")["carbs_g"].sum().reset_index().rename(columns={"carbs_g": "carb_g"})
    else:
        kcal_by_day = pd.DataFrame(columns=["d", "intake_kcal"]) 
        carb_by_day = pd.DataFrame(columns=["d", "carb_g"]) 

    if not acts_df.empty:
        acts_df["d"] = pd.to_datetime(acts_df["dt"]).dt.date
        out_kcal = acts_df.groupby("d")["calories"].sum().reset_index().rename(columns={"calories": "burn_kcal"})
        steps_by_day = acts_df.groupby("d")["steps"].sum(min_count=1).reset_index().rename(columns={"steps": "steps"})
    else:
        out_kcal = pd.DataFrame(columns=["d", "burn_kcal"]) 
        steps_by_day = pd.DataFrame(columns=["d", "steps"]) 

    daily = pd.merge(kcal_by_day, out_kcal, on="d", how="outer")
    daily = pd.merge(daily, carb_by_day, on="d", how="outer")
    if not w_df.empty:
        w_df["d"] = pd.to_datetime(w_df["d"]).dt.date
        daily = pd.merge(daily, w_df[["d", "weight_kg"]], on="d", how="outer")

    daily = daily.sort_values("d")
    daily_calorie_target_line = load_df("profile")["daily_calorie_target"].iloc[0] if not load_df("profile").empty else 0
    daily_carb_target_line = load_df("profile")["daily_carb_target_g"].iloc[0] if not load_df("profile").empty else 0

    daily_fill = daily.fillna({"intake_kcal":0, "burn_kcal":0, "carb_g":0})

    if daily_fill.empty:
        st.info("아직 통계에 표시할 데이터가 없습니다. '오늘 기록'에서 식단/운동/체중을 입력해 주세요.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.write("체중 추이 (kg)")
            if "weight_kg" in daily_fill.columns and daily_fill["weight_kg"].notna().any():
                chart_w = alt.Chart(daily_fill.dropna(subset=["weight_kg"])) \
                    .mark_line(point=True) \
                    .encode(x=alt.X("d:T", title="날짜"), y=alt.Y("weight_kg:Q", title="체중(kg)"))
                st.altair_chart(chart_w, use_container_width=True)
            else:
                st.info("체중 데이터가 아직 없습니다.")

        with c2:
            st.write("칼로리 섭취/소모")
            melt = daily_fill.melt(id_vars=["d"], value_vars=["intake_kcal", "burn_kcal"], var_name="type", value_name="kcal")
            chart_c = alt.Chart(melt).mark_bar().encode(
                x=alt.X("d:T", title="날짜"),
                y=alt.Y("kcal:Q", title="kcal"),
                color="type:N",
                tooltip=["d:T", "type:N", "kcal:Q"],
            )
            st.altair_chart(chart_c, use_container_width=True)

        st.write("일일 탄수화물(g)")
        chart_carbs = alt.Chart(daily_fill).mark_line(point=True).encode(
            x=alt.X("d:T", title="날짜"),
            y=alt.Y("carb_g:Q", title="탄수화물(g)"),
        )
        if daily_carb_target_line:
            rule = alt.Chart(pd.DataFrame({"y": [daily_carb_target_line]})).mark_rule().encode(y="y:Q")
            st.altair_chart(chart_carbs + rule, use_container_width=True)
        else:
            st.altair_chart(chart_carbs, use_container_width=True)

        st.write("일일 걸음수")
        if not steps_by_day.empty and steps_by_day["steps"].notna().any():
            chart_s = alt.Chart(steps_by_day.fillna({"steps":0})).mark_bar().encode(
                x=alt.X("d:T", title="날짜"),
                y=alt.Y("steps:Q", title="걸음수"),
            )
            st.altair_chart(chart_s, use_container_width=True)
        else:
            st.info("걸음수 데이터가 아직 없습니다.")

# ----------------------------- 탭: 가이드 ----------------------------- #
with TAB3:
    st.subheader("🥗 식단 가이드 (당뇨 전단계 & 갱년기 친화)")
    st.markdown(
        """
        - 하루 3끼 + 필요 시 간식 1회, 식사 간격 3~4시간 권장
        - 현미/잡곡, 채소, 단백질(생선·두부·계란·닭가슴살), 견과류 중심의 균형
        - 정제 탄수화물·설탕·달콤한 음료 최소화, 과일은 1~2회/일 소량
        - 탄수화물 목표: 약 150 g/일부터 시작해 반응(공복/식후 혈당, 체중)에 맞춰 조정

        **예시 식단표** (각 400~600 kcal 범위에서 조정)
        - 아침: 현미밥 1/2공기 + 달걀 1개 + 샐러드 + 두부 100g
        - 점심: 곤약/현미국수 + 닭가슴살 100~120g + 샐러드 + 올리브오일 드레싱
        - 저녁: 생선(연어/고등어) 120g + 찐브로콜리/시금치 + 두부/콩류 소량
        - 간식(선택): 플레인 요거트 + 아몬드 한 줌(20~25g) 또는 방울토마토

        💡 외식/반찬 팁: 밥 양 반공기부터, 국물은 건더기 위주, 튀김/전은 적게, 소스는 따로.
        """
    )

    st.subheader("🚶 걷기 운동 가이드 (무릎 친화)")
    st.markdown(
        """
        - 목표: 주 5일, 회당 30~45분 빠른 걷기(평지 위주). 통증 3/10 이하 유지.
        - 속도: 편안한 대화가 가능한 4.0~5.0 km/h부터 시작, 점진적 증가.
        - 신발: 쿠셔닝 좋은 워킹화, 경사/계단/러닝/스쿼트 회피.
        - 보강: 2~3일/주 둔근·햄스트링·종아리 가벼운 근지구력(통증 없는 범위, 밴드/체중 저항)
        - 준비/마무리: 5~10분 워밍업/쿨다운 + 종아리/햄스트링 스트레칭.
        """
    )

    st.info("혈당·체중 반응은 개인차가 큽니다. 이상 증상 시 전문의와 상의하세요.")

# ----------------------------- 추가: 내보내기/가져오기 ----------------------------- #
with st.expander("데이터 내보내기/가져오기"):
    export_btn = st.button("CSV로 내보내기(zip)")
    if export_btn:
        meals = load_df("meals")
        acts = load_df("activities")
        weights = load_df("weights")
        from zipfile import ZipFile
        zip_path = "data/export_predicare.zip"
        with ZipFile(zip_path, 'w') as zf:
            meals.to_csv("data/meals.csv", index=False)
            acts.to_csv("data/activities.csv", index=False)
            weights.to_csv("data/weights.csv", index=False)
            zf.write("data/meals.csv", arcname="meals.csv")
            zf.write("data/activities.csv", arcname="activities.csv")
            zf.write("data/weights.csv", arcname="weights.csv")
        with open(zip_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        href = f'<a download="predicare_export.zip" href="data:file/zip;base64,{b64}">ZIP 다운로드</a>'
        st.markdown(href, unsafe_allow_html=True)

    st.markdown("**주의**: 브라우저/실행 환경에 따라 파일 저장 경로가 달라질 수 있습니다.")

# ----------------------------- requirements 안내 ----------------------------- #
with st.expander("requirements.txt 예시"):
    st.code(
        """
        streamlit
        altair
        pandas
        numpy
        pillow
        """.strip(), language="text")
