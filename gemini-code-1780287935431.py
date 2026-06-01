import streamlit as st
import pandas as pd
import os
import pickle
from datetime import datetime, timedelta

st.set_page_config(page_title="스타트리 (Startree)", page_icon="🌳", layout="wide")

DB_FILE = "startree_data_v2.pkl"

def load_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "rb") as f:
            return pickle.load(f)
    return None

def save_data(data):
    with open(DB_FILE, "wb") as f:
        pickle.dump(data, f)

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
            "calendar_events": {}, 
            "notices": [],
            "chats": [],
            "stories": [],  # [새로운 기능] 인스타 감성 스토리 저장소
            "stocks": {}    # [새로운 기능] 기여도 주식 가격 데이터
        }

data = st.session_state.app_data

with st.sidebar:
    st.title("🌳 스타트리 설정")
    if st.button("⚠️ 앱 전체 초기화", help="모든 데이터를 지우고 처음부터 시작합니다."):
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)
        st.session_state.app_data = {
            "step": 1, "member_count": 1, "members": [], "leader_idx": 0,
            "team_name": "조", "subject": "", "start_date": datetime.today().date(),
            "end_date": datetime.today().date() + timedelta(days=7),
            "calendar_events": {}, "notices": [], "chats": [], "stories": [], "stocks": {}
        }
        st.rerun()

# 초기 설정 1단계부터 5단계
if data["step"] < 6:
    st.title("🚀 스타트리 초기 설정")
    
    if data["step"] == 1:
        st.subheader("1단계: 팀의 총 인원수를 입력해주세요.")
        count = st.number_input("인원 수 (명)", min_value=1, max_value=20, value=data["member_count"])
        if st.button("다음 단계로"):
            data["member_count"] = count
            if len(data["members"]) != count:
                data["members"] = [{"이름": "", "연락처": "", "역할": ""} for _ in range(count)]
            data["step"] = 2
            save_data(data)
            st.rerun()

    elif data["step"] == 2:
        st.subheader("2단계: 조원들의 정보를 입력하고 조장을 선택해주세요.")
        member_names = []
        for i in range(data["member_count"]):
            st.markdown(f"#### 👤 조원 {i+1}")
            col1, col2, col3 = st.columns(3)
            with col1:
                data["members"][i]["이름"] = st.text_input(f"이름", value=data["members"][i]["이름"], key=f"name_{i}")
            with col2:
                data["members"][i]["연락처"] = st.text_input(f"연락처", value=data["members"][i]["연락처"], key=f"phone_{i}")
            with col3:
                data["members"][i]["역할"] = st.text_input(f"역할", value=data["members"][i]["역할"], key=f"role_{i}")
            member_names.append(data["members"][i]["이름"] if data["members"][i]["이름"] else f"조원 {i+1}")
        
        st.markdown("---")
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

    elif data["step"] == 4:
        st.subheader("4단계: 어떤 조 활동을 할 것인지 주제를 적어주세요.")
        subj = st.text_input("프로젝트 주제/내용", value=data["subject"])
        
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

    elif data["step"] == 5:
        st.subheader("5단계: 조 활동의 마감 기한을 선택해주세요.")
        e_date = st.date_input("마감 날짜 선택", value=data["end_date"], min_value=data["start_date"])
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("이전 단계"):
                data["step"] = 4
                st.rerun()
        with col_btn2:
            if st.button("🎉 설정 완료 및 홈화면 이동"):
                data["end_date"] = e_date
                # 주식 데이터 초기화 (모두 공평하게 10,000원에서 시작)
                for m in data["members"]:
                    if m["이름"]:
                        data["stocks"][m["이름"]] = [10000]
                data["step"] = 6
                save_data(data)
                st.rerun()

