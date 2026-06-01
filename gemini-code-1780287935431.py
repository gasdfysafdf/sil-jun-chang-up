import streamlit as st
import pandas as pd
from datetime import datetime

# 1. 페이지 기본 설정 및 스타일
st.set_page_config(page_title="스타트리 (Startree)", page_icon="🌳", layout="wide")

st.markdown("""
    <style>
    .main-title { font-size: 36px; font-weight: bold; color: #2E7D32; text-align: center; margin-bottom: 5px; }
    .sub-title { font-size: 16px; color: #666; text-align: center; margin-bottom: 30px; }
    .stProgress > div > div > div > div { background-color: #4CAF50; }
    </style>
""", unsafe_allow_html=True)

# 2. 세션 상태(Session State)를 활용한 가상 데이터 초기화
if 'tasks' not in st.session_state:
    st.session_state.tasks = [
        {"팀원": "김해용", "과제명": "서비스 기획 및 요구사항 정의", "마감일": "2026-04-15", "상태": "완료"},
        {"팀원": "장현석", "과제명": "와이어프레임 및 UI/UX 설계", "마감일": "2026-04-20", "상태": "진행 중"},
        {"팀원": "조성우", "과제명": "데이터베이스 및 백엔드 설계", "마감일": "2026-04-25", "상태": "진행 전"},
    ]

if 'members' not in st.session_state:
    st.session_state.members = ["김해용", "장현석", "조성우"]

# 3. 사이드바 - 팀 관리 및 과제 추가
with st.sidebar:
    st.header("🌳 스타트리 설정실")
    st.subheader("1. 새로운 과제 배정")
    
    with st.form(key='task_form', clear_on_submit=True):
        new_worker = st.selectbox("담당 팀원 선택", st.session_state.members)
        new_task_name = st.text_input("수행할 과제 입력", placeholder="예: 발표 자료 만들기")
        new_due_date = st.date_input("마감일 설정", min_value=datetime.today())
        new_status = st.selectbox("초기 상태", ["진행 전", "진행 중", "완료"])
        
        submit_button = st.form_submit_button(label='과제 등록하기')
        
        if submit_button:
            if new_task_name.strip() == "":
                st.error("과제명을 입력해주세요!")
            else:
                st.session_state.tasks.append({
                    "팀원": new_worker,
                    "과제명": new_task_name,
                    "마감일": str(new_due_date),
                    "상태": new_status
                })
                st.success(f"'{new_worker}' 팀원에게 과제가 배정되었습니다!")

    st.write("---")
    st.subheader("2. 팀원 관리")
    new_member = st.text_input("새로운 팀원 이름 추가")
    if st.button("팀원 초대"):
        if new_member and new_member not in st.session_state.members:
            st.session_state.members.append(new_member)
            st.success(f"{new_member}님이 팀에 합류했습니다.")
            st.rerun()

# 4. 메인 화면 - 대시보드 구성
st.markdown("<div class='main-title'>🌳 스타트리 (Startree)</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-title'>대학생을 위한 ERP 기반 팀 프로젝트 일정 & 역할 관리 매니저</div>", unsafe_allow_html=True)

# 📊 진행 상황 칸반(Kanban) 스타일 데이터 처리
df = pd.DataFrame(st.session_state.tasks)

if not df.empty:
    total_tasks = len(df)
    completed_tasks = len(df[df['상태'] == '완료'])
    progress_rate = int((completed_tasks / total_tasks) * 100) if total_tasks > 0 else 0
    
    # 상단 요약 지표 (Metrics)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("총 배정 과제 수", f"{total_tasks} 개")
    with col2:
        st.metric("완료된 과제 수", f"{completed_tasks} 개")
    with col3:
        st.metric("프로젝트 달성률", f"{progress_rate}%")
        
    st.progress(progress_rate / 100)
    st.write("")
    
    # 칸반 보드 형태로 시각화 (3열 구성)
    st.subheader("📌 실시간 프로젝트 칸반 보드")
    k_col1, k_col2, k_col3 = st.columns(3)
    
    with k_col1:
        st.markdown("### 🟥 진행 전")
        todo_list = df[df['상태'] == '진행 전']
        for idx, row in todo_list.iterrows():
            with st.expander(f"**{row['과제명']}**"):
                st.write(f"👤 담당자: {row['팀원']}")
                st.write(f"📅 마감일: {row['마감일']}")
                if st.button("진행하기", key=f"btn_todo_{idx}"):
                    st.session_state.tasks[idx]['상태'] = '진행 중'
                    st.rerun()
                    
    with k_col2:
        st.markdown("### 🟨 진행 중")
        doing_list = df[df['상태'] == '진행 중']
        for idx, row in doing_list.iterrows():
            with st.expander(f"**{row['과제명']}**"):
                st.write(f"👤 담당자: {row['팀원']}")
                st.write(f"📅 마감일: {row['마감일']}")
                if st.button("완료처리", key=f"btn_doing_{idx}"):
                    st.session_state.tasks[idx]['상태'] = '완료'
                    st.rerun()
                    
    with k_col3:
        st.markdown("### 🟩 완료")
        done_list = df[df['상태'] == '완료']
        for idx, row in done_list.iterrows():
            with st.expander(f"**{row['과제명']}**"):
                st.write(f"👤 담당자: {row['팀원']}")
                st.write(f"📅 마감일: {row['마감일']}")
                if st.button("되돌리기", key=f"btn_done_{idx}"):
                    st.session_state.tasks[idx]['상태'] = '진행 중'
                    st.rerun()

    st.write("---")
    
    # 데이터 테이블 뷰 제공
    st.subheader("📋 전체 일정 데이터 상세 보기")
    st.dataframe(df, use_container_width=True)
    
    # 과제 초기화 기능 (테스트용)
    if st.button("모든 과제 초기화"):
        st.session_state.tasks = []
        st.rerun()
else:
    st.info("현재 배정된 과제가 없습니다. 왼쪽 사이드바에서 첫 번째 과제를 배정해 보세요!")