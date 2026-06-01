import streamlit as st
import pandas as pd
import os
import pickle
from datetime import datetime, timedelta

# 페이지 기본 설정
st.set_page_config(page_title="스타트리 (Startree)", page_icon="🌳", layout="wide")

DB_FILE = "startree_data.pkl"

# 데이터 로드 및 저장 함수 (데이터 유지 기능)
def load_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "rb") as f:
            return pickle.load(f)
    return None

def save_data(data):
    with open(DB_FILE, "wb") as f:
        pickle.dump(data, f)

# 세션 상태 초기화
if "app_data" not in st.session_state:
    saved = load_data()
    if saved:
        st.session_state.app_data = saved
    else:
        st.session_state.app_data = {
            "step": 1,
            "member_count": 1,
            "members": [],
            "leader_idx": 0,
            "team_name": "조",
            "subject": "",
            "start_date": datetime.today().date(),
            "end_date": datetime.today().date() + timedelta(days=7),
            "calendar_events": {},  # {str(date): {"content": "", "status": "❌"}}
            "notices": [],
            "chats": []
        }

data = st.session_state.app_data

# [6단계] 앱 초기화 기능 (화면 구석이나 하단에 배치 가능하도록 함수화)
def reset_app():
    if st.sidebar.button("⚠️ 앱 전체 초기화", help="모든 데이터를 지우고 1단계부터 다시 시작합니다."):
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)
        st.session_state.app_data = {
            "step": 1, "member_count": 1, "members": [], "leader_idx": 0,
            "team_name": "조", "subject": "", "start_date": datetime.today().date(),
            "end_date": datetime.today().date() + timedelta(days=7),
            "calendar_events": {}, "notices": [], "chats": []
        }
        st.rerun()

# 사이드바에 초기화 버튼 배치
with st.sidebar:
    st.title("🌳 스타트리")
    reset_app()

# ==========================================
# ⚙️ 초기 설정 프로세스 (Step 1 ~ 5)
# ==========================================
if data["step"] < 6:
    st.title("🚀 스타트리 초기 설정")
    
    # 1단계: 인원수 입력
    if data["step"] == 1:
        st.subheader("1단계: 팀의 총 인원수를 입력해주세요.")
        count = st.number_input("인원 수 (명)", min_value=1, max_value=20, value=data["member_count"])
        if st.button("다음 단계로"):
            data["member_count"] = count
            # 인원수에 맞게 멤버 리스트 구조 미리 생성
            if len(data["members"]) != count:
                data["members"] = [{"이름": "", "연락처": "", "역할": ""} for _ in range(count)]
            data["step"] = 2
            save_data(data)
            st.rerun()

    # 2단계: 조원 정보 입력 및 조장 선택
    elif data["step"] == 2:
        st.subheader("2단계: 조원들의 정보를 입력하고 조장을 선택해주세요.")
        
        member_names = []
        for i in range(data["member_count"]):
            st.markdown(f"#### 👤 조원 {i+1}")
            col1, col2, col3 = st.columns(3)
            with col1:
                data["members"][i]["이름"] = st.text_input(f"이름", value=data["members"][i]["이름"], key=f"name_{i}")
            with col2:
                data["members"][i]["연락처"] = st.text_input(f"연락처", value=data["members"][i]["연락처"], key=f"phone_{i}", placeholder="010-XXXX-XXXX")
            with col3:
                data["members"][i]["역할"] = st.text_input(f"역할", value=data["members"][i]["역할"], key=f"role_{i}", placeholder="예: PPT 제작, 발표")
            member_names.append(data["members"][i]["이름"] if data["members"][i]["이름"] else f"조원 {i+1}")
        
        st.markdown("---")
        # 조장 선택 기능
        data["leader_idx"] = st.selectbox("👑 이 조의 조장은 누구인가요?", range(data["member_count"]), format_func=lambda x: member_names[x])
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("이전 단계"):
                data["step"] = 1
                st.rerun()
        with col_btn2:
            if st.button("다음 단계로"):
                data["step"] = 3
                save_data(data)
                st.rerun()

    # 3단계: 조 이름 입력 (Skip 가능)
    elif data["step"] == 3:
        st.subheader("3단계: 조 이름을 정해주세요.")
        t_name = st.text_input("조 이름 입력", placeholder="미입력 시 '조'로 설정됩니다.")
        
        col_btn1, col_btn2, col_btn3 = st.columns(3)
        with col_btn1:
            if st.button("이전 단계"):
                data["step"] = 2
                st.rerun()
        with col_btn2:
            if st.button("⏩ Skip (넘어가기)"):
                data["team_name"] = "조"
                data["step"] = 4
                save_data(data)
                st.rerun()
        with col_btn3:
            if st.button("다음 단계로"):
                data["team_name"] = t_name if t_name.strip() else "조"
                data["step"] = 4
                save_data(data)
                st.rerun()

    # 4단계: 주제 입력
    elif data["step"] == 4:
        st.subheader("4단계: 어떤 조 활동을 할 것인지 주제를 적어주세요.")
        subj = st.text_input("프로젝트 주제/내용", value=data["subject"], placeholder="예: 창업동아리 앱 프로토타입 개발")
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("이전 단계"):
                data["step"] = 3
                st.rerun()
        with col_btn2:
            if st.button("다음 단계로"):
                data["subject"] = subj
                data["step"] = 5
                save_data(data)
                st.rerun()

    # 5단계: 마감 기한 입력
    elif data["step"] == 5:
        st.subheader("5단계: 조 활동의 마감 기한을 선택해주세요.")
        st.info(f"시작일은 오늘({data['start_date']})로 자동 설정되며, 마감일까지의 달력이 생성됩니다.")
        e_date = st.date_input("마감 날짜 선택", value=data["end_date"], min_value=data["start_date"])
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("이전 단계"):
                data["step"] = 4
                st.rerun()
        with col_btn2:
            if st.button("🎉 설정 완료 및 홈화면 이동"):
                data["end_date"] = e_date
                data["step"] = 6  # 홈 화면 진입 코드
                save_data(data)
                st.rerun()

