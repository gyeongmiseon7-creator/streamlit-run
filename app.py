import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import json

# Plotly 임포트 (Streamlit 호환)
try:
    import plotly.graph_objs as go
    import plotly.express as px
except:
    import plotly.graph_objects as go
    import plotly.express as px

# 페이지 설정
st.set_page_config(page_title="나의 건강 관리", layout="wide", page_icon="🏥")

# 세션 상태 초기화
if 'weight_data' not in st.session_state:
    st.session_state.weight_data = []
if 'meal_data' not in st.session_state:
    st.session_state.meal_data = []
if 'exercise_data' not in st.session_state:
    st.session_state.exercise_data = []

# 당뇨 관리 친화적인 음식 목록 (100개)
FOOD_DATABASE = {
    # 채소류 (20개)
    "시금치나물(70g)": 20, "브로콜리(100g)": 35, "양배추(100g)": 25, "오이(100g)": 15,
    "토마토(100g)": 18, "당근(100g)": 41, "파프리카(100g)": 26, "양상추(100g)": 15,
    "배추(100g)": 13, "무(100g)": 18, "가지(100g)": 25, "호박(100g)": 20,
    "콩나물(100g)": 30, "숙주나물(100g)": 28, "미역(20g)": 10, "김(10g)": 20,
    "청경채(100g)": 13, "근대(100g)": 19, "깻잎(20g)": 10, "상추(50g)": 8,
    
    # 단백질류 (20개)
    "닭가슴살(100g)": 165, "계란1개": 78, "두부(80g)": 60, "연어(100g)": 206,
    "고등어구이(100g)": 205, "참치캔(80g)": 110, "새우(100g)": 99, "오징어(100g)": 92,
    "명태(100g)": 83, "삶은달걀(1개)": 78, "계란흰자(1개)": 17, "닭안심(100g)": 114,
    "소고기(살코기100g)": 201, "돼지고기(살코기100g)": 143, "흰살생선(100g)": 82,
    "콩(30g)": 120, "병아리콩(50g)": 82, "렌틸콩(50g)": 58, "검은콩(30g)": 114,
    "아몬드(15g)": 87,
    
    # 곡류 (20개)
    "현미밥(210g, 1공기)": 310, "귀리(40g)": 152, "퀴노아(50g)": 185, "보리(40g)": 143,
    "통밀빵(1조각, 40g)": 92, "고구마(중1개, 130g)": 130, "감자(중1개, 150g)": 115,
    "단호박(100g)": 47, "옥수수(1개, 150g)": 132, "흑미밥(210g)": 315,
    "잡곡밥(210g)": 320, "메밀국수(100g)": 343, "현미죽(1그릇)": 180,
    "통밀파스타(100g)": 348, "우엉(100g)": 58, "연근(100g)": 66,
    "밤(5개)": 170, "은행(20알)": 90, "토란(100g)": 58, "무말랭이(30g)": 85,
    
    # 과일류 (15개)
    "사과(중1개, 200g)": 104, "배(중1개, 250g)": 103, "귤(1개, 100g)": 45,
    "딸기(100g)": 32, "블루베리(100g)": 57, "키위(1개, 100g)": 61,
    "자몽(1/2개, 150g)": 52, "오렌지(1개, 150g)": 62, "수박(200g)": 60,
    "참외(1/2개, 200g)": 62, "복숭아(중1개, 150g)": 59, "체리(100g)": 63,
    "멜론(200g)": 68, "자두(1개, 80g)": 38, "포도(100g)": 69,
    
    # 유제품 및 기타 (15개)
    "무가당요거트(150ml)": 90, "저지방우유(200ml)": 90, "두유(200ml)": 95,
    "그릭요거트(100g)": 59, "코티지치즈(50g)": 52, "모짜렐라치즈(30g)": 85,
    "아몬드우유(200ml)": 39, "케피어(150ml)": 80, "리코타치즈(50g)": 87,
    "페타치즈(30g)": 75, "저지방치즈(20g)": 50, "플레인요거트(100g)": 61,
    "카망베르치즈(30g)": 85, "염소치즈(30g)": 76, "무가당두유(200ml)": 81,
    
    # 견과류 및 씨앗 (10개)
    "호두(10g)": 65, "땅콩(15g)": 87, "캐슈넛(15g)": 82, "피스타치오(15g)": 85,
    "해바라기씨(15g)": 88, "호박씨(15g)": 84, "치아시드(10g)": 49,
    "아마씨(10g)": 55, "참깨(10g)": 57, "잣(10g)": 67
}

