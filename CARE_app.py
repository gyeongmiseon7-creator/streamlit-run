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
st.altair_chart(chart_carbs + rul