# 메인 홈 화면 운영
else:
    m_names = [m["이름"] if m["이름"] else f"조원 {idx+1}" for idx, m in enumerate(data["members"])]
    leader_name = data["members"][data["leader_idx"]]["이름"]
    
    # 상단 대시보드 타이틀
    st.title(f"🌳 {data['team_name']} 워크스페이스")
    st.markdown(f"**🎯 주제:** {data['subject']} | **👑 조장:** {leader_name}")
    
    # [아이디어 2번 적용] 인스타 스타일 스토리 바 상단 배치
    st.write("---")
    st.markdown("### 📸 조원들의 실시간 스토리 인증")
    if data["stories"]:
        story_cols = st.columns(max(len(data["stories"]), 5))
        for s_idx, s in enumerate(data["stories"]):
            with story_cols[s_idx % 5]:
                st.markdown(f"🔴 **{s['user']}**")
                st.caption(f"⏱️ {s['time']}")
                st.text_area(label=f"스토리_{s_idx}", value=s["content"], height=70, disabled=True, label_visibility="collapsed")
    else:
        st.caption("아직 올라온 스토리가 없습니다. 아래 홈 탭에서 오늘 한 일을 사진 대신 글로 인증해 보세요!")
    st.write("---")

    # 메인 탭 분리
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📢 홈 및 스토리 업로드", "📊 팀플 기여도 주식 차트", "📅 달력 일정 관리", "👥 조원 정보 관리", "💬 DM 채팅방"])
    
    # 탭 1: 홈 및 공지, 스토리 작성
    with tab1:
        col_left, col_right = st.columns(2)
        with col_left:
            st.subheader("📸 새 스토리 올리기 (인스타 감성 업무 인증)")
            with st.form("story_form", clear_on_submit=True):
                s_user = st.selectbox("작성자 선택", m_names, key="story_u")
                s_text = st.text_input("지금 어떤 팀플 업무 중인가요? (예: 카페에서 카페인 수집하며 PPT 3페이지 장인 정신으로 제작 중)")
                submit_s = st.form_submit_button("스토리 게시")
                if submit_s and s_text.strip():
                    data["stories"].insert(0, {
                        "user": s_user,
                        "content": s_text,
                        "time": datetime.now().strftime("%H:%M")
                    })
                    save_data(data)
                    st.rerun()
                    
        with col_right:
            st.subheader("📌 팀 공지사항 게시판")
            with st.form("notice_form", clear_on_submit=True):
                notice_text = st.text_area("공지글 내용을 입력하세요.")
                uploaded_file = st.file_uploader("파일 첨부 (선택사항)")
                submit_notice = st.form_submit_button("공지 등록")
                if submit_notice and notice_text.strip():
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
        st.markdown("#### 📋 등록된 공지 목록")
        for n in data["notices"]:
            st.info(f"📅 {n['date']}\n\n{n['content']}\n\n📎 파일: {n['file']}")

    # [아이디어 1번 적용] 탭 2: 팀플 기여도 주식 차트
    with tab2:
        st.subheader("📈 실시간 팀플 기여도 주식 차트")
        st.caption("조장님이 달력에서 완료 승인을 해줄 때마다 주가가 상한가를 칩니다! 잠수 시 하한가 폭락 주의.")
        
        # 가상의 타임라인 차트 데이터 구성
        stock_df = pd.DataFrame(dict([ (k, pd.Series(v)) for k, v in data["stocks"].items() ]))
        st.line_chart(stock_df)
        
        # 현재 주가 순위 표시
        st.markdown("#### 💰 조원별 현재 기여도 주가 현황")
        rank_cols = st.columns(len(data["stocks"]))
        for r_idx, (name, prices) in enumerate(data["stocks"].items()):
            with rank_cols[r_idx]:
                current_price = prices[-1]
                prev_price = prices[-2] if len(prices) > 1 else 10000
                diff = current_price - prev_price
                st.metric(label=f"{name} 주가", value=f"{current_price:,} 원", delta=f"{diff:,} 원")

    # 탭 3: 달력 일정 관리 (주가 변동 로직 결합)
    with tab3:
        st.subheader("📅 맞춤형 대시보드 달력")
        
        start, end = data["start_date"], data["end_date"]
        date_list = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        date_strs = [str(d) for d in date_list]
        
        selected_date_str = st.selectbox("🗓️ 조회하거나 할 일을 입력할 날짜 선택", date_strs)
        
        # 각 날짜별로 담당자 지정을 위해 구조 업그레이드
        current_event = data["calendar_events"].get(selected_date_str, {"content": "등록된 일이 없습니다.", "status": "❌", "worker": m_names[0]})
        
        col_ev1, col_ev2 = st.columns(2)
        with col_ev1:
            event_input = st.text_input(f"[{selected_date_str}] 할 일 입력", value=current_event["content"])
        with col_ev2:
            worker_input = st.selectbox(f"[{selected_date_str}] 담당 조원 지정", m_names, index=m_names.index(current_event.get("worker", m_names[0])))
            
        if st.button("일정 및 담당자 저장"):
            data["calendar_events"][selected_date_str] = {
                "content": event_input,
                "status": current_event["status"],
                "worker": worker_input
            }
            save_data(data)
            st.success("달력 일정이 저장되었습니다.")
            st.rerun()
            
        st.write("---")
        st.markdown("### 📋 전체 날짜별 진행 및 조장 최종 결재 현황")
        
        for d_str in date_strs:
            ev = data["calendar_events"].get(d_str, {"content": "등록된 일이 없습니다.", "status": "❌", "worker": "없음"})
            c_d, c_w, c_c, c_s = st.columns([2, 2, 4, 2])
            
            with c_d:
                st.write(d_str)
            with c_w:
                st.write(f"👤 {ev['worker']}")
            with c_c:
                st.write(ev["content"])
            with c_s:
                is_done = (ev["status"] == "✔️")
                if st.button(f"결재: {ev['status']}", key=f"cal_btn_{d_str}"):
                    if ev["content"] != "등록된 일이 없습니다." and ev["worker"] in data["stocks"]:
                        # 상태 변경
                        new_status = "❌" if is_done else "✔️"
                        data["calendar_events"][d_str]["status"] = new_status
                        
                        # [주가 반영] 완료 승인 시 주가 +3,000원 / 취소 시 -3,000원 폭락
                        current_p = data["stocks"][ev["worker"]][-1]
                        if new_status == "✔️":
                            data["stocks"][ev["worker"]].append(current_p + 3000)
                        else:
                            data["stocks"][ev["worker"]].append(max(1000, current_p - 3000))
                            
                        save_data(data)
                        st.rerun()

    # 탭 4: 조원 정보 관리
    with tab3:
        pass # Streamlit 중복 선언 방지용으로 아래 tab4 사용
    with tab4:
        st.subheader("👥 팀원 명부 관리")
        edit_team_name = st.text_input("조 이름 변경", value=data["team_name"])
        edit_subject = st.text_input("주제 변경", value=data["subject"])
        if st.button("팀 정보 수정완료"):
            data["team_name"] = edit_team_name
            data["subject"] = edit_subject
            save_data(data)
            st.success("팀 기본 정보가 변경되었습니다.")
            st.rerun()
            
        st.write("---")
        for i in range(len(data["members"])):
            is_l = " (👑 조장)" if i == data["leader_idx"] else ""
            st.markdown(f"**조원 {i+1}{is_l}**")
            c1, c2, c3 = st.columns(3)
            with c1:
                data["members"][i]["이름"] = st.text_input(f"이름", value=data["members"][i]["이름"], key=f"ed_n_{i}")
            with c2:
                data["members"][i]["연락처"] = st.text_input(f"연락처", value=data["members"][i]["연락처"], key=f"ed_p_{i}")
            with c3:
                data["members"][i]["역할"] = st.text_input(f"역할", value=data["members"][i]["역할"], key=f"ed_r_{i}")
                
        if st.button("조원 정보 최종 저장"):
            save_data(data)
            st.success("정보가 업데이트되었습니다.")
            st.rerun()

    # [아이디어 3번 적용] 탭 5: DM 채팅방 및 상단 전화 기능 (마감 임박 긴급 경보 기능 포함)
    with tab5:
        # 마감 임박한 일정이 있는지 검사 (예: 오늘 날짜 일정이 미완료(❌) 상태인지 체크)
        today_str = str(datetime.today().date())
        today_event = data["calendar_events"].get(today_str, {"status": "❌", "content": "등록된 일이 없습니다."})
        
        is_emergency = today_event["content"] != "등록된 일이 없습니다." and today_event["status"] == "❌"
        
        # 만약 마감 안 지켜졌으면 빨간 경고창(사이렌 대피소 모드) 활성화
        if is_emergency:
            st.error(f"🚨 긴급 경보: 오늘 마감인 과제 [{today_event['content']}]가 아직 완료되지 않았습니다! 디엠방에 비상이 걸렸습니다.")
            
        chat_h1, chat_h2 = st.columns([8, 2])
        with chat_h1:
            st.markdown(f"### 📱 {data['team_name']} 단체 DM 대화방")
        with chat_h2:
            if st.button("📞 실시간 보이스콜 연결", help="인스타 스타일 상단 전화 버튼"):
                st.toast("🎵 조원들에게 실시간 그룹 통화를 연결하고 있습니다... (가상 기능)", icon="📞")
                
        st.write("---")
        
        # 채팅 로그 출력 (긴급 상황일 땐 배경 색상 체감을 위해 테두리 추가)
        chat_box = st.container(height=250)
        with chat_box:
            for c in data["chats"]:
                st.markdown(f"**[{c['sender']}]** *{c['time']}*")
                st.info(c["msg"])
                
        with st.form("chat_form", clear_on_submit=True):
            c_sender = st.selectbox("메시지 보낼 사람", m_names, key="chat_s")
            c_msg = st.text_input("메시지 입력 창...", placeholder="조원들과 대화를 나눠보세요.")
            submit_c = st.form_submit_button("전송")
            if submit_c and c_msg.strip():
                data["chats"].append({
                    "sender": c_sender,
                    "msg": c_msg,
                    "time": datetime.now().strftime("%H:%M")
                })
                save_data(data)
                st.rerun()