# 무릎 친화적 운동 목록
EXERCISE_DATABASE = {
    "천천히 걷기 (30분)": 120,
    "보통 속도 걷기 (30분)": 150,
    "빠르게 걷기 (30분)": 180,
    "실내 자전거 (가볍게, 30분)": 140,
    "수영 (가볍게, 30분)": 200,
    "수중 걷기 (30분)": 120,
    "요가 (30분)": 90,
    "스트레칭 (30분)": 70,
    "필라테스 (30분)": 100,
    "앉아서 다리 들기 (10분)": 40,
    "벽 푸시업 (10분)": 50,
    "의자 운동 (20분)": 80
}

# 메인 타이틀
st.title("🏥 나의 건강 관리 프로그램")
st.markdown("### 당뇨 관리를 위한 맞춤형 체중 관리 시스템")

# 사이드바 - 프로필
with st.sidebar:
    st.header("👤 내 정보")
    st.info("""
    **연령대**: 50대  
    **상태**: 갱년기, 당뇨 전단계  
    **특이사항**: 무릎 수술 (전방십자인대)  
    **목표**: 건강한 체중 관리
    """)
    
    st.markdown("---")
    st.header("📅 오늘의 목표")
    target_cal = st.number_input("목표 칼로리 (kcal)", 1200, 2000, 1500)
    target_exercise = st.number_input("목표 운동 시간 (분)", 20, 120, 30)

# 탭 생성
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 대시보드", "🍽️ 식단 기록", "🏃 운동 기록", "📈 통계", "📋 음식 목록"])

