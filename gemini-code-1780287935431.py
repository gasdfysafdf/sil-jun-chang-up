import streamlit as st
import pandas as pd
import os
import pickle
import uuid
import time
from datetime import datetime, timedelta

st.set_page_config(page_title="스타트리 (Startree)", page_icon="🌳", layout="wide")

DB_FILE = "startree_multi_team_db.pkl"

# --- [멀티팀 데이터베이스 엔진] ---
def load_all_data():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "rb") as f:
            return pickle.load(f)
    return {
        "users_master": {},  # { "leader_id": {"pw": "...", "team_id": "uuid_str"} }
        "teams_master": {}   # { "team_id_str": { 팀 세부 데이터 세트 } }
    }

def save_all_data(master_db):
    with open(DB_FILE, "wb") as f:
        pickle.dump(master_db, f)

master_db = load_all_data()

# --- [개별 브라우저 세션 상태 초기화] ---
if "current_team_id" not in st.session_state:
    st.session_state.current_team_id = None
if "current_user" not in st.session_state:
    st.session_state.current_user = None
if "user_role" not in st.session_state:
    st.session_state.user_role = "leader" 
if "step" not in st.session_state:
    st.session_state.step = "auth_login"

# 🔗 조원 초대 링크 파라미터 트래킹
query_params = st.query_params
if "invite" in query_params and "team_id" in query_params:
    target_team = query_params["team_id"]
    if target_team in master_db["teams_master"] and st.session_state.step not in ["main_home", "member_auth"]:
        st.session_state.current_team_id = target_team
        st.session_state.user_role = "member"
        st.session_state.step = "member_auth"

# 현재 접속 세션 바인딩
team_data = None
m_names = []
leader_name = "미정"
if st.session_state.current_team_id and st.session_state.current_team_id in master_db["teams_master"]:
    team_data = master_db["teams_master"][st.session_state.current_team_id]
    m_names = [m["이름"] for m in team_data["members"] if m["이름"]]
    leader_name = team_data["members"][team_data["leader_idx"]]["이름"] if team_data["members"] else "미정"

# --- [사이드바 제어창 및 수동 새로고침] ---
with st.sidebar:
    st.title("🌳 스타트리 서비스 센터")
    
    # 🔄 수동 새로고침 버튼
    if st.button("🔄 시스템 실시간 동기화 (새로고침)", use_container_width=True):
        st.rerun()
        
    st.write("---")
    if st.session_state.current_user:
        role_label = "👑 조장" if st.session_state.user_role == "leader" else "👤 조원"
        t_name_display = team_data['team_name'] if team_data else "설정중"
        st.success(f"소속: {t_name_display}\n\n계정: {st.session_state.current_user} [{role_label}]")
        
        if st.button("To. 로그아웃 (접속 종료)", use_container_width=True):
            st.session_state.current_user = None
            st.session_state.current_team_id = None
            st.session_state.user_role = "leader"
            st.session_state.step = "auth_login"
            st.query_params.clear()
            st.rerun()
    else:
        st.warning("상용화 멀티팀 인증 모드 구동 중")
        
    st.write("---")
    st.caption("🚨 마스터 포맷 시 파일 데이터 전체가 증발하므로 주의하세요.")
    if st.button("⚠️ [관리자] 마스터 DB 전체 포맷"):
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)
        st.session_state.clear()
        st.query_params.clear()
        st.rerun()