# ==========================================
# 🏠 6, 7단계: 메인 홈 화면 및 기능 운영
# ==========================================
else:
    # 대시보드 상단 헤더
    st.title(f"🌳 {data['team_name']} 실시간 워크스페이스")
    st.markdown(f"**🎯 프로젝트 주제:** {data['subject']}")
    
    # 상단 탭 구성 (홈/공지방, 달력 관리, 조원 정보 수정, DM 채팅방)
    tab1, tab2, tab3, tab4 = st.tabs(["📢 홈 & 공지사항", "📅 달력 일정 관리", "👥 조원 정보 관리", "💬 DM 채팅방"])
    
    # ----------------------------------------
    # 탭 1: 홈 & 공지사항 (글 작성 및 파일 업로드)
    # ----------------------------------------
    with tab1:
        st.subheader("📌 팀 공지사항 게시판")
        
        # 글 작성 및 파일 업로드
        with st.form("notice_form", clear_on_submit=True):
            notice_text = st.text_area("공지글 또는 전달사항을 적어주세요.")
            uploaded_file = st.file_uploader("파일 첨부 (선택사항)", type=["pdf", "png", "jpg", "zip", "hwp", "xlsx", "pptx"])
            submit_notice = st.form_submit_button("공지 올리기")
            
            if submit_notice:
                if notice_text.strip():
                    file_info = uploaded_file.name if uploaded_file else "첨부 파일 없음"
                    data["notices"].insert(0, {
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "content": notice_text,
                        "file": file_info
                    })
                    save_data(data)
                    st.success("공지가 등록되었습니다.")
                    st.rerun()
        
        st.write("---")
        # 공지 출력
        if data["notices"]:
            for n in data["notices"]:
                st.info(f"**📅 {n['date']}**\n\n{n['content']}\n\n📎 *파일: {n['file']}*")
        else:
            st.text("등록된 공지사항이 없습니다.")

    # ----------------------------------------
    # 탭 2: 달력 일정 관리 (처음 실행일 ~ 끝나는 날 달력 구현)
    # ----------------------------------------
    with tab2:
        st.subheader("📅 맞춤형 대시보드 달력")
        st.caption(f"프로젝트 기간: {data['start_date']} ~ {data['end_date']}")
        
        # 날짜 범위 생성
        start = data["start_date"]
        end = data["end_date"]
        delta = end - start
        
        date_list = [start + timedelta(days=i) for i in range(delta.days + 1)]
        date_strs = [str(d) for d in date_list]
        
        # 날짜 선택기
        selected_date_str = st.selectbox("🗓️ 조회하거나 할 일을 입력할 날짜를 선택하세요", date_strs)
        
        # 선택한 날짜의 할 일 입력 및 보기
        current_event = data["calendar_events"].get(selected_date_str, {"content": "", "status": "❌"})
        
        event_input = st.text_input(f"[{selected_date_str}] 이날 해야 할 일 입력/수정", value=current_event["content"])
        if st.button("일정 저장"):
            if selected_date_str not in data["calendar_events"]:
                data["calendar_events"][selected_date_str] = {"content": "", "status": "❌"}
            data["calendar_events"][selected_date_str]["content"] = event_input
            save_data(data)
            st.success("일정이 반영되었습니다.")
            st.rerun()
            
        st.write("---")
        st.markdown("### 📋 전체 날짜별 할 일 목록")
        
        # 조장 이름 가져오기
        leader_name = data["members"][data["leader_idx"]]["이름"] if data["members"] else "미정"
        st.write(f"👑 **조장 권한 ({leader_name}):** 조장님만 완료(✔️) 및 미완료(❌) 체크박스를 변경할 수 있습니다.")
        
        # 표 형태로 달력 일정 및 조장 확인란 구현
        for d_str in date_strs:
            ev = data["calendar_events"].get(d_str, {"content": "등록된 할 일이 없습니다.", "status": "❌"})
            col_d, col_c, col_s = st.columns([2, 5, 2])
            
            with col_d:
                st.write(f"**{d_str}**")
            with col_c:
                st.write(ev["content"])
            with col_s:
                # 조장 체크 기능 (조장 전용 UI 시뮬레이션)
                is_completed = (ev["status"] == "✔️")
                # 토글 버튼처럼 구현
                btn_label = f"상태: {ev['status']} (변경)"
                if st.button(btn_label, key=f"status_btn_{d_str}"):
                    if ev["content"] != "등록된 할 일이 없습니다.":
                        data["calendar_events"][d_str]["status"] = "❌" if is_completed else "✔️"
                        save_data(data)
                        st.rerun()

    # ----------------------------------------
    # 탭 3: 조원 정보 관리 (수정 및 추가 가능)
    # ----------------------------------------
    with tab3:
        st.subheader("👥 팀원 명부 및 수정")
        
        # 조 이름 및 주제 실시간 수정
        st.markdown("#### ✏️ 팀 기본정보 수정")
        edit_team_name = st.text_input("조 이름 수정", value=data["team_name"])
        edit_subject = st.text_input("주제 수정", value=data["subject"])
        if st.button("기본정보 업데이트"):
            data["team_name"] = edit_team_name
            data["subject"] = edit_subject
            save_data(data)
            st.success("기본정보가 수정되었습니다.")
            st.rerun()
            
        st.write("---")
        st.markdown("#### ✏️ 조원 세부정보 수정")
        for i in range(len(data["members"])):
            is_leader = " (👑 조장)" if i == data["leader_idx"] else ""
            st.markdown(f"**조원 {i+1}{is_leader}**")
            col1, col2, col3 = st.columns(3)
            with col1:
                data["members"][i]["이름"] = st.text_input(f"이름", value=data["members"][i]["이름"], key=f"edit_name_{i}")
            with col2:
                data["members"][i]["연락처"] = st.text_input(f"연락처", value=data["members"][i]["연락처"], key=f"edit_phone_{i}")
            with col3:
                data["members"][i]["역할"] = st.text_input(f"역할", value=data["members"][i]["역할"], key=f"edit_role_{i}")
        
        # 조장 재선택
        m_names = [m["이름"] if m["이름"] else f"조원 {idx+1}" for idx, m in enumerate(data["members"])]
        data["leader_idx"] = st.selectbox("조장 변경", range(len(data["members"])), index=data["leader_idx"], format_func=lambda x: m_names[x])
        
        if st.button("조원 정보 저장"):
            save_data(data)
            st.success("조원 정보가 안전하게 수정되었습니다.")
            st.rerun()
            
        st.write("---")
        # 신규 조원 중간 추가 기능
        st.markdown("#### ➕ 새로운 조원 추가")
        add_col1, add_col2, add_col3 = st.columns(3)
        with add_col1:
            add_name = st.text_input("새 조원 이름", key="add_n")
        with add_col2:
            add_phone = st.text_input("새 조원 연락처", key="add_p")
        with add_col3:
            add_role = st.text_input("새 조원 역할", key="add_r")
            
        if st.button("이 팀원에 추가하기"):
            if add_name.strip():
                data["members"].append({"이름": add_name, "연락처": add_phone, "역할": add_role})
                data["member_count"] = len(data["members"])
                save_data(data)
                st.success(f"{add_name} 조원이 추가되었습니다.")
                st.rerun()

    # ----------------------------------------
    # 탭 4: DM 채팅방 (인스타 DM 스타일 UI + 상단 전화 버튼)
    # ----------------------------------------
    with tab4:
        st.subheader("💬 인스타 DM 스타일 팀 대화방")
        
        # 상단바 영역 (채팅방 이름 + 인스타 스타일 전화기 아이콘)
        chat_header_col1, chat_header_col2 = st.columns([8, 2])
        with chat_header_col1:
            st.markdown(f"### 📱 {data['team_name']} 단체 DM")
        with chat_header_col2:
            # 상단 전화 버튼 배치 (클릭 시 알림 전송 가상 모달)
            if st.button("📞 전화 걸기", help="조원들에게 그룹 보이스콜 전화를 거는 기능 버튼입니다."):
                st.toast("📞 실시간 전화 연결을 시도 중입니다... (가상 기능)", icon="🎵")
        
        st.write("---")
        
        # 채팅 내역 보여주기 박스 형태
        chat_container = st.container(height=300)
        with chat_container:
            if data["chats"]:
                for c in data["chats"]:
                    # 말풍선 스타일 가상 구현
                    st.markdown(f"**[{c['sender']}]** *({c['time']})*")
                    st.info(c["msg"])
            else:
                st.caption("아직 주고받은 메시지가 없습니다. 첫 인사를 건네보세요!")
                
        # 메시지 전송 폼
        with st.form("chat_send_form", clear_on_submit=True):
            chat_sender = st.selectbox("보내는 사람 선택", m_names)
            chat_msg = st.text_input("메시지 보내기...", placeholder="메시지를 입력하세요.")
            send_btn = st.form_submit_button("전송")
            
            if send_btn and chat_msg.strip():
                data["chats"].append({
                    "sender": chat_sender,
                    "msg": chat_msg,
                    "time": datetime.now().strftime("%H:%M")
                })
                save_data(data)
                st.rerun()
