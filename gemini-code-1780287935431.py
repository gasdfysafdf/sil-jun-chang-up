import streamlit as st
import pandas as pd
import os
import pickle
from datetime import datetime, timedelta

st.set_page_config(page_title="스타트리 (Startree)", page_icon="🌳", layout="wide")

DB_FILE = "startree_master_db.pkl"

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
            "users_db": {},               
            "current_user": None,          
            "step": "auth_login",          
            "member_count": 1,
            "members": [],                 
            "leader_idx": 0,
            "team_name": "",
            "subject": "",
            "start_date": datetime.today().date(),
            "end_date": datetime.today().date() + timedelta(days=7),
            # 하루 여러 일정 지원을 위해 구조 변경: "날짜": [{"id": 0, "content": "발표", "worker": "카이", "status": "⏳"}]
            "calendar_events": {}, 
            "notices": [],
            "chats": [],
            "stories": [],  
            "stocks": {},
            "stock_logs": {} 
        }

data = st.session_state.app_data
m_names = [m["이름"] for m in data["members"] if m["이름"]]

# 사이드바 제어창
with st.sidebar:
    st.title("🌳 스타트리 검증 모드")
    if data["current_user"]:
        st.success(f"🔐 로그인 계정: {data['current_user']}")
        if st.button("로그아웃"):
            data["current_user"] = None
            data["step"] = "auth_login"
            save_data(data)
            st.rerun()
    else:
        st.warning("로그인이 필요한 상태입니다.")
        
    st.write("---")
    if st.button("⚠️ 시스템 전체 초기화", help="모든 가상 데이터를 완전히 지우고 처음부터 다시 시연합니다."):
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)
        st.session_state.app_data = {
            "users_db": {},
            "current_user": None,
            "step": "auth_login",
            "member_count": 1,
            "members": [],
            "leader_idx": 0,
            "team_name": "",
            "subject": "",
            "start_date": datetime.today().date(),
            "end_date": datetime.today().date() + timedelta(days=7),
            "calendar_events": {}, "notices": [], "chats": [], "stories": [], "stocks": {}, "stock_logs": {}
        }
        st.rerun()

# 1. 로그인 화면
if data["step"] == "auth_login":
    st.title("🔐 스타트리 조장 로그인")
    st.caption("대학생 팀플 라이트 ERP 스타트리 MVP 시연 버전입니다.")
    
    login_id = st.text_input("아이디", key="login_id_input")
    login_pw = st.text_input("비밀번호", type="password", key="login_pw_input")
    
    col_l1, col_l2 = st.columns(2)
    with col_l1:
        if st.button("로그인하기"):
            if login_id in data["users_db"] and data["users_db"][login_id] == login_pw:
                data["current_user"] = login_id
                
                if data["team_name"].strip() and data["members"]:
                    data["step"] = "main_home"
                else:
                    data["step"] = "setup_1"
                    
                save_data(data)
                st.success("로그인 성공!")
                st.rerun()
            else:
                st.error("아이디 또는 비밀번호가 틀렸습니다.")
    with col_l2:
        if st.button("신규 회원가입하러 가기"):
            data["step"] = "auth_register"
            save_data(data)
            st.rerun()

# 2. 회원가입 화면
elif data["step"] == "auth_register":
    st.title("📝 스타트리 조장 회원가입")
    st.caption("새로운 팀의 조장 계정을 생성합니다.")
    
    reg_id = st.text_input("생성할 아이디", key="reg_id_input")
    reg_pw = st.text_input("생성할 비밀번호", type="password", key="reg_pw_input")
    
    if "id_checked" not in st.session_state:
        st.session_state.id_checked = False
        
    if st.button("아이디 중복 확인"):
        if not reg_id.strip():
            st.warning("아이디를 입력해 주세요.")
        elif reg_id in data["users_db"]:
            st.error("이미 존재하는 아이디입니다. 다른 아이디를 입력해 주세요.")
            st.session_state.id_checked = False
        else:
            st.success("사용 가능한 아이디입니다!")
            st.session_state.id_checked = True
            
    if st.button("회원가입 완료하기"):
        if not st.session_state.id_checked:
            st.error("회원가입을 하려면 먼저 아이디 중복 확인을 완료해야 합니다.")
        elif not reg_pw.strip():
            st.error("비밀번호를 입력해 주세요.")
        else:
            data["users_db"][reg_id] = reg_pw
            data["step"] = "auth_login"
            save_data(data)
            st.session_state.id_checked = False
            st.success("회원가입 완료! 로그인 화면으로 돌아갑니다.")
            st.rerun()

