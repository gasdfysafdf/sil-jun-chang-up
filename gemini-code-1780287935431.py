import streamlit as st
import pandas as pd
import os
import uuid
import json
from datetime import datetime, timedelta
from supabase import create_client, Client

st.set_page_config(page_title="스타트리 (Startree) - 마스터 통합본", page_icon="🌳", layout="wide")

# --- [Supabase 연결] ---
# Streamlit Cloud의 경우 .streamlit/secrets.toml에 설정
# 로컬의 경우 .streamlit/secrets.toml 파일을 만들어서 아래 형식으로 입력:
#
# [supabase]
# url = "https://xxxxxx.supabase.co"
# key = "your-anon-key"

@st.cache_resource
def get_supabase_client() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

supabase = get_supabase_client()

# --- [멀티팀 & 관리자 데이터베이스 엔진 - Supabase 버전] ---
# Supabase에 'startree_db' 테이블 하나만 사용
# 컬럼: id (text, primary key), data (jsonb)
# 딱 하나의 row (id='main')에 전체 데이터를 JSON으로 저장

# 관리자 계정은 Streamlit Secrets에서 불러옴 (코드에 직접 노출 금지)
ADMIN_ID = st.secrets["admin"]["id"]
ADMIN_PW = st.secrets["admin"]["pw"]

DEFAULT_DB = {
    "users_master": {},
    "teams_master": {},
    "admin_master": {
        "admin_id": ADMIN_ID,
        "admin_pw": ADMIN_PW,
        "system_notices": [],
        "bug_reports": []
    }
}

def load_all_data():
    try:
        res = supabase.table("startree_db").select("data").eq("id", "main").execute()
        if res.data and len(res.data) > 0:
            db = res.data[0]["data"]
            # 하위 호환성 보정
            if "admin_master" not in db:
                db["admin_master"] = DEFAULT_DB["admin_master"].copy()
            if "users_master" not in db:
                db["users_master"] = {}
            if "teams_master" not in db:
                db["teams_master"] = {}
            return db
        else:
            # 최초 실행: row 생성
            supabase.table("startree_db").insert({"id": "main", "data": DEFAULT_DB}).execute()
            return DEFAULT_DB.copy()
    except Exception as e:
        st.error(f"DB 연결 오류: {e}")
        return DEFAULT_DB.copy()

def save_all_data(master_db):
    try:
        supabase.table("startree_db").upsert({"id": "main", "data": master_db}).execute()
    except Exception as e:
        st.error(f"DB 저장 오류: {e}")

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
if "active_chat_room_id" not in st.session_state:
    st.session_state.active_chat_room_id = None  

# 🔗 초대 링크 트래킹 및 검증 로직 (관리자가 아닐 때만 작동)
qp = st.query_params
if "invite" in qp and "team_id" in qp:
    target_team = qp["team_id"]
    if target_team in master_db["teams_master"]:
        if st.session_state.step != "main_home" and st.session_state.step != "admin_dashboard" and st.session_state.current_user is None:
            st.session_state.current_team_id = target_team
            st.session_state.user_role = "member"
            st.session_state.step = "member_auth"

# 현재 접속 세션 데이터 맵핑 안전망
team_data = None
m_names = []
leader_name = "미정"
if st.session_state.current_team_id and st.session_state.current_team_id in master_db["teams_master"]:
    team_data = master_db["teams_master"][st.session_state.current_team_id]
    m_names = [m["이름"] for m in team_data.get("members", []) if m.get("이름")]
    if team_data.get("members") and "leader_idx" in team_data:
        try:
            leader_name = team_data["members"][team_data["leader_idx"]]["이름"]
        except Exception:
            leader_name = "미정"

# --- [사이드바 제어창] ---
with st.sidebar:
    st.title("🌳 스타트리 서비스 센터")
    
    if st.button("🔄 시스템 전체 강제 새로고침", use_container_width=True):
        st.rerun()
        
    st.write("---")
    if st.session_state.current_user:
        if st.session_state.user_role == "admin":
            st.error(f"👑 최고 마스터 관리자 권한\n\n접속 계정: {st.session_state.current_user}")
        else:
            role_label = "👑 조장" if st.session_state.user_role == "leader" else "👤 조원"
            t_name_display = team_data.get('team_name', '설정중') if team_data else "설정중"
            st.success(f"소속 조: {t_name_display}\n\n접속자: {st.session_state.current_user} [{role_label}]")
        
        if st.button("To. 로그아웃 (접속 종료)", use_container_width=True):
            st.session_state.current_user = None
            st.session_state.current_team_id = None
            st.session_state.user_role = "leader"
            st.session_state.step = "auth_login"
            st.session_state.active_chat_room_id = None
            st.query_params.clear()
            st.rerun()
    else:
        st.warning("상용화 멀티팀 독립 세션 구동 중")
        
    st.write("---")
    st.caption("⚙️ Startree Enterprise v2.0 (2026)")

# ==========================================
# [분기 1] 조원 전용 초대 링크 접속 처리 화면
# ==========================================
if st.session_state.step == "member_auth" and team_data:
    st.title("🔗 스타트리 조원 초대 가입 패스")
    st.subheader(f"🌳 '{team_data.get('team_name', '우리팀')}' 팀 워크스페이스")
    st.markdown(f"**🎯 프로젝트 주제:** {team_data.get('subject', '미정')} | **👑 담당 조장:** {leader_name}")
    
    if not m_names:
        st.error("❌ 조장님이 아직 조원 명부를 작성하지 않았습니다.")
    else:
        only_members_names = [name for name in m_names if name != leader_name]
        
        if not only_members_names:
            st.warning("현재 조장 외에 등록된 조원 성명이 존재하지 않습니다.")
            st.stop()
            
        st.info("💡 명단에서 본인의 이름을 선택하여 입장해 주세요.")
        selected_member = st.selectbox("👤 당신은 누구인가요? 본인의 이름을 선택하세요.", only_members_names)
        
        if st.button("🎉 조원 권한으로 워크스페이스 입장"):
            st.session_state.current_user = selected_member
            st.session_state.user_role = "member"
            st.session_state.step = "main_home"
            st.success(f"확인되었습니다, {selected_member} 조원님! 대시보드로 이동합니다.")
            st.rerun()