# ==========================================
# [분기 1] 조원 전용 초대 링크 접속 처리 화면
# ==========================================
if st.session_state.step == "member_auth" and team_data:
    st.title("🔗 스타트리 조원 초대 가입 패스")
    st.subheader(f"🌳 '{team_data['team_name']}' 팀 워크스페이스")
    st.markdown(f"**🎯 프로젝트 주제:** {team_data['subject']} | **👑 담당 조장:** {leader_name}")
    st.caption("조장 로그인 계정이 없어도, 지정된 명단 선택을 통해 즉시 접속이 가능합니다.")
    
    if not m_names:
        st.error("❌ 조장님이 아직 조원 명부를 작성하지 않았습니다. 조장에게 초기 팀 설정을 완료해달라고 요청하세요.")
    else:
        # 🔒 조원 목록에서 조장(Leader) 이름은 완벽하게 필터링하여 제외
        only_members_names = [name for name in m_names if name != leader_name]
        
        if not only_members_names:
            st.warning("현재 조장 외에 등록된 조원 성명이 존재하지 않습니다. 조장 수정창에서 명단을 업데이트 하세요.")
            st.stop()
            
        st.info("💡 명단에서 본인의 이름을 선택하여 입장해 주세요. 조장 계정은 이 창으로 진입할 수 없습니다.")
        selected_member = st.selectbox("👤 당신은 누구인가요? 본인의 이름을 선택하세요.", only_members_names)
        
        if st.button("🎉 조원 권한으로 워크스페이스 입장"):
            st.session_state.current_user = selected_member
            st.session_state.user_role = "member"
            st.session_state.step = "main_home"
            st.success(f"확인되었습니다, {selected_member} 조원님! 대시보드로 이동합니다.")
            st.rerun()

# ==========================================
# [분기 2] 조장 로그인 화면
# ==========================================
elif st.session_state.step == "auth_login":
    st.title("🔐 스타트리 조장 로그인 포털")
    st.caption("동시에 여러 팀이 가입하고 고유 링크를 뽑아 사용하는 런칭 패키지입니다.")
    
    login_id = st.text_input("조장 아이디", key="login_id_input").strip()
    login_pw = st.text_input("비밀번호", type="password", key="login_pw_input").strip()
    
    col_l1, col_l2 = st.columns(2)
    with col_l1:
        if st.button("로그인하기", use_container_width=True):
            if login_id in master_db["users_master"] and master_db["users_master"][login_id]["pw"] == login_pw:
                user_info = master_db["users_master"][login_id]
                st.session_state.current_user = login_id
                st.session_state.user_role = "leader"
                st.session_state.current_team_id = user_info["team_id"]
                
                if st.session_state.current_team_id in master_db["teams_master"]:
                    st.session_state.step = "main_home"
                else:
                    st.session_state.step = "setup_1"
                st.rerun()
            else:
                st.error("아이디 또는 비밀번호가 잘못되었습니다.")
    with col_l2:
        if st.button("새로운 팀 개설하기 (조장 가입)", use_container_width=True):
            st.session_state.step = "auth_register"
            st.rerun()

# ==========================================
# [분기 3] 조장 회원가입 (고유 컨테이너 ID 할당)
# ==========================================
elif st.session_state.step == "auth_register":
    st.title("📝 신규 프로젝트 팀 등록 마법사")
    
    reg_id = st.text_input("원하는 조장 ID", key="reg_id_input").strip()
    reg_pw = st.text_input("원하는 비밀번호", type="password", key="reg_pw_input").strip()
    
    if "id_checked" not in st.session_state:
        st.session_state.id_checked = False
        
    if st.button("아이디 중복 검증"):
        if not reg_id:
            st.warning("아이디를 입력하세요.")
        elif reg_id in master_db["users_master"]:
            st.error("❌ 이미 존재하거나 사용 중인 조장 ID입니다.")
            st.session_state.id_checked = False
        else:
            st.success("✔️ 사용 가능한 멋진 아이디입니다.")
            st.session_state.id_checked = True
            
    if st.button("새로운 프로젝트 방 개설 완료"):
        if not st.session_state.id_checked:
            st.error("ID 중복 검증 단계를 통과해야 완료할 수 있습니다.")
        elif not reg_pw:
            st.error("비밀번호를 입력하세요.")
        else:
            new_team_id = str(uuid.uuid4())
            master_db["users_master"][reg_id] = {
                "pw": reg_pw, "team_id": new_team_id
            }
            save_all_data(master_db)
            st.session_state.id_checked = False
            st.session_state.step = "auth_login"
            st.success("팀 생성이 완료되었습니다! 개설한 ID로 로그인해 주세요.")
            st.rerun()