# 탭1: 대시보드
with tab1:
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("현재 체중", "0 kg", "기록 시작하기")
    
    with col2:
        today_meals = [m for m in st.session_state.meal_data if m['date'] == datetime.now().strftime("%Y-%m-%d")]
        today_cal = sum([m['calories'] for m in today_meals])
        st.metric("오늘 섭취 칼로리", f"{today_cal} kcal", f"{today_cal - target_cal:+.0f} kcal")
    
    with col3:
        today_exercise = [e for e in st.session_state.exercise_data if e['date'] == datetime.now().strftime("%Y-%m-%d")]
        today_burn = sum([e['calories'] for e in today_exercise])
        st.metric("오늘 소모 칼로리", f"{today_burn} kcal", f"{today_burn} kcal")
    
    st.markdown("---")
    
    # 체중 추이 그래프
    if st.session_state.weight_data:
        st.subheader("📉 체중 변화 추이")
        df_weight = pd.DataFrame(st.session_state.weight_data)
        df_weight['date'] = pd.to_datetime(df_weight['date'])
        df_weight = df_weight.sort_values('date')
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_weight['date'], 
            y=df_weight['weight'],
            mode='lines+markers',
            name='체중',
            line=dict(color='#FF6B6B', width=3),
            marker=dict(size=8)
        ))
        fig.update_layout(
            xaxis_title="날짜",
            yaxis_title="체중 (kg)",
            hovermode='x unified',
            height=400
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("체중 데이터를 입력하면 그래프가 표시됩니다.")
    
    # 오늘의 식단 요약
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🍽️ 오늘의 식단")
        if today_meals:
            for meal in today_meals:
                st.write(f"**{meal['time']}** - {meal['food']} ({meal['calories']} kcal)")
        else:
            st.write("아직 기록된 식단이 없습니다.")
    
    with col2:
        st.subheader("🏃 오늘의 운동")
        if today_exercise:
            for exercise in today_exercise:
                st.write(f"**{exercise['exercise']}** - {exercise['calories']} kcal 소모")
        else:
            st.write("아직 기록된 운동이 없습니다.")

# 탭2: 식단 기록
with tab2:
    st.header("🍽️ 식단 기록하기")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        meal_date = st.date_input("날짜", datetime.now())
        meal_time = st.selectbox("시간대", ["아침", "점심", "저녁", "간식"])
        
        # 음식 검색
        search_food = st.text_input("음식 검색 (이름 입력)", placeholder="예: 닭가슴살")
        
        if search_food:
            filtered_foods = {k: v for k, v in FOOD_DATABASE.items() if search_food in k}
            if filtered_foods:
                selected_food = st.selectbox("음식 선택", list(filtered_foods.keys()))
                calories = filtered_foods[selected_food]
                
                st.info(f"**{selected_food}**: {calories} kcal")
                
                # 분량 조절
                portion = st.slider("분량 조절 (%)", 50, 200, 100, 10)
                adjusted_cal = int(calories * portion / 100)
                st.write(f"조절된 칼로리: **{adjusted_cal} kcal**")
                
                if st.button("식단에 추가", type="primary"):
                    st.session_state.meal_data.append({
                        'date': meal_date.strftime("%Y-%m-%d"),
                        'time': meal_time,
                        'food': selected_food,
                        'calories': adjusted_cal,
                        'portion': portion
                    })
                    st.success(f"{selected_food}이(가) 추가되었습니다!")
                    st.rerun()
            else:
                st.warning("검색 결과가 없습니다.")
        else:
            # 카테고리별 추천 음식
            st.subheader("🔍 카테고리별 음식")
            category = st.selectbox("카테고리 선택", 
                ["채소류 (저칼로리)", "단백질류 (포만감)", "곡류 (에너지)", "과일류 (비타민)", "기타"])
            
            category_map = {
                "채소류 (저칼로리)": list(FOOD_DATABASE.keys())[:20],
                "단백질류 (포만감)": list(FOOD_DATABASE.keys())[20:40],
                "곡류 (에너지)": list(FOOD_DATABASE.keys())[40:60],
                "과일류 (비타민)": list(FOOD_DATABASE.keys())[60:75],
                "기타": list(FOOD_DATABASE.keys())[75:]
            }
            
            for food in category_map[category][:10]:
                col_a, col_b, col_c = st.columns([3, 1, 1])
                with col_a:
                    st.write(food)
                with col_b:
                    st.write(f"{FOOD_DATABASE[food]} kcal")
                with col_c:
                    if st.button("추가", key=f"add_{food}"):
                        st.session_state.meal_data.append({
                            'date': meal_date.strftime("%Y-%m-%d"),
                            'time': meal_time,
                            'food': food,
                            'calories': FOOD_DATABASE[food],
                            'portion': 100
                        })
                        st.success("추가됨!")
                        st.rerun()
    
    with col2:
        st.subheader("📸 음식 사진 분석")
        st.info("""
        **개발 예정 기능**
        
        음식 사진을 업로드하면
        AI가 자동으로:
        - 음식 종류 인식
        - 칼로리 계산
        - 영양 정보 제공
        
        현재는 음식 목록에서
        직접 선택해주세요.
        """)
        
        uploaded_file = st.file_uploader("음식 사진 업로드", type=['jpg', 'png', 'jpeg'])
        if uploaded_file:
            st.image(uploaded_file, caption="업로드된 사진", use_container_width=True)
            st.warning("사진 분석 기능은 개발 중입니다.")
    
    # 오늘의 식단 목록
    st.markdown("---")
    st.subheader("📋 기록된 식단")
    
    if st.session_state.meal_data:
        df_meals = pd.DataFrame(st.session_state.meal_data)
        df_meals = df_meals.sort_values('date', ascending=False)
        
        for idx, row in df_meals.head(20).iterrows():
            col1, col2, col3, col4, col5 = st.columns([2, 1, 2, 1, 1])
            with col1:
                st.write(f"**{row['date']}**")
            with col2:
                st.write(row['time'])
            with col3:
                st.write(row['food'])
            with col4:
                st.write(f"{row['calories']} kcal")
            with col5:
                if st.button("삭제", key=f"del_meal_{idx}"):
                    st.session_state.meal_data = [m for i, m in enumerate(st.session_state.meal_data) if i != idx]
                    st.rerun()
    else:
        st.write("아직 기록된 식단이 없습니다.")

# 탭3: 운동 기록
with tab3:
    st.header("🏃 운동 기록하기")
    
    st.info("⚠️ 무릎 건강을 위한 저강도 운동 위주로 구성되어 있습니다.")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        exercise_date = st.date_input("운동 날짜", datetime.now(), key="ex_date")
        
        st.subheader("추천 운동 목록")
        
        for exercise, cal in EXERCISE_DATABASE.items():
            col_a, col_b, col_c = st.columns([3, 1, 1])
            with col_a:
                st.write(f"**{exercise}**")
            with col_b:
                st.write(f"{cal} kcal")
            with col_c:
                if st.button("기록", key=f"ex_{exercise}"):
                    st.session_state.exercise_data.append({
                        'date': exercise_date.strftime("%Y-%m-%d"),
                        'exercise': exercise,
                        'calories': cal
                    })
                    st.success("운동이 기록되었습니다!")
                    st.rerun()
    
    with col2:
        st.subheader("💡 운동 팁")
        st.markdown("""
        **무릎 보호를 위한 주의사항:**
        
        ✅ **추천 운동**
        - 평지 걷기
        - 수영, 수중 걷기
        - 실내 자전거
        - 요가, 스트레칭
        
        ❌ **피해야 할 운동**
        - 등산 (내리막길)
        - 달리기, 조깅
        - 스쿼트, 런지
        - 점프 동작
        
        **운동 전후:**
        - 충분한 스트레칭
        - 무릎 보호대 착용
        - 통증 시 즉시 중단
        """)
    
    # 운동 기록 목록
    st.markdown("---")
    st.subheader("📋 운동 기록")
    
    if st.session_state.exercise_data:
        df_exercise = pd.DataFrame(st.session_state.exercise_data)
        df_exercise = df_exercise.sort_values('date', ascending=False)
        
        for idx, row in df_exercise.head(15).iterrows():
            col1, col2, col3, col4 = st.columns([2, 3, 1, 1])
            with col1:
                st.write(f"**{row['date']}**")
            with col2:
                st.write(row['exercise'])
            with col3:
                st.write(f"{row['calories']} kcal")
            with col4:
                if st.button("삭제", key=f"del_ex_{idx}"):
                    st.session_state.exercise_data = [e for i, e in enumerate(st.session_state.exercise_data) if i != idx]
                    st.rerun()
    else:
        st.write("아직 기록된 운동이 없습니다.")

# 탭4: 통계
with tab4:
    st.header("📈 건강 통계")
    
    # 체중 기록
    st.subheader("⚖️ 체중 기록")
    col1, col2 = st.columns(2)
    
    with col1:
        weight_date = st.date_input("측정 날짜", datetime.now(), key="weight_date")
        weight_value = st.number_input("체중 (kg)", 40.0, 150.0, 60.0, 0.1)
        
        if st.button("체중 기록", type="primary"):
            st.session_state.weight_data.append({
                'date': weight_date.strftime("%Y-%m-%d"),
                'weight': weight_value
            })
            st.success("체중이 기록되었습니다!")
            st.rerun()
    
    with col2:
        if st.session_state.weight_data:
            latest_weight = st.session_state.weight_data[-1]['weight']
            if len(st.session_state.weight_data) > 1:
                prev_weight = st.session_state.weight_data[-2]['weight']
                weight_change = latest_weight - prev_weight
                st.metric("최근 체중", f"{latest_weight} kg", f"{weight_change:+.1f} kg")
            else:
                st.metric("최근 체중", f"{latest_weight} kg")
        else:
            st.info("체중을 기록해주세요.")
    
    # 주간 통계
    st.markdown("---")
    st.subheader("📊 주간 리포트")
    
    # 최근 7일 데이터
    today = datetime.now()
    week_ago = today - timedelta(days=7)
    
    week_meals = [m for m in st.session_state.meal_data 
                  if datetime.strptime(m['date'], "%Y-%m-%d") >= week_ago]
    week_exercise = [e for e in st.session_state.exercise_data 
                     if datetime.strptime(e['date'], "%Y-%m-%d") >= week_ago]
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        total_cal = sum([m['calories'] for m in week_meals])
        avg_cal = total_cal / 7 if total_cal > 0 else 0
        st.metric("주간 평균 섭취", f"{avg_cal:.0f} kcal/일")
    
    with col2:
        total_burn = sum([e['calories'] for e in week_exercise])
        avg_burn = total_burn / 7 if total_burn > 0 else 0
        st.metric("주간 평균 소모", f"{avg_burn:.0f} kcal/일")
    
    with col3:
        net_cal = avg_cal - avg_burn
        st.metric("순 칼로리", f"{net_cal:.0f} kcal/일")
    
    # 일별 칼로리 그래프
    if week_meals or week_exercise:
        st.subheader("📊 일별 칼로리 비교")
        
        dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
        
        intake_by_date = {date: 0 for date in dates}
        burn_by_date = {date: 0 for date in dates}
        
        for meal in week_meals:
            if meal['date'] in intake_by_date:
                intake_by_date[meal['date']] += meal['calories']
        
        for exercise in week_exercise:
            if exercise['date'] in burn_by_date:
                burn_by_date[exercise['date']] += exercise['calories']
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=dates,
            y=[intake_by_date[d] for d in dates],
            name='섭취 칼로리',
            marker_color='#FF6B6B'
        ))
        fig.add_trace(go.Bar(
            x=dates,
            y=[burn_by_date[d] for d in dates],
            name='소모 칼로리',
            marker_color='#4ECDC4'
        ))
        
        fig.update_layout(
            barmode='group',
            xaxis_title="날짜",
            yaxis_title="칼로리 (kcal)",
            height=400
        )
        st.plotly_chart(fig, use_container_width=True)