# ==========================================
# [분기 2] 대통합 로그인 화면 (3안 공유 로그인 방식 인터셉트)
# ==========================================
elif st.session_state.step == "auth_login":
    st.title("🔐 스타트리 통합 로그인 포털")

    login_id = st.text_input("아이디(ID)", key="login_id_input").strip()
    login_pw = st.text_input("비밀번호(PW)", type="password", key="login_pw_input").strip()

    col_l1, col_l2 = st.columns(2)
    with col_l1:
        if st.button("로그인하기", use_container_width=True):
            admin_cfg = master_db["admin_master"]
            if login_id == admin_cfg["admin_id"] and login_pw == admin_cfg["admin_pw"]:
                st.session_state.current_user = login_id
                st.session_state.user_role = "admin"
                st.session_state.step = "admin_dashboard"
                st.success("👑 최고 마스터 관리자 인증에 성공했습니다. 관제탑을 로드합니다.")
                st.rerun()
            elif login_id in master_db["users_master"] and master_db["users_master"][login_id]["pw"] == login_pw:
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
                st.error("아이디 또는 비밀번호가 잘못되었습니다. (대소문자 구분 확인)")
    with col_l2:
        if st.button("새로운 팀 개설하기 (조장 가입)", use_container_width=True):
            st.session_state.step = "auth_register"
            st.rerun()

    st.write("---")

    # --- [ID/PW 찾기] ---
    with st.expander("🔍 ID / 비밀번호 찾기"):
        find_tab = st.radio("어떤 정보를 잊으셨나요?", ["아이디(ID) 찾기", "비밀번호(PW) 찾기", "ID와 비밀번호 모두 잊어버렸어요"], horizontal=True, key="find_tab_radio")

        if find_tab == "아이디(ID) 찾기":
            st.caption("비밀번호와 조 이름을 입력하면 아이디를 찾아드립니다.")
            find_pw = st.text_input("비밀번호 입력", type="password", key="find_pw_input").strip()
            find_team_name = st.text_input("조 이름 입력 (예: 1조, 스파크조 등)", key="find_team_name_id").strip()
            if st.button("아이디 찾기", key="find_id_btn"):
                if not find_pw or not find_team_name:
                    st.warning("비밀번호와 조 이름을 모두 입력해주세요.")
                else:
                    found_id = None
                    for uid, uinfo in master_db["users_master"].items():
                        if uinfo["pw"] == find_pw:
                            t_info = master_db["teams_master"].get(uinfo["team_id"], {})
                            if t_info.get("team_name", "").strip() == find_team_name:
                                found_id = uid
                                break
                    if found_id:
                        st.success(f"✅ 찾으시는 아이디는 **{found_id}** 입니다.")
                    else:
                        st.error("❌ 입력하신 정보와 일치하는 계정을 찾을 수 없습니다.")

        elif find_tab == "비밀번호(PW) 찾기":
            st.caption("아이디와 조 이름을 입력하면 비밀번호를 찾아드립니다.")
            find_id = st.text_input("아이디 입력", key="find_id_input").strip()
            find_team_name2 = st.text_input("조 이름 입력 (예: 1조, 스파크조 등)", key="find_team_name_pw").strip()
            if st.button("비밀번호 찾기", key="find_pw_btn"):
                if not find_id or not find_team_name2:
                    st.warning("아이디와 조 이름을 모두 입력해주세요.")
                else:
                    found_pw = None
                    if find_id in master_db["users_master"]:
                        uinfo = master_db["users_master"][find_id]
                        t_info = master_db["teams_master"].get(uinfo["team_id"], {})
                        if t_info.get("team_name", "").strip() == find_team_name2:
                            found_pw = uinfo["pw"]
                    if found_pw:
                        st.success(f"✅ 찾으시는 비밀번호는 **{found_pw}** 입니다.")
                    else:
                        st.error("❌ 입력하신 정보와 일치하는 계정을 찾을 수 없습니다.")

        else:
            st.error("😢 ID와 비밀번호를 모두 분실하신 경우, 보안 정책상 시스템 내부에서 복구가 불가능합니다. 새로운 팀을 다시 생성해 주세요.")

    st.write("---")

    # --- [시스템 운영 안내 고정 문구] ---
    st.markdown("""
> **📋 시스템 운영 안내**
> - 🔐 **보안 주의:** 개인의 ID와 비밀번호는 다른 팀원에게 절대 공유하지 마세요.
> - ⚠️ **분실 안내:** ID와 비밀번호를 **모두** 분실하신 경우, 보안 정책상 새로운 팀을 다시 생성해야 합니다. (복구 불가)
> - 🔍 **정보 찾기:** 둘 중 하나만 잊으셨다면 위의 **[ID / 비밀번호 찾기]** 버튼을 통해 셀프 복구를 진행하세요.
""")

# ==========================================
# [분기 3] 조장 회원가입
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
        elif reg_id in master_db["users_master"] or reg_id == master_db["admin_master"]["admin_id"]:
            st.error("❌ 이미 존재하거나 사용 중인 시스템 ID입니다.")
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
# [분기 4] 팀 빌딩 마법사 (1단계 ~ 5단계 및 고유링크 발급)
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
            "start_date": str(datetime.today().date()), "end_date": str((datetime.today() + timedelta(days=7)).date()),
            "calendar_events": {}, "notices": [], "chat_rooms": [], "chats_archive": [], "stories": [], "stocks": {}, "stock_logs": {}
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
    t_name = st.text_input("예: 1조, 2조, 스파크조 등", key="t_name_setup")
    if st.button("다음 단계로"):
        master_db["teams_master"][st.session_state.current_team_id]["team_name"] = t_name if t_name.strip() else "우리팀"
        save_all_data(master_db)
        st.session_state.step = "setup_4"
        st.rerun()

elif st.session_state.step == "setup_4":
    st.title("🚀 스타트리 초기 설정")
    st.subheader("4단계: 프로젝트 팀 과제 주제를 입력해 주세요.")
    subj = st.text_input("예: 인공지능 창업 과제 등", key="subj_setup")
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
        master_db["teams_master"][st.session_state.current_team_id]["end_date"] = str(e_date)
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
    st.caption("💡 위 주소를 복사해 팀원들에게 공유하세요.")
    
    if st.button("🎉 링크 확인 완료 및 대시보드 오픈"):
        current_team = master_db["teams_master"][st.session_state.current_team_id]
        if "stocks" not in current_team: current_team["stocks"] = {}
        if "stock_logs" not in current_team: current_team["stock_logs"] = {}
        if "chat_rooms" not in current_team: current_team["chat_rooms"] = []
        if "chats_archive" not in current_team: current_team["chats_archive"] = []
        
        for m in current_team["members"]:
            if m["이름"] and m["이름"] not in current_team["stocks"]:
                current_team["stocks"][m["이름"]] = [10000]
                current_team["stock_logs"][m["이름"]] = []
        save_all_data(master_db)
        st.session_state.step = "main_home"
        st.rerun()