# ==========================================
# [분기 4] 팀 빌딩 마법사 (1단계 ~ 5단계)
# ==========================================
elif st.session_state.step == "setup_1":
    st.title("🚀 스타트리 초기 설정")
    st.subheader("1단계: 팀의 총원(인원수)을 지정해 주세요.")
    count = st.number_input("인원 수 (명)", min_value=1, max_value=20, value=1)
    if st.button("다음 단계로"):
        master_db["teams_master"][st.session_state.current_team_id] = {
            "member_count": count,
            "members": [{"이름": "", "연락처": "", "역할": ""} for _ in range(count)],
            "leader_idx": 0, "team_name": "", "subject": "",
            "start_date": datetime.today().date(), "end_date": datetime.today().date() + timedelta(days=7),
            "calendar_events": {}, "notices": [], "chats": [], "stories": [], "stocks": {}, "stock_logs": {}
        }
        save_all_data(master_db)
        st.session_state.step = "setup_2"
        st.rerun()

elif st.session_state.step == "setup_2":
    st.title("🚀 스타트리 초기 설정")
    st.subheader("2단계: 팀원 명부를 작성하고 실제 조장을 지정하세요.")
    
    current_team = master_db["teams_master"][st.session_state.current_team_id]
    member_names = []
    
    for i in range(current_team["member_count"]):
        st.markdown(f"#### 👤 조원 {i+1}")
        col1, col2, col3 = st.columns(3)
        with col1: current_team["members"][i]["이름"] = st.text_input("이름(성명)", value=current_team["members"][i]["이름"], key=f"setup_n_{i}").strip()
        with col2: current_team["members"][i]["연락처"] = st.text_input("연락처(- 포함)", value=current_team["members"][i]["연락처"], key=f"setup_p_{i}")
        with col3: current_team["members"][i]["역할"] = st.text_input("배정 업무", value=current_team["members"][i]["역할"], key=f"setup_r_{i}")
        member_names.append(current_team["members"][i]["이름"] if current_team["members"][i]["이름"] else f"조원 {i+1}")
        
    st.write("---")
    current_team["leader_idx"] = st.selectbox("👑 기입한 조원 중 누가 '조장(팀장)' 인가요?", range(current_team["member_count"]), format_func=lambda x: member_names[x])
    
    if st.button("다음 단계로"):
        if any(not m["이름"] for m in current_team["members"]):
            st.error("명단에 빈 칸이 있으면 안 됩니다. 이름을 채워주세요.")
        else:
            save_all_data(master_db)
            st.session_state.step = "setup_3"
            st.rerun()

elif st.session_state.step == "setup_3":
    st.title("🚀 스타트리 초기 설정")
    st.subheader("3단계: 프로젝트 팀 명칭(조 이름)을 정해 주세요.")
    t_name = st.text_input("예: 스파크조, 크리에이티브팀 등", key="t_name_setup")
    if st.button("다음 단계로"):
        master_db["teams_master"][st.session_state.current_team_id]["team_name"] = t_name if t_name.strip() else "우리팀"
        save_all_data(master_db)
        st.session_state.step = "setup_4"
        st.rerun()

elif st.session_state.step == "setup_4":
    st.title("🚀 스타트리 초기 설정")
    st.subheader("4단계: 프로젝트 팀 과제 주제를 입력해 주세요.")
    subj = st.text_input("예: 핀테크 앱 창업 기획안, 캡스톤 디자인 등", key="subj_setup")
    if st.button("다음 단계로"):
        master_db["teams_master"][st.session_state.current_team_id]["subject"] = subj
        save_all_data(master_db)
        st.session_state.step = "setup_5"
        st.rerun()

elif st.session_state.step == "setup_5":
    st.title("🚀 스타트리 초기 설정")
    st.subheader("5단계: 이번 팀 프로젝트의 최종 마감 기한을 선택해 주세요.")
    e_date = st.date_input("종료 데드라인 지정", key="e_date_setup")
    if st.button("다음 단계로"):
        master_db["teams_master"][st.session_state.current_team_id]["end_date"] = e_date
        save_all_data(master_db)
        st.session_state.step = "setup_link"
        st.rerun()