# 탭5: 음식 목록
with tab5:
    st.header("📋 음식 데이터베이스 (100개)")
    st.write("당뇨 관리에 적합한 음식 목록입니다.")
    
    # 검색 기능
    search = st.text_input("음식 검색", placeholder="음식 이름을 입력하세요")
    
    # 정렬 옵션
    sort_by = st.selectbox("정렬 기준", ["이름순", "칼로리 낮은순", "칼로리 높은순"])
    
    # 음식 목록을 데이터프레임으로
    food_df = pd.DataFrame(list(FOOD_DATABASE.items()), columns=['음식명', '칼로리(kcal)'])
    
    if search:
        food_df = food_df[food_df['음식명'].str.contains(search)]
    
    if sort_by == "칼로리 낮은순":
        food_df = food_df.sort_values('칼로리(kcal)')
    elif sort_by == "칼로리 높은순":
        food_df = food_df.sort_values('칼로리(kcal)', ascending=False)
    else:
        food_df = food_df.sort_values('음식명')
    
    # 카테고리별 필터
    categories = st.multiselect("카테고리 선택", 
        ["채소류", "단백질류", "곡류", "과일류", "유제품", "견과류"],
        default=[])
    
    st.dataframe(food_df, use_container_width=True, height=600)
    
    st.markdown("---")
    st.info("""
    **💡 당뇨 관리 식단 팁:**
    - 채소류를 먼저 충분히 섭취하세요 (포만감 증가)
    - 단백질을 매 끼니마다 포함하세요 (혈당 안정화)
    - 정제 탄수화물 대신 통곡물을 선택하세요
    - 과일은 하루 1-2회, 소량씩 섭취하세요
    - 식사는 천천히, 규칙적으로 하세요
    """)

# 하단 정보
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666;'>
    <p>💚 건강한 하루를 응원합니다!</p>
    <p style='font-size: 0.9em;'>꾸준한 기록이 건강을 만듭니다</p>
</div>
""", unsafe_allow_html=True)