# ==========================================
# [분기 5] 👑 최고 마스터 관리자(Admin) 관제탑 레이어
# ==========================================
elif st.session_state.step == "admin_dashboard" and st.session_state.user_role == "admin":
    st.title("🌳 스타트리 시스템 통합 관제탑 (Master Admin Portal)")
    st.markdown(f"**⚡ 현재 일시:** {datetime.now().strftime('%Y-%m-%d %H:%M')} | **🔑 관리 계정:** {st.session_state.current_user} [🚨 최고권한 마스터]")
    st.write("---")
    
    admin_tabs = st.tabs([
        "📊 전체 현황 대시보드",
        "👥 조장 및 팀 정보 제어실",
        "🗂️ 팀 직접 편집",
        "🚨 SOS 버그 제보 수신함",
        "📢 전사 긴급 공지 송출",
        "🧹 팀 데이터 관리",
        "⚙️ 마스터 보안 및 위험구역"
    ])
    
    # --- 관리자 탭 0: 전체 현황 대시보드 ---
    with admin_tabs[0]:
        st.subheader("📊 스타트리 플랫폼 전체 현황 대시보드")
        
        total_teams = len(master_db["users_master"])
        total_members = sum(len(v.get("members", [])) for v in master_db["teams_master"].values())
        total_bugs = len(master_db["admin_master"].get("bug_reports", []))
        pending_bugs = len([r for r in master_db["admin_master"].get("bug_reports", []) if r["status"] != "✔️ 처리완료"])
        total_notices = len(master_db["admin_master"].get("system_notices", []))
        total_chats = sum(len(v.get("chats_archive", [])) for v in master_db["teams_master"].values())
        total_stories = sum(len(v.get("stories", [])) for v in master_db["teams_master"].values())

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🏢 등록 팀 수", f"{total_teams}팀")
        c2.metric("👥 전체 조원 수", f"{total_members}명")
        c3.metric("🚨 미처리 SOS", f"{pending_bugs}건", delta=f"전체 {total_bugs}건", delta_color="inverse")
        c4.metric("💬 전체 채팅 수", f"{total_chats}건")

        st.write("---")
        col_left, col_right = st.columns(2)

        with col_left:
            st.markdown("#### 📋 팀별 활동 요약")
            if not master_db["users_master"]:
                st.info("등록된 팀이 없습니다.")
            else:
                summary_rows = []
                for l_id, u_info in master_db["users_master"].items():
                    t_id = u_info["team_id"]
                    t_info = master_db["teams_master"].get(t_id, {})
                    summary_rows.append({
                        "조 이름": t_info.get("team_name", "설정중"),
                        "조장 ID": l_id,
                        "조원 수": len(t_info.get("members", [])),
                        "공지 수": len(t_info.get("notices", [])),
                        "스토리 수": len(t_info.get("stories", [])),
                        "채팅 수": len(t_info.get("chats_archive", [])),
                        "채팅방 수": len(t_info.get("chat_rooms", [])),
                    })
                st.dataframe(pd.DataFrame(summary_rows), use_container_width=True)

        with col_right:
            st.markdown("#### 🚨 미처리 SOS 빠른 보기")
            pending_list = [r for r in master_db["admin_master"].get("bug_reports", []) if r["status"] != "✔️ 처리완료"]
            if not pending_list:
                st.success("✅ 미처리 SOS 없음 - 모든 문의가 처리되었습니다.")
            else:
                for rep in reversed(pending_list[-5:]):
                    with st.container(border=True):
                        st.markdown(f"**{rep['team_name']} · {rep['sender']}** | {rep['time']}")
                        st.caption(rep["content"][:80] + ("..." if len(rep["content"]) > 80 else ""))
            
            st.write("---")
            st.markdown(f"📢 **전사 공지 {total_notices}건** 송출 중 | ✨ **스토리 {total_stories}건** 게시됨")

    # --- 관리자 탭 1: 조장 및 팀 통합 관리 원장 ---
    with admin_tabs[1]:
        st.subheader("🗂️ 가입 팀 및 조장 계정 마스터 원장")
        st.caption("현재 플랫폼에 등록된 모든 조장의 아이디와 비밀번호 실시간 리스트입니다.")
        
        if not master_db["users_master"]:
            st.info("현재 가입된 프로젝트 팀(조장)이 존재하지 않습니다.")
        else:
            team_records = []
            for l_id, u_info in master_db["users_master"].items():
                t_id = u_info["team_id"]
                t_info = master_db["teams_master"].get(t_id, {})
                team_records.append({
                    "조장 ID": l_id,
                    "비밀번호": u_info["pw"],
                    "팀 고유 고유 ID": t_id,
                    "조 이름": t_info.get("team_name", "초기 설정 미완료"),
                    "프로젝트 주제": t_info.get("subject", "-"),
                    "조원 수": len(t_info.get("members", []))
                })
            
            st.table(pd.DataFrame(team_records))
            
            st.write("---")
            st.markdown("#### 🔑 조장 비밀번호 긴급 변경 복구소")
            col_ad1, col_ad2 = st.columns(2)
            with col_ad1:
                target_edit_leader = st.selectbox("비밀번호를 재발급할 조장 ID 선택", list(master_db["users_master"].keys()))
            with col_ad2:
                new_assigned_pw = st.text_input("새로 지정할 원격 강제 비밀번호", placeholder="예: temporary1234!")
                
            if st.button("🔒 해당 조장 비밀번호 원격 강제 변경 배포"):
                if new_assigned_pw.strip():
                    master_db["users_master"][target_edit_leader]["pw"] = new_assigned_pw.strip()
                    save_all_data(master_db)
                    st.success(f"🎉 조장 [{target_edit_leader}]의 비밀번호가 성공적으로 변경되었습니다!")
                    st.rerun()

    # --- 관리자 탭 2: 팀 직접 편집 ---
    with admin_tabs[2]:
        st.subheader("🗂️ 팀 정보 및 조원 명단 직접 편집")
        st.caption("관리자가 특정 팀의 이름, 주제, 마감일, 조원 정보를 직접 수정할 수 있습니다.")

        all_team_ids = list(master_db["users_master"].keys())
        if not all_team_ids:
            st.info("등록된 팀이 없습니다.")
        else:
            # 팀 선택
            team_select_options = {}
            for l_id, u_info in master_db["users_master"].items():
                t_id = u_info["team_id"]
                t_info = master_db["teams_master"].get(t_id, {})
                label = f"{t_info.get('team_name', '설정중')} (조장: {l_id})"
                team_select_options[label] = t_id

            selected_label = st.selectbox("✏️ 편집할 팀 선택", list(team_select_options.keys()))
            edit_team_id = team_select_options[selected_label]
            edit_team = master_db["teams_master"].get(edit_team_id, {})

            if not edit_team:
                st.warning("해당 팀의 상세 데이터가 없습니다. (초기 설정 미완료)")
            else:
                st.write("---")
                st.markdown("#### 📝 기본 팀 정보 수정")
                with st.form("admin_edit_team_info_form"):
                    new_team_name = st.text_input("조 이름", value=edit_team.get("team_name", ""))
                    new_subject = st.text_input("프로젝트 주제", value=edit_team.get("subject", ""))
                    import datetime as _dt
                    try:
                        default_end = _dt.date.fromisoformat(edit_team.get("end_date", str(_dt.date.today())))
                    except Exception:
                        default_end = _dt.date.today()
                    new_end_date = st.date_input("마감 기한", value=default_end)
                    if st.form_submit_button("💾 팀 기본 정보 저장"):
                        db_w = load_all_data()
                        db_w["teams_master"][edit_team_id]["team_name"] = new_team_name.strip() or edit_team.get("team_name", "우리팀")
                        db_w["teams_master"][edit_team_id]["subject"] = new_subject.strip()
                        db_w["teams_master"][edit_team_id]["end_date"] = str(new_end_date)
                        save_all_data(db_w)
                        st.success("✅ 팀 기본 정보가 저장되었습니다.")
                        st.rerun()

                st.write("---")
                st.markdown("#### 👥 조원 명단 수정")
                members = edit_team.get("members", [])
                if not members:
                    st.caption("등록된 조원이 없습니다.")
                else:
                    with st.form("admin_edit_members_form"):
                        updated_members = []
                        member_names_for_leader = []
                        for i, m in enumerate(members):
                            st.markdown(f"**조원 {i+1}**")
                            col_m1, col_m2, col_m3 = st.columns(3)
                            with col_m1:
                                m_name = st.text_input("이름", value=m.get("이름", ""), key=f"adm_m_name_{edit_team_id}_{i}")
                            with col_m2:
                                m_contact = st.text_input("연락처", value=m.get("연락처", ""), key=f"adm_m_contact_{edit_team_id}_{i}")
                            with col_m3:
                                m_role = st.text_input("역할", value=m.get("역할", ""), key=f"adm_m_role_{edit_team_id}_{i}")
                            updated_members.append({"이름": m_name, "연락처": m_contact, "역할": m_role})
                            member_names_for_leader.append(m_name if m_name else f"조원 {i+1}")

                        current_leader_idx = edit_team.get("leader_idx", 0)
                        new_leader_idx = st.selectbox(
                            "👑 조장 지정",
                            range(len(updated_members)),
                            index=min(current_leader_idx, len(updated_members)-1),
                            format_func=lambda x: member_names_for_leader[x]
                        )
                        if st.form_submit_button("💾 조원 명단 저장"):
                            db_w = load_all_data()
                            db_w["teams_master"][edit_team_id]["members"] = updated_members
                            db_w["teams_master"][edit_team_id]["leader_idx"] = new_leader_idx
                            save_all_data(db_w)
                            st.success("✅ 조원 명단이 저장되었습니다.")
                            st.rerun()
                    
    # --- 관리자 탭 3: 버그 리포트 & SOS 센터 ---
    with admin_tabs[3]:
        st.subheader("📥 1:1 버그 제보 및 SOS 문의 수신함")
        
        # 2초 간격 실시간 모니터링
        @st.fragment(run_every=3)
        def show_admin_bug_reports_live():
            fresh_db = load_all_data()
            reports = fresh_db["admin_master"].get("bug_reports", [])
            
            if not reports:
                st.info("현재 접수된 SOS 버그 문의가 없습니다. 시스템 정상 가동 중")
            else:
                for idx, rep in enumerate(reversed(reports)):
                    # 역순 인덱스 정합성 매칭
                    true_idx = len(reports) - 1 - idx
                    with st.container(border=True):
                        col_r1, col_r2 = st.columns([3, 1])
                        with col_r1:
                            status_badge = "🟢 완료" if rep["status"] == "✔️ 처리완료" else "⏳ 대기"
                            st.markdown(f"### [{status_badge}] {rep['team_name']} - {rep['sender']} 조원")
                            st.caption(f"📅 제보 시간: {rep['time']} | 🆔 팀 ID: {rep['team_id']}")
                            st.warning(f"💬 내용: {rep['content']}")
                        with col_r2:
                            if rep.get("image_bytes"):
                                st.image(rep["image_bytes"], caption="📷 클릭 시 확대 가능", use_container_width=True)
                            else:
                                st.caption("첨부 이미지 없음")
                        
                        if rep.get("reply"):
                            st.info(f"👑 내 답변: {rep['reply']}")
                        
                        # 답변 작성 폼
                        with st.form(f"admin_reply_form_{rep['report_id']}_{true_idx}", clear_on_submit=True):
                            reply_text = st.text_input("답변 내용 기입", key=f"admin_rep_in_{rep['report_id']}_{true_idx}")
                            c_b1, c_b2 = st.columns(2)
                            with c_b1:
                                if st.form_submit_button("🚀 답변 전송 및 완료"):
                                    db_write = load_all_data()
                                    db_write["admin_master"]["bug_reports"][true_idx]["reply"] = reply_text.strip()
                                    db_write["admin_master"]["bug_reports"][true_idx]["status"] = "✔️ 처리완료"
                                    save_all_data(db_write)
                                    st.rerun()
                            with c_b2:
                                if st.form_submit_button("🗑️ 리포트 영구 삭제"):
                                    db_write = load_all_data()
                                    db_write["admin_master"]["bug_reports"].pop(true_idx)
                                    save_all_data(db_write)
                                    st.rerun()
        show_admin_bug_reports_live()

    # --- 관리자 탭 4: 전사 공지사항 송출 ---
    with admin_tabs[4]:
        st.subheader("📢 전사 서비스 긴급 공지 배너 배포 타워")
        st.caption("이곳에서 공지를 작성하면 서비스를 사용하는 모든 팀 대시보드 최상단에 빨간색 비상 안내판이 강제 로드됩니다.")
        
        with st.form("sys_notice_form", clear_on_submit=True):
            sys_msg = st.text_area("공지 내용 (예: 금일 서버 점검 안내 등)")
            if st.form_submit_button("🚨 전 시스템 강제 긴급 공지 송출"):
                if sys_msg.strip():
                    master_db["admin_master"].setdefault("system_notices", []).insert(0, {
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "msg": sys_msg.strip()
                    })
                    save_all_data(master_db)
                    st.success("전사 공지가 성공적으로 배포되었습니다!")
                    st.rerun()
                    
        st.write("---")
        st.markdown("#### 📜 송출 중인 전사 공지 히스토리")
        for idx, sn in enumerate(master_db["admin_master"].get("system_notices", [])):
            with st.container(border=True):
                st.caption(f"📅 {sn['time']}")
                st.write(sn["msg"])
                if st.button("🗑️ 삭제", key=f"del_sys_n_{idx}"):
                    master_db["admin_master"]["system_notices"].pop(idx)
                    save_all_data(master_db)
                    st.rerun()

    # --- 관리자 탭 5: 팀 데이터 관리 ---
    with admin_tabs[5]:
        st.subheader("🧹 팀 데이터 세밀 관리")
        st.caption("특정 팀의 채팅·스토리·공지 초기화, 또는 팀 계정 완전 삭제를 수행합니다.")

        all_user_ids = list(master_db["users_master"].keys())
        if not all_user_ids:
            st.info("등록된 팀이 없습니다.")
        else:
            mgmt_options = {}
            for l_id, u_info in master_db["users_master"].items():
                t_id = u_info["team_id"]
                t_info = master_db["teams_master"].get(t_id, {})
                label = f"{t_info.get('team_name', '설정중')} (조장: {l_id})"
                mgmt_options[label] = (l_id, t_id)

            selected_mgmt_label = st.selectbox("🎯 관리 대상 팀 선택", list(mgmt_options.keys()), key="mgmt_team_select")
            mgmt_leader_id, mgmt_team_id = mgmt_options[selected_mgmt_label]
            mgmt_team = master_db["teams_master"].get(mgmt_team_id, {})

            st.write("---")
            col_d1, col_d2 = st.columns(2)

            with col_d1:
                st.markdown("#### 🗑️ 항목별 초기화")
                st.warning("초기화는 복구가 불가능합니다.")
                init_chat = st.button("💬 채팅 전체 초기화", use_container_width=True, key="init_chat_btn")
                init_story = st.button("✨ 스토리 피드 초기화", use_container_width=True, key="init_story_btn")
                init_notice = st.button("📢 팀 공지사항 초기화", use_container_width=True, key="init_notice_btn")
                init_chatrooms = st.button("🚪 채팅방 목록 초기화", use_container_width=True, key="init_chatrooms_btn")
                init_calendar = st.button("📅 캘린더 일정 초기화", use_container_width=True, key="init_calendar_btn")

                if init_chat:
                    db_w = load_all_data()
                    db_w["teams_master"][mgmt_team_id]["chats_archive"] = []
                    save_all_data(db_w)
                    st.success("✅ 채팅 기록이 초기화되었습니다.")
                    st.rerun()
                if init_story:
                    db_w = load_all_data()
                    db_w["teams_master"][mgmt_team_id]["stories"] = []
                    save_all_data(db_w)
                    st.success("✅ 스토리 피드가 초기화되었습니다.")
                    st.rerun()
                if init_notice:
                    db_w = load_all_data()
                    db_w["teams_master"][mgmt_team_id]["notices"] = []
                    save_all_data(db_w)
                    st.success("✅ 팀 공지사항이 초기화되었습니다.")
                    st.rerun()
                if init_chatrooms:
                    db_w = load_all_data()
                    db_w["teams_master"][mgmt_team_id]["chat_rooms"] = []
                    db_w["teams_master"][mgmt_team_id]["chats_archive"] = []
                    save_all_data(db_w)
                    st.success("✅ 채팅방 목록과 대화 내역이 초기화되었습니다.")
                    st.rerun()
                if init_calendar:
                    db_w = load_all_data()
                    db_w["teams_master"][mgmt_team_id]["calendar_events"] = {}
                    save_all_data(db_w)
                    st.success("✅ 캘린더 일정이 초기화되었습니다.")
                    st.rerun()

            with col_d2:
                st.markdown("#### ☣️ 팀 계정 완전 삭제")
                st.error("팀 계정을 삭제하면 해당 조장 ID, 팀 정보, 모든 데이터가 영구 삭제됩니다.")
                confirm_delete_team = st.checkbox(f"'{selected_mgmt_label}' 팀을 완전히 삭제하겠습니다.", key="confirm_delete_team_cb")
                if st.button("🗑️ 선택한 팀 완전 삭제", use_container_width=True, key="delete_team_final_btn"):
                    if confirm_delete_team:
                        db_w = load_all_data()
                        if mgmt_leader_id in db_w["users_master"]:
                            del db_w["users_master"][mgmt_leader_id]
                        if mgmt_team_id in db_w["teams_master"]:
                            del db_w["teams_master"][mgmt_team_id]
                        save_all_data(db_w)
                        st.success(f"✅ '{selected_mgmt_label}' 팀이 완전히 삭제되었습니다.")
                        st.rerun()
                    else:
                        st.warning("위의 삭제 동의 체크박스에 체크해야 작동합니다.")

                st.write("---")
                st.markdown("#### 📬 SOS 버그 리포트 일괄 삭제")
                st.caption("처리 완료된 리포트만 일괄 정리합니다.")
                if st.button("🧹 처리완료 SOS 일괄 삭제", use_container_width=True, key="clean_done_sos_btn"):
                    db_w = load_all_data()
                    db_w["admin_master"]["bug_reports"] = [
                        r for r in db_w["admin_master"].get("bug_reports", [])
                        if r["status"] != "✔️ 처리완료"
                    ]
                    save_all_data(db_w)
                    st.success("✅ 처리완료된 SOS 리포트가 정리되었습니다.")
                    st.rerun()

    # --- 관리자 탭 6: 관리자 계정 변경 & 위험 구역 ---
    with admin_tabs[6]:
        st.subheader("⚙️ 최고 권한 마스터 계정 설정 변경")
        with st.form("admin_profile_form"):
            new_ad_id = st.text_input("새 최고 관리자 ID", value=master_db["admin_master"]["admin_id"]).strip()
            new_ad_pw = st.text_input("새 최고 관리자 비밀번호", value=master_db["admin_master"]["admin_pw"], type="password").strip()
            if st.form_submit_button("마스터 계정 정보 즉시 갱신"):
                if new_ad_id and new_ad_pw:
                    master_db["admin_master"]["admin_id"] = new_ad_id
                    master_db["admin_master"]["admin_pw"] = new_ad_pw
                    save_all_data(master_db)
                    st.success("관리자 프로필이 변경되었습니다. 다음 로그인부터 적용됩니다.")
                    st.rerun()
                    
        st.write("---")
        st.error("☣️ 위험 구역 (Danger Zone) - 일반 사용자 화면에서 격리됨")
        st.markdown("#### 🚨 시스템 마스터 DB 포맷")
        st.caption("이 버튼을 누르면 가입된 모든 팀의 데이터, 조장 계정, 채팅 아카이브, 버그 리포트가 소스에서 전면 파괴됩니다.")
        
        # 실수 방지 2중 안전 잠금장치
        confirm_format = st.checkbox("내가 모든 책임을 지며 시스템 원장을 전면 폭파하는 것에 동의합니다.")
        if st.button("⚠️ [관리자 마스터 최종 권한] DB 원장 전체 포맷 실행"):
            if confirm_format:
                # Supabase 기반 전체 포맷: 기존 row를 DEFAULT_DB로 초기화
                reset_db = {
                    "users_master": {},
                    "teams_master": {},
                    "admin_master": {
                        "admin_id": master_db["admin_master"]["admin_id"],
                        "admin_pw": master_db["admin_master"]["admin_pw"],
                        "system_notices": [],
                        "bug_reports": []
                    }
                }
                save_all_data(reset_db)
                st.session_state.clear()
                st.query_params.clear()
                st.rerun()
            else:
                st.warning("위의 파괴 동의 체크박스에 체크해야 작동합니다.")