elif st.session_state.step == "setup_link":
    st.title("🔗 고유 얼라이언스 초대 링크 발급")
    st.subheader("우리 조 전용 독립 공간 초대장 주소입니다.")
    
    host = st.context.headers.get("Host", "localhost:8501")
    protocol = "https" if "localhost" not in host else "http"
    v_link = f"{protocol}://{host}/?invite=true&team_id={st.session_state.current_team_id}"
    
    st.info(v_link)
    st.caption("💡 위 주소를 복사해 팀원들에게 공유하세요. 조원들은 조장 이름을 제외한 명단에서 로그인 없이 즉시 입장하게 됩니다.")
    
    if st.button("🎉 링크 확인 완료 및 대시보드 오픈"):
        current_team = master_db["teams_master"][st.session_state.current_team_id]
        for m in current_team["members"]:
            if m["이름"] and m["이름"] not in current_team["stocks"]:
                current_team["stocks"][m["이름"]] = [10000]
                current_team["stock_logs"][m["이름"]] = []
        save_all_data(master_db)
        st.session_state.step = "main_home"
        st.rerun()

# ==========================================
# [분기 5] 최종 메인 비즈니스 워크스페이스 레이어
# ==========================================
else:
    if not team_data:
        st.error("세션 만료 또는 유효하지 않은 팀 ID입니다. 재접속이 필요합니다.")
        st.stop()
        
    current_name = st.session_state.current_user
    is_leader = (st.session_state.user_role == "leader")
    
    st.title(f"🌳 {team_data['team_name']} 독점 워크스페이스")
    st.markdown(f"**🎯 주제:** {team_data['subject']} | **👑 총괄조장:** {leader_name} | **👤 접속 중인 유저:** {current_name} ({'조장 플러그인' if is_leader else '조원 플러그인'})")
    st.write("---")

    tab_titles = ["📢 팀 홈 및 공지사항", "✨ 스토리 피드 광장", "📊 기여도 주식 차트", "📅 달력 일정 관리", "💬 다중 대상 DM방"]
    if is_leader:
        tab_titles.insert(4, "👥 조원 정보 수정창")
        
    tabs = st.tabs(tab_titles)
    tab_mapping = {title: tabs[i] for i, title in enumerate(tab_titles)}
    
    # --- 탭 1: 공지사항 게시판 ---
    with tab_mapping["📢 팀 홈 및 공지사항"]:
        st.subheader("📌 팀 고유 공지사항")
        
        # 🔄 실시간 자동 새로고침 영역 지정 (st.fragment 사용 - 5초 간격)
        @st.fragment(run_every=5)
        def show_notices_live():
            fresh_db = load_all_data()
            fresh_team = fresh_db["teams_master"].get(st.session_state.current_team_id, team_data)
            
            for idx, n in enumerate(fresh_team["notices"]):
                with st.container(border=True):
                    st.caption(f"📅 {n['date']}")
                    st.write(n["content"])
                    if n.get("file_bytes") is not None:
                        st.download_button(label=f"📎 파일 열기 ({n['file_name']})", data=n["file_bytes"], file_name=n["file_name"], key=f"notice_live_file_{idx}")
        
        if is_leader:
            with st.form("notice_form", clear_on_submit=True):
                notice_text = st.text_area("새로운 공지 작성")
                uploaded_file = st.file_uploader("증빙/참고 파일 스토리지 업로드")
                if st.form_submit_button("📢 공지사항 전면 게시"):
                    if notice_text.strip():
                        file_name = "첨부 파일 없음"
                        file_bytes = None
                        if uploaded_file is not None:
                            file_name = uploaded_file.name
                            file_bytes = uploaded_file.read()
                            
                        team_data["notices"].insert(0, {
                            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "content": notice_text, "file_name": file_name, "file_bytes": file_bytes
                        })
                        save_all_data(master_db)
                        st.success("공지가 실시간 전송되었습니다!")
                        st.rerun()
        else:
            st.caption("💡 공지사항 편집 권한은 마스터 조장 전용입니다. (5초 간격 실시간 자동 동기화 적용 중)")
            
        st.write("---")
        show_notices_live()

    # --- 탭 2: 피드 광장 ---
    with tab_mapping["✨ 스토리 피드 광장"]:
        st.subheader("📸 우리 팀 스토리 피드 보드")
        col_up, col_view = st.columns([2, 3])
        
        with col_up:
            with st.form("story_upload_form", clear_on_submit=True):
                st_text = st.text_area("오늘 수행한 업무 피드 요약 작성")
                st_media = st.file_uploader("사진/동영상/음성 미디어 첨부", type=["png", "jpg", "jpeg", "mp4", "mp3", "wav"])
                if st.form_submit_button("피드 스퀘어 게시") and st_text.strip():
                    media_type = None
                    media_data = None
                    if st_media is not None:
                        media_data = st_media.read()
                        if st_media.name.lower().endswith((".png", ".jpg", ".jpeg")): media_type = "image"
                        elif st_media.name.lower().endswith(".mp4"): media_type = "video"
                        elif st_media.name.lower().endswith((".mp3", ".wav")): media_type = "audio"
                            
                    display_user_name = f"{current_name}(조장)" if is_leader else f"{current_name}(조원)"
                    team_data["stories"].insert(0, {
                        "user": display_user_name, "content": st_text, "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "media_type": media_type, "media_data": media_data, "likes": 0, "comments": []
                    })
                    save_all_data(master_db)
                    st.rerun()
                    
        with col_view:
            for idx, s in enumerate(team_data["stories"]):
                with st.container(border=True):
                    st.markdown(f"🔴 **{s['user']}** | *{s['time']}*")
                    st.write(s["content"])
                    if s.get("media_type") == "image": st.image(s["media_data"], use_container_width=True)
                    elif s.get("media_type") == "video": st.video(s["media_data"])
                    elif s.get("media_type") == "audio": st.audio(s["media_data"])
                        
                    if st.button(f"❤️ 응원 {s.get('likes', 0)}개", key=f"like_b_{idx}"):
                        s["likes"] = s.get("likes", 0) + 1
                        save_all_data(master_db)
                        st.rerun()
                    
                    for cm in s.get("comments", []):
                        st.markdown(f"**{cm['writer']}**: {cm['text']}")
                    with st.form(f"comment_f_{idx}", clear_on_submit=True):
                        c_text = st.text_input("댓글 피드백 달기", key=f"cm_t_{idx}")
                        if st.form_submit_button("댓글 게시") and c_text.strip():
                            s["comments"].append({"writer": f"{current_name}", "text": c_text})
                            save_all_data(master_db)
                            st.rerun()

    # --- 탭 3: 기여도 차트 ---
    with tab_mapping["📊 기여도 주식 차트"]:
        st.subheader("📊 조원 기여 가치 지분 대시보드")
        if team_data.get("stocks"):
            grid_cols = st.columns(len(team_data["stocks"]))
            for index, name in enumerate(team_data["stocks"].keys()):
                with grid_cols[index]:
                    current_val = team_data["stocks"][name][-1]
                    logs = team_data["stock_logs"].get(name, [])
                    with st.container(border=True):
                        st.markdown(f"**{name}**")
                        st.markdown(f"지분 지표: **{current_val:,} P**")
                        if logs:
                            last_log = logs[-1]
                            color = "#2ec4b6" if last_log["type"] == "plus" else "#e71d36"
                            sign = "+" if last_log["type"] == "plus" else "-"
                            st.markdown(f"<span style='color:{color}; font-weight:bold;'>{sign}{last_log['val']:,} P</span>", unsafe_allow_html=True)
            
            st.write("---")
            selected_stock_user = st.selectbox("추적 대상 조원 정밀 조회", list(team_data["stocks"].keys()))
            if selected_stock_user:
                user_history = team_data["stocks"][selected_stock_user]
                chart_df = pd.DataFrame({"기여도 가치 추이 (P)": user_history})
                st.line_chart(chart_df)

    # --- 탭 4: 달력 일정 관리 ---
    with tab_mapping["📅 달력 일정 관리"]:
        st.subheader("📅 우리 팀 업무 결재선 타임라인")
        
        start_date = team_data.get("start_date", datetime.today().date())
        end_date = team_data.get("end_date", datetime.today().date())
        if isinstance(start_date, str): start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        if isinstance(end_date, str): end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        
        date_list = [start_date + timedelta(days=i) for i in range((end_date - start_date).days + 1)]
        date_strs = [str(d) for d in date_list]
        
        if is_leader:
            col_reg1, col_reg2, col_reg3 = st.columns([2, 2, 4])
            with col_reg1: selected_date_str = st.selectbox("날짜 지정", date_strs, key="sel_date")
            with col_reg2: worker_input = st.selectbox("책임 담당자 지정", m_names if m_names else ["없음"], key="sel_worker")
            with col_reg3: event_input = st.text_input("상세 과업 임무 내용 기입", key="sel_content")
                
            if st.button("➕ 새로운 업무 분배 배치"):
                if event_input.strip():
                    if selected_date_str not in team_data["calendar_events"] or not isinstance(team_data["calendar_events"][selected_date_str], list):
                        team_data["calendar_events"][selected_date_str] = []
                    
                    team_data["calendar_events"][selected_date_str].append({
                        "id": len(team_data["calendar_events"][selected_date_str]),
                        "content": event_input.strip(), "status": "⏳", "worker": worker_input
                    })
                    save_all_data(master_db)
                    st.success("배치 성공")
                    st.rerun()
        
        st.write("---")
        for d_str in date_strs:
            day_events = team_data["calendar_events"].get(d_str, [])
            if not isinstance(day_events, list): day_events = []
                
            if not day_events:
                c_d, c_w, c_c, c_s, c_ops = st.columns([1.5, 1.2, 4.5, 1.0, 1.8])
                c_d.write(d_str)
                c_w.write("👤 미지정")
                c_c.write("등록된 전술 과업이 없습니다.")
                c_s.write("-")
            else:
                for idx in range(len(day_events) - 1, -1, -1):
                    ev = day_events[idx]
                    c_d, c_w, c_c, c_s, c_ops = st.columns([1.5, 1.2, 4.5, 1.0, 1.8])
                    
                    c_d.write(d_str)
                    c_w.write(f"👤 {ev['worker']}")
                    c_c.write(ev['content'])
                    c_s.write("✔️ 결재승인" if "✔️" in ev["status"] else "❌ 이행반려" if "❌" in ev["status"] else "⏳ 검토대기")
                    
                    if is_leader:
                        with c_ops:
                            b1, b2, b3 = st.columns(3)
                            with b1:
                                if st.button("✔️", key=f"v_{d_str}_{idx}_{ev.get('id', idx)}"):
                                    ev["status"] = "✔️"
                                    tw = ev["worker"]
                                    if tw in team_data["stocks"]:
                                        team_data["stocks"][tw].append(team_data["stocks"][tw][-1] + 3000)
                                        team_data["stock_logs"].setdefault(tw, []).append({"type": "plus", "val": 3000, "reason": f"{d_str} 결재성공"})
                                    save_all_data(master_db)
                                    st.rerun()
                            with b2:
                                if st.button("❌", key=f"x_{d_str}_{idx}_{ev.get('id', idx)}"):
                                    ev["status"] = "❌"
                                    tw = ev["worker"]
                                    if tw in team_data["stocks"]:
                                        team_data["stocks"][tw].append(max(1000, team_data["stocks"][tw][-1] - 3000))
                                        team_data["stock_logs"].setdefault(tw, []).append({"type": "minus", "val": 3000, "reason": f"{d_str} 태만반려"})
                                    save_all_data(master_db)
                                    st.rerun()
                            with b3:
                                if st.button("🗑️", key=f"del_{d_str}_{idx}_{ev.get('id', idx)}"):
                                    team_data["calendar_events"][d_str].pop(idx)
                                    save_all_data(master_db)
                                    st.rerun()
                    else:
                        c_ops.write("🔒 변경불가")

    # --- 탭 5: 조원 정보 수정창 (조장 전용 차단막 완비) ---
    if is_leader:
        with tab_mapping["👥 조원 정보 수정창"]:
            st.subheader("👥 조원 명부 실시간 편집 마이그레이션")
            edit_team_name = st.text_input("조 이름 변경", value=team_data["team_name"])
            edit_subject = st.text_input("프로젝트 주제 변경", value=team_data["subject"])
            if st.button("핵심 메타데이터 수정 동기화"):
                team_data["team_name"] = edit_team_name
                team_data["subject"] = edit_subject
                save_all_data(master_db)
                st.success("정보가 변경되었습니다.")
                st.rerun()
                
            st.write("---")
            updated_members = []
            for i in range(len(team_data["members"])):
                is_leader_mark = " (👑 조장)" if i == team_data["leader_idx"] else ""
                st.markdown(f"#### 👤 조원 {i+1}{is_leader_mark} 정보 수정")
                
                old_name = team_data["members"][i]["이름"]
                new_name = st.text_input(f"성명", value=old_name, key=f"fixed_n_{i}").strip()
                fixed_p = st.text_input(f"연락처", value=team_data["members"][i]["연락처"], key=f"fixed_p_{i}")
                fixed_r = st.text_input(f"역할군", value=team_data["members"][i]["역할"], key=f"fixed_r_{i}")
                
                updated_members.append({"이름": new_name, "연락처": fixed_p, "역할": fixed_r})
                
                if old_name and new_name and old_name != new_name:
                    if old_name in team_data["stocks"]:
                        team_data["stocks"][new_name] = team_data["stocks"].pop(old_name)
                    if old_name in team_data["stock_logs"]:
                        team_data["stock_logs"][new_name] = team_data["stock_logs"].pop(old_name)
                        
            if st.button("👥 수정된 원장 명부 최종 인덱싱 배포"):
                team_data["members"] = updated_members
                for m in team_data["members"]:
                    if m["이름"] and m["이름"] not in team_data["stocks"]:
                        team_data["stocks"][m["이름"]] = [10000]
                        team_data["stock_logs"][m["이름"]] = []
                save_all_data(master_db)
                st.success("명단 배포 완료!")
                st.rerun()

    # --- 탭 6: 다중 대상 DM방 (보안 필터링 및 5초 주기 자동 동기화 완비) ---
    with tab_mapping["💬 다중 대상 DM방"]:
        st.subheader("💬 팀 내부 전용 고속 실시간 DM 라우터")
        st.caption("🔒 본인이 발신했거나, 수신 대상자로 지정된 프라이빗 메시지만 화면에 안전하게 표시됩니다.")
        
        # 🔄 카카오톡처럼 백그라운드에서 실시간으로 나와 연관된 채팅만 로드하는 컴포넌트
        @st.fragment(run_every=5)
        def show_chats_live():
            fresh_db = load_all_data()
            fresh_team = fresh_db["teams_master"].get(st.session_state.current_team_id, team_data)
            
            chat_box = st.container(height=300)
            with chat_box:
                for c in fresh_team["chats"]:
                    # 수신자 문자열(예: "1, 2, 3")을 리스트로 분리 및 공백 제거
                    receiver_list = [r.strip() for r in c['receivers'].split(",")]
                    
                    # 보안 조건: 내가 보낸 메시지이거나, 수신 대상에 내 이름(current_name)이 있는 경우만 노출
                    if current_name in c['sender'] or current_name in receiver_list:
                        st.markdown(f"**[{c['sender']} ➔ {c['receivers']}]** <small>{c['time']}</small>", unsafe_allow_html=True)
                        st.info(c["msg"])
        
        # 보안 실시간 채팅창 출력
        show_chats_live()
                
        with st.form("multi_dm_form", clear_on_submit=True):
            all_target_names = list(m_names)
            if leader_name not in all_target_names: 
                all_target_names.append(leader_name)
                
            selected_receivers = st.multiselect("메시지 수신 대상 조원 선택", all_target_names, default=all_target_names)
            dm_msg = st.text_input("메시지 작성", placeholder="전송 시 수신 대상자의 화면에만 즉시 업데이트됩니다.")
            
            if st.form_submit_button("🚀 전용 채널 메시지 발송"):
                if dm_msg.strip():
                    if not selected_receivers:
                        st.error("최소 한 명 이상의 수신 대상을 지정해야 합니다.")
                    else:
                        sender_display = f"{current_name}(조장)" if is_leader else f"{current_name}(조원)"
                        team_data["chats"].append({
                            "sender": sender_display, 
                            "receivers": ", ".join(selected_receivers),
                            "msg": dm_msg, 
                            "time": datetime.now().strftime("%H:%M")
                        })
                        save_all_data(master_db)
                        st.rerun()