# 3. 조원 수 설정 단계
elif data["step"] == "setup_1":
    st.title("🚀 스타트리 초기 설정")
    st.subheader("1단계: 팀의 총 인원수를 입력해주세요.")
    count = st.number_input("인원 수 (명)", min_value=1, max_value=20, value=data["member_count"])
    if st.button("다음 단계로"):
        data["member_count"] = count
        data["members"] = [{"이름": "", "연락처": "", "역할": ""} for _ in range(count)]
        data["step"] = "setup_2"
        save_data(data)
        st.rerun()

# 4. 조원 상세 정보 직접 기입
elif data["step"] == "setup_2":
    st.title("🚀 스타트리 초기 설정")
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
    data["leader_idx"] = st.selectbox("👑 이 팀의 조장(팀장)은 누구인가요?", range(data["member_count"]), format_func=lambda x: member_names[x])
    
    if st.button("다음 단계로"):
        has_empty_name = any(not m["이름"].strip() for m in data["members"])
        if has_empty_name:
            st.error("모든 조원의 이름을 올바르게 입력해 주세요.")
        else:
            data["step"] = "setup_3"
            save_data(data)
            st.rerun()

# 5. 팀 이름 입력 단계
elif data["step"] == "setup_3":
    st.title("🚀 스타트리 초기 설정")
    st.subheader("3단계: 프로젝트 팀 명을 정해주세요.")
    t_name = st.text_input("팀 이름 입력", value=data["team_name"])
    if st.button("다음 단계로"):
        data["team_name"] = t_name if t_name.strip() else "조"
        data["step"] = "setup_4"
        save_data(data)
        st.rerun()

# 6. 프로젝트 주제 입력 단계
elif data["step"] == "setup_4":
    st.title("🚀 스타트리 초기 설정")
    st.subheader("4단계: 프로젝트 팀 활동 주제를 입력해주세요.")
    subj = st.text_input("프로젝트 주제/내용", value=data["subject"])
    if st.button("다음 단계로"):
        data["subject"] = subj
        data["step"] = "setup_5"
        save_data(data)
        st.rerun()

# 7. 마감 기한 설정 단계
elif data["step"] == "setup_5":
    st.title("🚀 스타트리 초기 설정")
    st.subheader("5단계: 이번 팀 프로젝트의 마감 기한을 선택해주세요.")
    e_date = st.date_input("마감 날짜 선택", value=data["end_date"])
    if st.button("다음 단계로"):
        data["end_date"] = e_date
        data["step"] = "setup_link"
        save_data(data)
        st.rerun()

# 8. 조원 초대용 가상 링크 생성 창
elif data["step"] == "setup_link":
    st.title("🔗 조원 초대 링크 생성 완료")
    st.subheader("다른 조원들에게 아래의 워크스페이스 참여 링크를 공유하세요!")
    
    v_link = f"https://startree.app/workspace/join?team={data['team_name']}&id=master_shared"
    st.info(v_link)
    st.caption("초대받은 조원들은 복잡한 가입 절차 없이, 이 링크 하나로 즉시 홈화면에 바로 접속할 수 있습니다.")
    
    if st.button("🎉 링크 복사 확인 및 홈화면 진입"):
        for m in data["members"]:
            if m["이름"] and m["이름"] not in data["stocks"]:
                data["stocks"][m["이름"]] = [10000]
                data["stock_logs"][m["이름"]] = []
        data["step"] = "main_home"
        save_data(data)
        st.rerun()