# ==========================================
# [분기 6] 최종 메인 비즈니스 워크스페이스 레이어
# ==========================================
else:
    if not team_data:
        st.error("세션 만료 또는 유효하지 않은 팀 ID입니다. 재접속이 필요합니다.")
        st.stop()
        
    current_name = st.session_state.current_user
    is_leader = (st.session_state.user_role == "leader")
    my_chat_name = leader_name if (is_leader and leader_name != "미정") else current_name

    # 🚨 [신규 기능 연동] 전사 긴급 공지 실시간 강제 상단 팝업 로드 (3초 자동새로고침)
    @st.fragment(run_every=3)
    def show_system_notice_banner():
        fresh_db = load_all_data()
        notices = fresh_db["admin_master"].get("system_notices", [])
        if notices:
            latest_sys_notice = notices[0]
            st.error(f"📢 [전사 시스템 마스터 긴급 공지 - {latest_sys_notice['time']}]\n\n{latest_sys_notice['msg']}")
        else:
            st.empty()
    show_system_notice_banner()

    st.title(f"🌳 {team_data.get('team_name', '우리팀')} 독점 워크스페이스")
    st.markdown(f"**🎯 주제:** {team_data.get('subject', '과제 주제')} | **👑 총괄조장:** {leader_name} | **👤 접속자:** {my_chat_name} ({'조장 플러그인' if is_leader else '조원 플러그인'})")
    st.write("---")

    tab_titles = ["📢 팀 홈 및 공지사항", "✨ 스토리 피드 광장", "📊 기여도 주식 차트", "📅 달력 일정 관리", "💬 멀티 카톡방 메신저", "🚨 관리자 SOS 고객센터"]
    if is_leader:
        tab_titles.insert(4, "👥 조원 정보 수정창")
        
    tabs = st.tabs(tab_titles)
    tab_mapping = {title: tabs[i] for i, title in enumerate(tab_titles)}
    
    # --- 탭 1: 공지사항 게시판 ---
    with tab_mapping["📢 팀 홈 및 공지사항"]:
        st.subheader("📌 팀 고유 공지사항")
        
        @st.fragment(run_every=3)
        def show_notices_live():
            fresh_db = load_all_data()
            fresh_team = fresh_db["teams_master"].get(st.session_state.current_team_id, team_data)
            
            for idx, n in enumerate(fresh_team.get("notices", [])):
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
                            
                        team_data.setdefault("notices", []).insert(0, {
                            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "content": notice_text, "file_name": file_name, "file_bytes": file_bytes
                        })
                        save_all_data(master_db)
                        st.success("공지가 실시간 전송되었습니다!")
                        st.rerun()
        else:
            st.caption("💡 공지사항 편집 권한은 마스터 조장 전용입니다. (2초 간격 실시간 자동 동기화)")
            
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
                            
                    team_data.setdefault("stories", []).insert(0, {
                        "story_id": str(uuid.uuid4()),
                        "user": f"{my_chat_name}", "content": st_text, "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "media_type": media_type, "media_data": media_data, "likes": 0, "comments": []
                    })
                    save_all_data(master_db)
                    st.rerun()
                    
        with col_view:
            @st.fragment(run_every=3)
            def show_stories_live():
                fresh_db = load_all_data()
                fresh_team = fresh_db["teams_master"].get(st.session_state.current_team_id, team_data)
                stories_list = fresh_team.get("stories", [])
                
                for s in stories_list:
                    s_id = s.get("story_id", s.get("time", str(uuid.uuid4())))
                    
                    with st.container(border=True):
                        st.markdown(f"🔴 **{s['user']}** | *{s['time']}*")
                        st.write(s["content"])
                        if s.get("media_type") == "image": st.image(s["media_data"], use_container_width=True)
                        elif s.get("media_type") == "video": st.video(s["media_data"])
                        elif s.get("media_type") == "audio": st.audio(s["media_data"])
                            
                        if st.button(f"❤️ 응원 {s.get('likes', 0)}개", key=f"like_b_{s_id}"):
                            db_to_write = load_all_data()
                            for origin_s in db_to_write["teams_master"][st.session_state.current_team_id].get("stories", []):
                                if origin_s.get("story_id") == s_id or (not origin_s.get("story_id") and origin_s.get("time") == s.get("time")):
                                    origin_s["likes"] = origin_s.get("likes", 0) + 1
                                    s["likes"] = origin_s["likes"]
                                    break
                            save_all_data(db_to_write)
                        
                        for cm in s.get("comments", []):
                            st.markdown(f"**{cm['writer']}**: {cm['text']}")
                            
                        with st.form(f"comment_f_{s_id}", clear_on_submit=True):
                            c_text = st.text_input("댓글 피드백 달기", key=f"cm_t_{s_id}")
                            if st.form_submit_button("댓글 게시") and c_text.strip():
                                db_to_write = load_all_data()
                                new_comment = {"writer": f"{my_chat_name}", "text": c_text.strip()}
                                
                                for origin_s in db_to_write["teams_master"][st.session_state.current_team_id].get("stories", []):
                                    if origin_s.get("story_id") == s_id or (not origin_s.get("story_id") and origin_s.get("time") == s.get("time")):
                                        origin_s.setdefault("comments", []).append(new_comment)
                                        s.setdefault("comments", []).append(new_comment)
                                        break
                                save_all_data(db_to_write)
            show_stories_live()

    # --- 탭 3: 기여도 차트 ---
    with tab_mapping["📊 기여도 주식 차트"]:
        st.subheader("📊 조원 기여 가치 지분 대시보드")
        
        @st.fragment(run_every=3)
        def show_stocks_live():
            fresh_db = load_all_data()
            fresh_team = fresh_db["teams_master"].get(st.session_state.current_team_id, team_data)
            
            if fresh_team.get("stocks"):
                grid_cols = st.columns(len(fresh_team["stocks"]))
                for index, name in enumerate(fresh_team["stocks"].keys()):
                    with grid_cols[index]:
                        current_val = fresh_team["stocks"][name][-1]
                        logs = fresh_team.get("stock_logs", {}).get(name, [])
                        with st.container(border=True):
                            st.markdown(f"**{name}**")
                            st.markdown(f"지분 지표: **{current_val:,} P**")
                            if logs:
                                last_log = logs[-1]
                                color = "#2ec4b6" if last_log["type"] == "plus" else "#e71d36"
                                sign = "+" if last_log["type"] == "plus" else "-"
                                st.markdown(f"<span style='color:{color}; font-weight:bold;'>{sign}{last_log['val']:,} P</span>", unsafe_allow_html=True)
                
                st.write("---")
                selected_stock_user = st.selectbox("추적 대상 조원 정밀 조회", list(fresh_team["stocks"].keys()))
                if selected_stock_user:
                    user_history = fresh_team["stocks"][selected_stock_user]
                    chart_df = pd.DataFrame({"기여도 가치 추이 (P)": user_history})
                    st.line_chart(chart_df)
        show_stocks_live()

    # --- 탭 4: 달력 일정 관리 ---
    with tab_mapping["📅 달력 일정 관리"]:
        st.subheader("📅 우리 팀 업무 결재선 타임라인")
        
        start_date_val = team_data.get("start_date", str(datetime.today().date()))
        end_date_val = team_data.get("end_date", str(datetime.today().date()))
        if isinstance(start_date_val, str): start_date_val = datetime.strptime(start_date_val, "%Y-%m-%d").date()
        if isinstance(end_date_val, str): end_date_val = datetime.strptime(end_date_val, "%Y-%m-%d").date()
        
        date_list = [start_date_val + timedelta(days=i) for i in range((end_date_val - start_date_val).days + 1)]
        date_strs = [str(d) for d in date_list]
        
        if is_leader:
            col_reg1, col_reg2, col_reg3 = st.columns([2, 2, 4])
            with col_reg1: selected_date_str = st.selectbox("날짜 지정", date_strs, key="sel_date")
            with col_reg2: worker_input = st.selectbox("책임 담당자 지정", m_names if m_names else ["없음"], key="sel_worker")
            with col_reg3: event_input = st.text_input("상세 과업 임무 내용 기입", key="sel_content")
                
            if st.button("➕ 새로운 업무 분배 배치"):
                if event_input.strip():
                    if selected_date_str not in team_data.setdefault("calendar_events", {}):
                        team_data["calendar_events"][selected_date_str] = []
                    
                    team_data["calendar_events"][selected_date_str].append({
                        "id": len(team_data["calendar_events"][selected_date_str]),
                        "content": event_input.strip(), "status": "⏳", "worker": worker_input
                    })
                    save_all_data(master_db)
                    st.success("배치 성공")
                    st.rerun()
        
        st.write("---")
        
        @st.fragment(run_every=3)
        def show_calendar_live():
            fresh_db = load_all_data()
            fresh_team = fresh_db["teams_master"].get(st.session_state.current_team_id, team_data)
            
            for d_str in date_strs:
                day_events = fresh_team.get("calendar_events", {}).get(d_str, [])
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
                        c_w.write(f"👤 {ev.get('worker', '미지정')}")
                        c_c.write(ev.get('content', '내용 없음'))
                        
                        status_str = ev.get("status", "⏳")
                        c_s.write("✔️ 결재승인" if "✔️" in status_str else "❌ 이행반려" if "❌" in status_str else "⏳ 검토대기")
                        
                        if is_leader:
                            with c_ops:
                                b1, b2, b3 = st.columns(3)
                                with b1:
                                    if st.button("✔️", key=f"v_{d_str}_{idx}_{ev.get('id', idx)}"):
                                        master_db["teams_master"][st.session_state.current_team_id]["calendar_events"][d_str][idx]["status"] = "✔️"
                                        tw = ev["worker"]
                                        if tw in master_db["teams_master"][st.session_state.current_team_id].setdefault("stocks", {}):
                                            master_db["teams_master"][st.session_state.current_team_id]["stocks"][tw].append(master_db["teams_master"][st.session_state.current_team_id]["stocks"][tw][-1] + 3000)
                                            master_db["teams_master"][st.session_state.current_team_id].setdefault("stock_logs", {}).setdefault(tw, []).append({"type": "plus", "val": 3000, "reason": f"{d_str} 결재성공"})
                                        save_all_data(master_db)
                                        st.rerun()
                                with b2:
                                    if st.button("❌", key=f"x_{d_str}_{idx}_{ev.get('id', idx)}"):
                                        master_db["teams_master"][st.session_state.current_team_id]["calendar_events"][d_str][idx]["status"] = "❌"
                                        tw = ev["worker"]
                                        if tw in master_db["teams_master"][st.session_state.current_team_id].setdefault("stocks", {}):
                                            master_db["teams_master"][st.session_state.current_team_id]["stocks"][tw].append(max(1000, master_db["teams_master"][st.session_state.current_team_id]["stocks"][tw][-1] - 3000))
                                            master_db["teams_master"][st.session_state.current_team_id].setdefault("stock_logs", {}).setdefault(tw, []).append({"type": "minus", "val": 3000, "reason": f"{d_str} 태만반려"})
                                        save_all_data(master_db)
                                        st.rerun()
                                with b3:
                                    if st.button("🗑️", key=f"del_{d_str}_{idx}_{ev.get('id', idx)}"):
                                        master_db["teams_master"][st.session_state.current_team_id]["calendar_events"][d_str].pop(idx)
                                        save_all_data(master_db)
                                        st.rerun()
                        else:
                            c_ops.write("🔒 변경불가")
        show_calendar_live()

    # --- 탭 5: 조원 정보 수정창 ---
    if is_leader:
        with tab_mapping["👥 조원 정보 수정창"]:
            st.subheader("👥 조원 명부 및 워크스페이스 관리실")
            
            st.markdown("#### 🔗 우리 조 고유 초대 링크 복사 및 공유")
            host = st.context.headers.get("Host", "localhost:8501")
            protocol = "https" if "localhost" not in host else "http"
            current_invite_link = f"{protocol}://{host}/?invite=true&team_id={st.session_state.current_team_id}"
            
            st.info(current_invite_link)
            st.caption("💡 위 주소를 복사하여 조원들에게 전달하면, 조원들이 언제든지 이 프로젝트 공간으로 재접속해 들어올 수 있습니다.")
            st.write("---")
            
            st.markdown("#### ⚙️ 팀 메타데이터 설정")
            edit_team_name = st.text_input("조 이름 변경", value=team_data.get("team_name", ""))
            edit_subject = st.text_input("프로젝트 주제 변경", value=team_data.get("subject", ""))
            if st.button("핵심 메타데이터 수정 동기화"):
                team_data["team_name"] = edit_team_name
                team_data["subject"] = edit_subject
                save_all_data(master_db)
                st.success("정보가 변경되었습니다.")
                st.rerun()
                
            st.write("---")
            updated_members = []
            name_changes = {}
            
            for i in range(len(team_data.get("members", []))):
                is_leader_mark = " (👑 조장)" if i == team_data.get("leader_idx", 0) else ""
                st.markdown(f"#### 👤 조원 {i+1}{is_leader_mark} 정보 수정")
                
                old_name = team_data["members"][i]["이름"]
                new_name = st.text_input(f"성명", value=old_name, key=f"fixed_n_{i}").strip()
                fixed_p = st.text_input(f"연락처", value=team_data["members"][i]["연락처"], key=f"fixed_p_{i}")
                fixed_r = st.text_input(f"역할군", value=team_data["members"][i]["역할"], key=f"fixed_r_{i}")
                
                updated_members.append({"이름": new_name, "연락처": fixed_p, "역할": fixed_r})
                
                if old_name and new_name and old_name != new_name:
                    name_changes[old_name] = new_name
                        
            if st.button("👥 수정된 원장 명부 최종 인덱싱 배포"):
                for old_n, new_n in name_changes.items():
                    if old_n in team_data.get("stocks", {}):
                        team_data["stocks"][new_n] = team_data["stocks"].pop(old_n)
                    if old_n in team_data.get("stock_logs", {}):
                        team_data["stock_logs"][new_n] = team_data["stock_logs"].pop(old_n)
                        
                    for room in team_data.get("chat_rooms", []):
                        if "members" in room:
                            room["members"] = [new_n if m == old_n else m for m in room["members"]]
                            
                    for chat in team_data.get("chats_archive", []):
                        if chat.get("sender") == old_n:
                            chat["sender"] = new_n
                            
                    for date_key, events in team_data.get("calendar_events", {}).items():
                        for ev in events:
                            if ev.get("worker") == old_n:
                                ev["worker"] = new_n
                                
                    for story in team_data.get("stories", []):
                        if story.get("user") == old_n:
                            story["user"] = new_n
                        for comment in story.get("comments", []):
                            if comment.get("writer") == old_n:
                                comment["writer"] = new_n

                    if st.session_state.current_user == old_n:
                        st.session_state.current_user = new_n

                team_data["members"] = updated_members
                for m in team_data["members"]:
                    if m["이름"] and m["이름"] not in team_data.setdefault("stocks", {}):
                        team_data["stocks"][m["이름"]] = [10000]
                        team_data["stock_logs"][m["이름"]] = []
                save_all_data(master_db)
                st.success("🎉 성명 변경 사항이 성공적으로 통합 반영되었습니다!")
                st.rerun()

    # --- 탭 6: 카톡형 커스텀 메신저 ---
    with tab_mapping["💬 멀티 카톡방 메신저"]:
        st.subheader("💬 우리 조 전용 실시간 커스텀 채팅방 포털")
        
        all_associates = list(m_names)
        if leader_name not in all_associates and leader_name != "미정": 
            all_associates.append(leader_name)
        all_associates = [p for p in all_associates if p.strip() != ""]
        
        if "chat_rooms" not in team_data: team_data["chat_rooms"] = []
        if "chats_archive" not in team_data: team_data["chats_archive"] = []
        
        with st.expander("➕ 새로운 단체/1:1 채팅방 개설하기", expanded=False):
            st.markdown("**방에 참가할 인원을 선택해 주세요 (나 포함 여러 명 선택 가능)**")
            choose_members = st.multiselect("채팅방 멤버 구성", all_associates, default=[my_chat_name])
            custom_room_title = st.text_input("채팅방 이름 설정", placeholder="예: 개발 파트 단톡방, 1대1 비밀방 등 (공백 시 멤버 이름 자동 지정)")
            
            if st.button("🚀 선택한 멤버로 채팅방 개설하기"):
                if len(choose_members) < 1:
                    st.error("최소 1명 이상의 멤버를 지정해야 합니다.")
                else:
                    if my_chat_name not in choose_members:
                        choose_members.append(my_chat_name)
                    choose_members = list(set(choose_members))
                    
                    if not custom_room_title.strip():
                        custom_room_title = ", ".join([p for p in choose_members if p != my_chat_name]) + " 님과의 채팅방" if len(choose_members) > 1 else "나와의 메모장"
                        
                    new_room_id = str(uuid.uuid4())
                    
                    m_db = load_all_data()
                    m_db["teams_master"][st.session_state.current_team_id].setdefault("chat_rooms", []).append({
                        "room_id": new_room_id,
                        "title": custom_room_title,
                        "members": choose_members
                    })
                    save_all_data(m_db)
                    st.session_state.active_chat_room_id = new_room_id
                    st.success(f"🎉 '{custom_room_title}'이 생성되었습니다!")
                    st.rerun()
                    
        st.write("---")
        
        @st.fragment(run_every=3)
        def show_entire_chat_system_live():
            fresh_db = load_all_data()
            fresh_team = fresh_db["teams_master"].get(st.session_state.current_team_id, {"chat_rooms": [], "chats_archive": []})
            
            col_rooms, col_chat_window = st.columns([1, 2])
            my_accessible_rooms = [r for r in fresh_team.get("chat_rooms", []) if my_chat_name in r.get("members", [])]
            
            with col_rooms:
                st.write("📥 **내 참여 채팅방 리스트 (2초 자동동기화)**")
                if not my_accessible_rooms:
                    st.caption("참여 중인 채팅방이 없습니다.")
                else:
                    for rm in my_accessible_rooms:
                        is_active = (st.session_state.active_chat_room_id == rm["room_id"])
                        label = f"💬 {rm['title']} ({len(rm['members'])}명)" + (" (열림)" if is_active else "")
                        
                        if st.button(label, key=f"room_tab_{rm['room_id']}", use_container_width=True):
                            st.session_state.active_chat_room_id = rm["room_id"]
                            st.rerun()
                            
            with col_chat_window:
                active_id = st.session_state.active_chat_room_id
                target_room = next((r for r in my_accessible_rooms if r["room_id"] == active_id), None)
                
                if target_room is None:
                    st.info("👈 왼쪽 참여방 목록에서 대화하고 싶은 채팅방을 선택해 주세요!")
                else:
                    c_title, c_exit = st.columns([3, 1])
                    with c_title:
                        st.markdown(f"### 💬 **{target_room['title']}**")
                        st.caption(f"👥 참여 멤버: {', '.join(target_room['members'])}")
                    
                    with c_exit:
                        if st.button("🚪 이 방 나가기", key=f"exit_room_{target_room['room_id']}", use_container_width=True):
                            db_write = load_all_data()
                            target_team_db = db_write["teams_master"][st.session_state.current_team_id]
                            
                            for origin_room in target_team_db.get("chat_rooms", []):
                                if origin_room["room_id"] == target_room["room_id"]:
                                    if my_chat_name in origin_room["members"]:
                                        origin_room["members"].remove(my_chat_name)
                                    break
                                    
                            save_all_data(db_write)
                            st.session_state.active_chat_room_id = None
                            st.toast("채팅방에서 퇴장하여 대화 내용 수신이 해제되었습니다.")
                            st.rerun()
                    
                    msg_box = st.container(height=320)
                    with msg_box:
                        for chat in fresh_team.get("chats_archive", []):
                            if chat.get("room_id") == target_room["room_id"]:
                                is_me = (chat["sender"] == my_chat_name)
                                if is_me:
                                    st.markdown(f"<div style='text-align: right; margin-bottom: 8px;'><span style='background-color: #ffe600; color: black; padding: 6px 12px; border-radius: 12px; display: inline-block; max-width: 70%; text-align: left;'><b>내가 보냄</b><br>{chat['msg']} <small style='color: gray; font-size:10px;'>{chat['time']}</small></span></div>", unsafe_allow_html=True)
                                else:
                                    st.markdown(f"<div style='text-align: left; margin-bottom: 8px;'><span style='background-color: #f1f1f1; color: black; padding: 6px 12px; border-radius: 12px; display: inline-block; max-width: 70%;'><b>{chat['sender']}</b><br>{chat['msg']} <small style='color: gray; font-size:10px;'>{chat['time']}</small></span></div>", unsafe_allow_html=True)
                    
                    with st.form(f"msg_send_form_{target_room['room_id']}", clear_on_submit=True):
                        text_input = st.text_input("메시지 입력", placeholder="대화를 입력해 보세요.", key=f"chat_text_in_{target_room['room_id']}")
                        if st.form_submit_button("🚀 전송") and text_input.strip():
                            m_db = load_all_data()
                            m_db["teams_master"][st.session_state.current_team_id].setdefault("chats_archive", []).append({
                                "room_id": target_room["room_id"],
                                "sender": my_chat_name,
                                "msg": text_input.strip(),
                                "time": datetime.now().strftime("%H:%M")
                            })
                            save_all_data(m_db)
                            st.rerun()

        show_entire_chat_system_live()

    # --- [🚨 신규 핵심 연동] 탭 7: 사용자용 관리자 SOS 고객센터 ---
    with tab_mapping["🚨 관리자 SOS 고객센터"]:
        st.subheader("🚨 시스템 마스터 버그 제보 및 1:1 SOS 소통 창구")
        st.markdown("프로젝트 앱 사용 도중 버그, 데이터 오류, 먹통 현상이 발생하면 **상세 내용과 함께 스크린샷 화면**을 첨부해 마스터 관리자에게 즉시 원격 제보할 수 있습니다.")
        
        col_sos1, col_sos2 = st.columns([2, 3])
        
        with col_sos1:
            st.markdown("#### 🛠️ 버그 및 문의 접수")
            with st.form("bug_report_user_form", clear_on_submit=True):
                bug_content = st.text_area("버그 현상 및 요청사항 상세 기입", placeholder="어떤 메뉴에서 어떤 에러가 나는지 적어주시면 빠르게 복구됩니다.")
                bug_img = st.file_uploader("오류 캡처 이미지 업로드 (선택)", type=["png", "jpg", "jpeg"])
                
                if st.form_submit_button("🚨 마스터 관제탑으로 SOS 긴급 전송"):
                    if bug_content.strip():
                        img_bytes = None
                        img_name = "없음"
                        if bug_img is not None:
                            img_bytes = bug_img.read()
                            img_name = bug_img.name
                            
                        m_db = load_all_data()
                        m_db["admin_master"].setdefault("bug_reports", []).append({
                            "report_id": str(uuid.uuid4()),
                            "team_id": st.session_state.current_team_id,
                            "team_name": team_data.get('team_name', '우리팀'),
                            "sender": my_chat_name,
                            "content": bug_content.strip(),
                            "image_bytes": img_bytes,
                            "image_name": img_name,
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "reply": None,
                            "status": "⏳ 대기중"
                        })
                        save_all_data(m_db)
                        st.success("🎉 관리자 앱으로 SOS 버그 제보가 실시간 접수되었습니다!")
                        st.rerun()
                        
        with col_sos2:
            st.markdown("#### 📬 내 제보 건 실시간 처리 및 관리자 답변 현황")
            
            @st.fragment(run_every=3)
            def show_my_sos_status_live():
                fresh_db = load_all_data()
                all_reports = fresh_db["admin_master"].get("bug_reports", [])
                # 내 팀의 제보만 필터링
                my_team_reports = [r for r in all_reports if r["team_id"] == st.session_state.current_team_id]
                
                if not my_team_reports:
                    st.caption("아직 접수하신 문의 내역이 없습니다.")
                else:
                    for my_rep in reversed(my_team_reports):
                        with st.container(border=True):
                            badge = "🟢 처리 완료" if my_rep["status"] == "✔️ 처리완료" else "⏳ 마스터 검토 중"
                            st.markdown(f"**[{badge}] 문의 일시: {my_rep['time']}**")
                            st.write(f"**내 제보:** {my_rep['content']}")
                            if my_rep.get("reply"):
                                st.info(f"👑 **관리자 오피셜 답변:** {my_rep['reply']}")
                            else:
                                st.caption("💬 관리자의 답변을 실시간 대기하고 있습니다.")
            show_my_sos_status_live()