# 9. 메인 워크스페이스 홈화면
else:
    leader_name = data["members"][data["leader_idx"]]["이름"] if data["members"] else "미정"
    
    st.title(f"🌳 {data['team_name']} 워크스페이스")
    st.markdown(f"**🎯 주제:** {data['subject']} | **👑 조장:** {leader_name} | **👤 로그인 상태:** {data['current_user']} (마스터 권한)")
    st.write("---")

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📢 팀 홈 및 공지사항", 
        "✨ 스토리 피드 광장", 
        "📊 기여도 주식 차트", 
        "📅 달력 일정 관리", 
        "👥 조원 정보 수정창", 
        "💬 다중 대상 DM방"
    ])
    
    # 탭 1: 공지사항 게시판
    with tab1:
        st.subheader("📌 팀 공지사항 관리")
        with st.form("notice_form", clear_on_submit=True):
            notice_text = st.text_area("공지글 내용을 입력하세요.")
            uploaded_file = st.file_uploader("공지 첨부파일 (선택사항)")
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
        for n in data["notices"]:
            st.info(f"📅 {n['date']}\n\n{n['content']}\n\n📎 파일: {n['file']}")

    # 탭 2: 피드 광장
    with tab2:
        st.subheader("📸 나의 팀플 스토리 업로드")
        col_up, col_view = st.columns([2, 3])
        
        with col_up:
            st.markdown("#### 📤 오늘의 프로젝트 진행 상황 피드 게시")
            with st.form("story_upload_form", clear_on_submit=True):
                st_text = st.text_area("조장님, 오늘 완료한 업무 내용을 한 줄 요약해 보세요.")
                st_media = st.file_uploader("사진, 영상, 음악 미디어 파일 첨부", type=["png", "jpg", "jpeg", "mp4", "mp3", "wav"])
                
                submit_story = st.form_submit_button("스토리 피드 게시")
                if submit_story and st_text.strip():
                    media_type = None
                    media_data = None
                    media_name = None
                    
                    if st_media is not None:
                        media_name = st_media.name
                        media_data = st_media.read()
                        if st_media.name.endswith((".png", ".jpg", ".jpeg")):
                            media_type = "image"
                        elif st_media.name.endswith(".mp4"):
                            media_type = "video"
                        elif st_media.name.endswith((".mp3", ".wav")):
                            media_type = "audio"
                            
                    data["stories"].insert(0, {
                        "user": f"{leader_name}(조장)", 
                        "content": st_text,
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "media_type": media_type,
                        "media_data": media_data,
                        "media_name": media_name,
                        "likes": 0,
                        "comments": []
                    })
                    save_data(data)
                    st.success("스토리가 업로드되었습니다!")
                    st.rerun()
                    
        with col_view:
            st.markdown("#### 📱 실시간 스토리 피드 목록")
            if not data["stories"]:
                st.caption("아직 게시된 스토리 피드가 없습니다.")
            else:
                for idx, s in enumerate(data["stories"]):
                    with st.container(border=True):
                        st.markdown(f"🔴 **{s['user']}** | *{s['time']}*")
                        st.write(s["content"])
                        
                        if s.get("media_type") == "image":
                            st.image(s["media_data"], use_container_width=True)
                        elif s.get("media_type") == "video":
                            st.video(s["media_data"])
                        elif s.get("media_type") == "audio":
                            st.audio(s["media_data"])
                            
                        if st.button(f"❤️ 좋아요 {s.get('likes', 0)}개", key=f"like_b_{idx}"):
                            s["likes"] = s.get("likes", 0) + 1
                            save_data(data)
                            st.rerun()
                                
                        st.markdown("---")
                        for cm in s.get("comments", []):
                            st.markdown(f"**{cm['writer']}**: {cm['text']}")
                            
                        with st.form(f"comment_f_{idx}", clear_on_submit=True):
                            c_text = st.text_input("댓글 남기기", key=f"cm_t_{idx}")
                            if st.form_submit_button("댓글 등록") and c_text.strip():
                                s["comments"].append({
                                    "writer": f"{leader_name}(조장)",
                                    "text": c_text
                                })
                                save_data(data)
                                st.rerun()

    # 📊 탭 3: 기여도 주식 차트 대시보드
    with tab3:
        st.subheader("📊 실시간 팀플 기여도 지표 (주식형 대시보드)")
        st.caption("달력 일정 관리에서 조장이 업무 수행 여부를 직접 확인 및 결재하면 상벌 포인트가 주가 그래프에 실시간 반영됩니다.")
        
        if not m_names:
            st.info("조원 정보가 설정되면 차트가 활성화됩니다.")
        else:
            st.markdown("### 🚨 실시간 조원별 거래 현황 및 변동 지표")
            
            grid_cols = st.columns(len(m_names))
            for index, name in enumerate(m_names):
                with grid_cols[index]:
                    if name not in data["stocks"]:
                        data["stocks"][name] = [10000]
                    if name not in data["stock_logs"]:
                        data["stock_logs"][name] = []
                        
                    current_val = data["stocks"][name][-1]
                    logs = data["stock_logs"][name]
                    
                    with st.container(border=True):
                        role_tag = "👑 조장" if name == leader_name else "👤 조원"
                        st.markdown(f"**{name}** `{role_tag}`")
                        st.markdown(f"현재 기여도: **{current_val:,} P**")
                        
                        if logs:
                            last_log = logs[-1]
                            if last_log["type"] == "plus":
                                st.markdown(f"<span style='color:#2ec4b6; font-weight:bold;'>▲ +{last_log['val']:,} P</span><br><small style='color:gray;'>{last_log['reason']}</small>", unsafe_allow_html=True)
                            else:
                                st.markdown(f"<span style='color:#e71d36; font-weight:bold;'>▼ -{last_log['val']:,} P</span><br><small style='color:gray;'>{last_log['reason']}</small>", unsafe_allow_html=True)
                        else:
                            st.caption("🔄 변동 내역 아직 없음")
            
            st.write("---")
            
            st.markdown("### 📈 조원별 기여도 개별 주식 차트 조회")
            selected_stock_user = st.selectbox("📊 상세 변동 그래프를 확인하려는 조원을 클릭하세요", m_names)
            
            if selected_stock_user:
                user_history = data["stocks"][selected_stock_user]
                
                chart_df = pd.DataFrame({
                    "거래 차수": [f"{i}차 변동" for i in range(len(user_history))],
                    "기여도 가치 (P)": user_history
                })
                chart_df = chart_df.set_index("거래 차수")
                st.line_chart(chart_df)
                
                st.markdown(f"📋 **{selected_stock_user}** 조원의 전체 변동 이력 로그")
                if not data["stock_logs"][selected_stock_user]:
                    st.caption("표시할 상세 기록이 없습니다.")
                else:
                    for l_idx, log in enumerate(reversed(data["stock_logs"][selected_stock_user])):
                        sign = "🟢 승인 (+)" if log["type"] == "plus" else "🔴 미이행 (-)"
                        st.write(f"{l_idx+1}. [{sign}] {log['reason']} ➔ **{log['val']:,} P 변동**")

    # 📅 탭 4: 달력 일정 관리 (하루 다중 등록 지원 및 깔끔한 기호 버튼 개편)
    with tab4:
        st.subheader("📅 맞춤형 스케줄러 관리")
        start, end = data["start_date"], data["end_date"]
        date_list = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        date_strs = [str(d) for d in date_list]
        
        col_reg1, col_reg2, col_reg3 = st.columns([2, 2, 4])
        with col_reg1:
            selected_date_str = st.selectbox("날짜 선택", date_strs, key="sel_date")
        with col_reg2:
            worker_input = st.selectbox("업무 담당자", m_names, key="sel_worker")
        with col_reg3:
            event_input = st.text_input("할 일 명칭 입력", placeholder="예: 대본 작성, ppt 제작 등", key="sel_content")
            
        if st.button("➕ 새로운 업무 등록/추가"):
            if not event_input.strip():
                st.error("할 일 명칭을 입력해 주세요.")
            else:
                if selected_date_str not in data["calendar_events"]:
                    data["calendar_events"][selected_date_str] = []
                
                # 리스트 형태로 어펜드하여 중복 덮어쓰기 완전 방지
                data["calendar_events"][selected_date_str].append({
                    "id": len(data["calendar_events"][selected_date_str]),
                    "content": event_input.strip(),
                    "status": "⏳ 대기",
                    "worker": worker_input
                })
                save_data(data)
                st.success(f"🎉 {selected_date_str}에 {worker_input}님의 [{event_input}] 업무가 추가되었습니다!")
                st.rerun()
            
        st.write("---")
        st.markdown("#### 📋 조장 전용 최종 업무 승인 결재 리스트")
        
        # 전체 날짜를 순회하며 등록된 모든 다중 일정을 출력
        for d_str in date_strs:
            day_events = data["calendar_events"].get(d_str, [])
            
            if not day_events:
                # 등록된 업무가 아예 없는 날짜의 디폴트 가이드 라인
                c_d, c_w, c_c, c_s, c_b1, c_b2 = st.columns([1.5, 1.5, 4, 1.5, 0.7, 0.7])
                with c_d: st.write(d_str)
                with c_w: st.write("👤 없음")
                with c_c: st.write("등록된 일이 없습니다.")
                with c_s: st.markdown("<span style='color:gray;'>-</span>", unsafe_allow_html=True)
                with c_b1: st.write("")
                with c_b2: st.write("")
            else:
                # 해당 날짜에 등록된 여러 개의 일정을 하나씩 하단에 나란히 풀어서 렌더링
                for ev in day_events:
                    # 완벽한 한 줄 유지를 위해 컬럼 너비 재조정 (글자 없는 아이콘 버튼 배치)
                    c_d, c_w, c_c, c_s, c_b1, c_b2 = st.columns([1.5, 1.5, 4, 1.5, 0.7, 0.7])
                    
                    with c_d: st.write(d_str)
                    with c_w: st.write(f"👤 {ev['worker']}")
                    with c_c: st.write(ev["content"])
                    with c_s: 
                        if ev["status"] == "✔️ 승인":
                            st.markdown("<span style='color:#2ec4b6; font-weight:bold;'>✔️ 승인 완료</span>", unsafe_allow_html=True)
                        elif ev["status"] == "❌ 반려":
                            st.markdown("<span style='color:#e71d36; font-weight:bold;'>❌ 미이행 반려</span>", unsafe_allow_html=True)
                        else:
                            st.markdown("<span style='color:orange;'>⏳ 결재 대기</span>", unsafe_allow_html=True)
                            
                    with c_b1:
                        # 글자를 제거하고 오직 체크 아이콘만 있는 가로 정렬 버튼 구현
                        if ev["status"] != "✔️ 승인":
                            if st.button("✔️", key=f"v_btn_{d_str}_{ev['id']}", help="과제 완수 승인"):
                                ev["status"] = "✔️ 승인"
                                target_worker = ev["worker"]
                                
                                if target_worker in data["stocks"]:
                                    current_p = data["stocks"][target_worker][-1]
                                    data["stocks"][target_worker].append(current_p + 3000)
                                    data["stock_logs"][target_worker].append({
                                        "type": "plus",
                                        "val": 3000,
                                        "reason": f"{d_str} [{ev['content']}] 승인완료"
                                    })
                                save_data(data)
                                st.rerun()
                        else:
                            st.write("")
                            
                    with c_b2:
                        # 글자를 제거하고 오직 X 아이콘만 있는 가로 정렬 버튼 구현
                        if ev["status"] != "❌ 반려":
                            if st.button("❌", key=f"x_btn_{d_str}_{ev['id']}", help="과제 미이행 반려"):
                                ev["status"] = "❌ 반려"
                                target_worker = ev["worker"]
                                
                                if target_worker in data["stocks"]:
                                    current_p = data["stocks"][target_worker][-1]
                                    next_p = max(1000, current_p - 3000)
                                    data["stocks"][target_worker].append(next_p)
                                    data["stock_logs"][target_worker].append({
                                        "type": "minus",
                                        "val": 3000,
                                        "reason": f"{d_str} [{ev['content']}] 미이행 패널티"
                                    })
                                save_data(data)
                                st.rerun()
                        else:
                            st.write("")

    # 👥 탭 5: 조원 정보 수정창
    with tab5:
        st.subheader("👥 조원 명부 관리 (수정 전용 공간)")
        
        edit_team_name = st.text_input("조 이름 변경", value=data["team_name"])
        edit_subject = st.text_input("프로젝트 주제 변경", value=data["subject"])
        if st.button("기본 팀 정보 수정확인"):
            data["team_name"] = edit_team_name
            data["subject"] = edit_subject
            save_data(data)
            st.success("팀 메인 정보가 성공적으로 변경되었습니다.")
            st.rerun()
            
        st.write("---")
        for i in range(len(data["members"])):
            is_leader_mark = " (👑 조장)" if i == data["leader_idx"] else ""
            st.markdown(f"#### 👤 조원 {i+1}{is_leader_mark} 정보 관리")
            data["members"][i]["이름"] = st.text_input(f"성명", value=data["members"][i]["이름"], key=f"fixed_n_{i}")
            data["members"][i]["연락처"] = st.text_input(f"연락처", value=data["members"][i]["연락처"], key=f"fixed_p_{i}")
            data["members"][i]["역할"] = st.text_input(f"담당 역할", value=data["members"][i]["역할"], key=f"fixed_r_{i}")
            st.write("---")
            
        if st.button("👥 조원 명단 데이터베이스 동기화 저장"):
            for m in data["members"]:
                if m["이름"] and m["이름"] not in data["stocks"]:
                    data["stocks"][m["이름"]] = [10000]
                    data["stock_logs"][m["이름"]] = []
            save_data(data)
            st.success("수정된 명단이 마스터 데이터베이스에 연동되었습니다.")
            st.rerun()

    # 💬 탭 6: 다중 대상 DM방 탭
    with tab6:
        st.subheader("💬 다중 대상 동시 전송 DM 채널")
        
        chat_box = st.container(height=300)
        with chat_box:
            for c in data["chats"]:
                st.markdown(f"**[{c['sender']} ➔ 수신자: {c['receivers']}]** *{c['time']}*")
                st.info(c["msg"])
                
        with st.form("multi_dm_form", clear_on_submit=True):
            selected_receivers = st.multiselect("📥 메시지를 보낼 수신자 조원들을 선택하세요 (다중 체크)", m_names, default=m_names)
            dm_msg = st.text_input("DM 메시지 내용 작성", placeholder="선택한 여러 명의 조원에게 메시지를 동시에 발송합니다.")
            
            if st.form_submit_button("🚀 다중 대상 DM 발송") and dm_msg.strip():
                if not selected_receivers:
                    st.error("메시지를 전송할 대상을 최소 1명 이상 선택하셔야 합니다.")
                else:
                    receiver_str = ", ".join(selected_receivers)
                    data["chats"].append({
                        "sender": f"{leader_name}(조장)",
                        "receivers": receiver_str,
                        "msg": dm_msg,
                        "time": datetime.now().strftime("%H:%M")
                    })
                    save_data(data)
                    st.rerun()
