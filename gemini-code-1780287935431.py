import streamlit as st
import pandas as pd
import os
import uuid
import json
import base64
from datetime import datetime, timedelta, date as date_type

st.set_page_config(page_title="스타트리 (Startree)", page_icon="🌳", layout="wide")

# =============================================
# [Supabase 연결]
# .streamlit/secrets.toml 설정:
# [supabase]
# url = "https://xxxxxx.supabase.co"
# key = "your-anon-key"
# [admin]
# id = "admin"
# pw = "your-admin-password"
# =============================================

@st.cache_resource
def get_supabase_client():
    from supabase import create_client, Client
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

supabase = get_supabase_client()

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

# =============================================
# [DB 핵심 수정] TTL 캐시로 폭발적 쿼리 방지
# 6초 캐시 → fragment run_every=6과 맞춤
# =============================================
@st.cache_data(ttl=5)
def load_all_data():
    try:
        res = supabase.table("startree_db").select("data").eq("id", "main").execute()
        if res.data and len(res.data) > 0:
            db = res.data[0]["data"]
            if "admin_master" not in db:
                db["admin_master"] = DEFAULT_DB["admin_master"].copy()
            if "users_master" not in db:
                db["users_master"] = {}
            if "teams_master" not in db:
                db["teams_master"] = {}
            return db
        else:
            supabase.table("startree_db").insert({"id": "main", "data": DEFAULT_DB}).execute()
            return DEFAULT_DB.copy()
    except Exception as e:
        st.error(f"DB 연결 오류: {e}")
        return DEFAULT_DB.copy()

def save_all_data(master_db):
    try:
        supabase.table("startree_db").upsert({"id": "main", "data": master_db}).execute()
        # 저장 후 캐시 즉시 무효화 → 다음 로드 때 최신 데이터 반영
        load_all_data.clear()
    except Exception as e:
        st.error(f"DB 저장 오류: {e}")

# =============================================
# [세션 초기화]
# =============================================
_defaults = {
    "current_team_id": None,
    "current_user": None,
    "user_role": "leader",
    "step": "auth_login",
    "active_chat_room_id": None,
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# 초대 링크 처리
qp = st.query_params
if "invite" in qp and "team_id" in qp:
    _db = load_all_data()
    target_team = qp["team_id"]
    if target_team in _db["teams_master"]:
        if st.session_state.current_user is None and st.session_state.step not in ("main_home", "admin_dashboard"):
            st.session_state.current_team_id = target_team
            st.session_state.user_role = "member"
            st.session_state.step = "member_auth"

# 현재 팀 데이터 매핑
master_db = load_all_data()
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

# =============================================
# [사이드바]
# =============================================
with st.sidebar:
    st.title("🌳 스타트리")
    if st.button("🔄 새로고침", use_container_width=True):
        load_all_data.clear()
        st.rerun()

    st.write("---")
    if st.session_state.current_user:
        if st.session_state.user_role == "admin":
            st.error(f"👑 마스터 관리자\n\n**{st.session_state.current_user}**")
        else:
            role_label = "👑 조장" if st.session_state.user_role == "leader" else "👤 조원"
            t_name_display = team_data.get("team_name", "설정중") if team_data else "설정중"
            st.success(f"**{t_name_display}**\n\n{st.session_state.current_user} [{role_label}]")

        if st.button("🚪 로그아웃", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.query_params.clear()
            st.rerun()
    else:
        st.info("로그인 후 이용 가능합니다")

    st.write("---")
    st.caption("⚙️ Startree v2.1 · 2026")

# =============================================
# [분기 1] 조원 초대 링크 접속
# =============================================
if st.session_state.step == "member_auth" and team_data:
    st.title("🔗 조원 초대 입장")
    st.subheader(f"🌳 '{team_data.get('team_name', '우리팀')}' 워크스페이스")
    st.markdown(f"**🎯 주제:** {team_data.get('subject', '미정')} | **👑 조장:** {leader_name}")

    if not m_names:
        st.error("❌ 조장님이 아직 조원 명부를 작성하지 않았습니다.")
    else:
        only_members = [n for n in m_names if n != leader_name]
        if not only_members:
            st.warning("현재 조장 외에 등록된 조원이 없습니다.")
            st.stop()

        st.info("💡 명단에서 본인 이름을 선택하여 입장하세요.")
        selected_member = st.selectbox("본인의 이름을 선택하세요", only_members)
        if st.button("🎉 조원 권한으로 입장"):
            st.session_state.current_user = selected_member
            st.session_state.user_role = "member"
            st.session_state.step = "main_home"
            st.rerun()

# =============================================
# [분기 2] 통합 로그인
# =============================================
elif st.session_state.step == "auth_login":
    st.title("🔐 스타트리 로그인")

    col_logo, col_form = st.columns([1, 2])
    with col_logo:
        st.markdown("""
        <div style='text-align:center; padding: 40px 0;'>
            <div style='font-size: 80px;'>🌳</div>
            <h2 style='color:#2e7d32;'>Startree</h2>
            <p style='color:gray;'>팀 프로젝트 통합 관리 플랫폼</p>
        </div>
        """, unsafe_allow_html=True)

    with col_form:
        st.subheader("로그인")
        login_id = st.text_input("아이디(ID)", key="login_id_input").strip()
        login_pw = st.text_input("비밀번호(PW)", type="password", key="login_pw_input").strip()

        col_l1, col_l2 = st.columns(2)
        with col_l1:
            if st.button("로그인", use_container_width=True, type="primary"):
                _db = load_all_data()
                admin_cfg = _db["admin_master"]
                if login_id == admin_cfg["admin_id"] and login_pw == admin_cfg["admin_pw"]:
                    st.session_state.current_user = login_id
                    st.session_state.user_role = "admin"
                    st.session_state.step = "admin_dashboard"
                    st.rerun()
                elif login_id in _db["users_master"] and _db["users_master"][login_id]["pw"] == login_pw:
                    user_info = _db["users_master"][login_id]
                    st.session_state.current_user = login_id
                    st.session_state.user_role = "leader"
                    st.session_state.current_team_id = user_info["team_id"]
                    st.session_state.step = "main_home" if user_info["team_id"] in _db["teams_master"] else "setup_1"
                    st.rerun()
                else:
                    st.error("아이디 또는 비밀번호가 잘못되었습니다.")
        with col_l2:
            if st.button("새 팀 개설 (조장 가입)", use_container_width=True):
                st.session_state.step = "auth_register"
                st.rerun()

        st.write("---")
        with st.expander("🔍 ID / 비밀번호 찾기"):
            find_tab = st.radio("", ["아이디 찾기", "비밀번호 찾기"], horizontal=True, key="find_tab_radio")
            _db = load_all_data()

            if find_tab == "아이디 찾기":
                find_pw = st.text_input("비밀번호", type="password", key="find_pw_input").strip()
                find_team = st.text_input("조 이름", key="find_team_name_id").strip()
                if st.button("아이디 찾기", key="find_id_btn"):
                    found = None
                    for uid, uinfo in _db["users_master"].items():
                        if uinfo["pw"] == find_pw:
                            t_info = _db["teams_master"].get(uinfo["team_id"], {})
                            if t_info.get("team_name", "").strip() == find_team:
                                found = uid
                                break
                    st.success(f"✅ 아이디: **{found}**") if found else st.error("일치하는 계정이 없습니다.")
            else:
                find_id = st.text_input("아이디", key="find_id_input").strip()
                find_team2 = st.text_input("조 이름", key="find_team_name_pw").strip()
                if st.button("비밀번호 찾기", key="find_pw_btn"):
                    found_pw = None
                    if find_id in _db["users_master"]:
                        uinfo = _db["users_master"][find_id]
                        t_info = _db["teams_master"].get(uinfo["team_id"], {})
                        if t_info.get("team_name", "").strip() == find_team2:
                            found_pw = uinfo["pw"]
                    st.success(f"✅ 비밀번호: **{found_pw}**") if found_pw else st.error("일치하는 계정이 없습니다.")

# =============================================
# [분기 3] 조장 회원가입
# =============================================
elif st.session_state.step == "auth_register":
    st.title("📝 신규 팀 등록")

    if "id_checked" not in st.session_state:
        st.session_state.id_checked = False

    reg_id = st.text_input("조장 ID", key="reg_id_input").strip()
    reg_pw = st.text_input("비밀번호", type="password", key="reg_pw_input").strip()
    reg_pw2 = st.text_input("비밀번호 확인", type="password", key="reg_pw2_input").strip()

    if st.button("아이디 중복 확인"):
        if not reg_id:
            st.warning("아이디를 입력하세요.")
        else:
            _db = load_all_data()
            if reg_id in _db["users_master"] or reg_id == _db["admin_master"]["admin_id"]:
                st.error("❌ 이미 사용 중인 아이디입니다.")
                st.session_state.id_checked = False
            else:
                st.success("✅ 사용 가능한 아이디입니다.")
                st.session_state.id_checked = True

    col_r1, col_r2 = st.columns(2)
    with col_r1:
        if st.button("팀 개설 완료", use_container_width=True, type="primary"):
            if not st.session_state.id_checked:
                st.error("아이디 중복 확인이 필요합니다.")
            elif not reg_pw:
                st.error("비밀번호를 입력하세요.")
            elif reg_pw != reg_pw2:
                st.error("비밀번호가 일치하지 않습니다.")
            else:
                new_team_id = str(uuid.uuid4())
                _db = load_all_data()
                _db["users_master"][reg_id] = {"pw": reg_pw, "team_id": new_team_id}
                save_all_data(_db)
                st.session_state.id_checked = False
                st.session_state.step = "auth_login"
                st.success("팀 개설 완료! 로그인해 주세요.")
                st.rerun()
    with col_r2:
        if st.button("← 로그인으로 돌아가기", use_container_width=True):
            st.session_state.step = "auth_login"
            st.rerun()

# =============================================
# [분기 4] 팀 초기 설정 마법사
# =============================================
elif st.session_state.step == "setup_1":
    st.title("🚀 팀 초기 설정")
    st.subheader("1단계: 팀 총원 지정")
    count = st.number_input("인원 수 (명)", min_value=1, max_value=20, value=3)
    if st.button("다음 →", type="primary"):
        _db = load_all_data()
        _db["teams_master"][st.session_state.current_team_id] = {
            "member_count": count,
            "members": [{"이름": "", "연락처": "", "역할": ""} for _ in range(count)],
            "leader_idx": 0, "team_name": "", "subject": "",
            "start_date": str(datetime.today().date()),
            "end_date": str((datetime.today() + timedelta(days=7)).date()),
            "calendar_events": {}, "notices": [], "chat_rooms": [],
            "chats_archive": [], "stories": [], "stocks": {}, "stock_logs": {}
        }
        save_all_data(_db)
        st.session_state.step = "setup_2"
        st.rerun()

elif st.session_state.step == "setup_2":
    st.title("🚀 팀 초기 설정")
    st.subheader("2단계: 팀원 명부 작성")
    _db = load_all_data()
    current_team = _db["teams_master"][st.session_state.current_team_id]
    member_names = []

    for i in range(current_team["member_count"]):
        st.markdown(f"**👤 조원 {i+1}**")
        col1, col2, col3 = st.columns(3)
        with col1:
            n = st.text_input("이름", value=current_team["members"][i].get("이름",""), key=f"s2_n_{i}")
        with col2:
            p = st.text_input("연락처", value=current_team["members"][i].get("연락처",""), key=f"s2_p_{i}")
        with col3:
            r = st.text_input("역할", value=current_team["members"][i].get("역할",""), key=f"s2_r_{i}")
        current_team["members"][i] = {"이름": n, "연락처": p, "역할": r}
        member_names.append(n if n else f"조원 {i+1}")

    leader_select = st.selectbox("👑 조장 지정", range(current_team["member_count"]),
                                  format_func=lambda x: member_names[x])
    current_team["leader_idx"] = leader_select

    if st.button("다음 →", type="primary"):
        save_all_data(_db)
        st.session_state.step = "setup_3"
        st.rerun()

elif st.session_state.step == "setup_3":
    st.title("🚀 팀 초기 설정")
    st.subheader("3단계: 팀 기본 정보 입력")
    _db = load_all_data()
    current_team = _db["teams_master"][st.session_state.current_team_id]

    team_name_in = st.text_input("팀(조) 이름", placeholder="예: 1조, 스파크팀")
    subject_in = st.text_input("프로젝트 주제")
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        start_d = st.date_input("프로젝트 시작일", value=datetime.today().date())
    with col_d2:
        end_d = st.date_input("프로젝트 마감일", value=(datetime.today() + timedelta(days=7)).date())

    if st.button("다음 →", type="primary"):
        current_team["team_name"] = team_name_in.strip() or "우리팀"
        current_team["subject"] = subject_in.strip()
        current_team["start_date"] = str(start_d)
        current_team["end_date"] = str(end_d)
        save_all_data(_db)
        st.session_state.step = "setup_4"
        st.rerun()

elif st.session_state.step == "setup_4":
    st.title("🚀 팀 초기 설정")
    st.subheader("4단계: 주식(기여도) 시스템 초기화")
    _db = load_all_data()
    current_team = _db["teams_master"][st.session_state.current_team_id]

    st.info("각 조원의 초기 기여도 주식 수량을 지정합니다. 기본값: 10,000P")
    stocks = {}
    stock_logs = {}
    for m in current_team["members"]:
        if m["이름"]:
            init_val = st.number_input(f"{m['이름']} 초기값 (P)", min_value=1000, max_value=100000, value=10000, step=1000, key=f"stock_init_{m['이름']}")
            stocks[m["이름"]] = [init_val]
            stock_logs[m["이름"]] = []

    if st.button("다음 →", type="primary"):
        current_team["stocks"] = stocks
        current_team["stock_logs"] = stock_logs
        save_all_data(_db)
        st.session_state.step = "setup_5"
        st.rerun()

elif st.session_state.step == "setup_5":
    st.title("🚀 팀 초기 설정")
    st.subheader("5단계: 초대 링크 발급 완료!")
    _db = load_all_data()
    t_info = _db["teams_master"].get(st.session_state.current_team_id, {})

    host = st.context.headers.get("Host", "localhost:8501")
    protocol = "https" if "localhost" not in host else "http"
    invite_link = f"{protocol}://{host}/?invite=true&team_id={st.session_state.current_team_id}"

    st.success(f"🎉 **{t_info.get('team_name','팀')}** 워크스페이스가 성공적으로 생성되었습니다!")
    st.markdown("#### 🔗 조원 초대 링크")
    st.info(invite_link)
    st.caption("이 링크를 조원들에게 공유하면 조원들이 이 워크스페이스에 입장할 수 있습니다.")

    if st.button("🌳 워크스페이스 입장", type="primary", use_container_width=True):
        st.session_state.step = "main_home"
        st.rerun()

# =============================================
# [분기 5] 관리자 대시보드 (대폭 강화)
# =============================================
elif st.session_state.step == "admin_dashboard" and st.session_state.user_role == "admin":
    st.title("🌳 스타트리 마스터 관제탑")
    st.markdown(f"**⚡ {datetime.now().strftime('%Y-%m-%d %H:%M')}** | 관리자: **{st.session_state.current_user}**")
    st.write("---")

    admin_tabs = st.tabs([
        "📊 전체 현황",
        "👥 팀 관리",
        "🗂️ 팀 직접 편집",
        "🚨 SOS 수신함",
        "📢 전사 공지",
        "📈 활동 분석",
        "🧹 데이터 관리",
        "⚙️ 보안 설정"
    ])

    # --- 관리자 탭 0: 전체 현황 대시보드 ---
    with admin_tabs[0]:
        st.subheader("📊 플랫폼 전체 현황")

        _db = load_all_data()
        total_teams = len(_db["users_master"])
        total_members = sum(len(v.get("members", [])) for v in _db["teams_master"].values())
        total_bugs = len(_db["admin_master"].get("bug_reports", []))
        pending_bugs = len([r for r in _db["admin_master"].get("bug_reports", []) if r["status"] != "✔️ 처리완료"])
        total_notices = len(_db["admin_master"].get("system_notices", []))
        total_chats = sum(len(v.get("chats_archive", [])) for v in _db["teams_master"].values())
        total_stories = sum(len(v.get("stories", [])) for v in _db["teams_master"].values())
        total_calendar = sum(sum(len(ev) for ev in v.get("calendar_events", {}).values()) for v in _db["teams_master"].values())

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🏢 등록 팀", f"{total_teams}팀")
        c2.metric("👥 전체 조원", f"{total_members}명")
        c3.metric("🚨 미처리 SOS", f"{pending_bugs}건", delta=f"전체 {total_bugs}건", delta_color="inverse")
        c4.metric("💬 전체 채팅", f"{total_chats}건")

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("✨ 스토리", f"{total_stories}건")
        c6.metric("📅 업무 일정", f"{total_calendar}건")
        c7.metric("📢 공지 송출", f"{total_notices}건")
        c8.metric("✅ 처리완료 SOS", f"{total_bugs - pending_bugs}건")

        st.write("---")
        col_left, col_right = st.columns(2)

        with col_left:
            st.markdown("#### 📋 팀별 활동 요약")
            if not _db["users_master"]:
                st.info("등록된 팀이 없습니다.")
            else:
                rows = []
                for l_id, u_info in _db["users_master"].items():
                    t_id = u_info["team_id"]
                    t_info = _db["teams_master"].get(t_id, {})
                    pending_tasks = sum(
                        1 for evs in t_info.get("calendar_events", {}).values()
                        for ev in evs if "⏳" in ev.get("status", "⏳")
                    )
                    rows.append({
                        "조 이름": t_info.get("team_name", "설정중"),
                        "조장 ID": l_id,
                        "조원 수": len(t_info.get("members", [])),
                        "공지": len(t_info.get("notices", [])),
                        "스토리": len(t_info.get("stories", [])),
                        "채팅": len(t_info.get("chats_archive", [])),
                        "미결 업무": pending_tasks,
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True)

        with col_right:
            st.markdown("#### 🚨 미처리 SOS")
            pending_list = [r for r in _db["admin_master"].get("bug_reports", []) if r["status"] != "✔️ 처리완료"]
            if not pending_list:
                st.success("✅ 모든 문의 처리 완료")
            else:
                for rep in reversed(pending_list[-5:]):
                    with st.container(border=True):
                        st.markdown(f"**{rep['team_name']} · {rep['sender']}** | {rep['time']}")
                        st.caption(rep["content"][:80] + ("..." if len(rep["content"]) > 80 else ""))

    # --- 관리자 탭 1: 팀 관리 ---
    with admin_tabs[1]:
        st.subheader("🗂️ 가입 팀 및 조장 계정 원장")

        _db = load_all_data()
        if not _db["users_master"]:
            st.info("등록된 팀이 없습니다.")
        else:
            records = []
            for l_id, u_info in _db["users_master"].items():
                t_id = u_info["team_id"]
                t_info = _db["teams_master"].get(t_id, {})
                records.append({
                    "조장 ID": l_id,
                    "비밀번호": u_info["pw"],
                    "조 이름": t_info.get("team_name", "미완료"),
                    "프로젝트 주제": t_info.get("subject", "-"),
                    "조원 수": len(t_info.get("members", [])),
                    "마감일": t_info.get("end_date", "-"),
                })
            st.dataframe(pd.DataFrame(records), use_container_width=True)

            st.write("---")
            col_pw1, col_pw2 = st.columns(2)
            with col_pw1:
                st.markdown("#### 🔑 비밀번호 강제 변경")
                target_leader = st.selectbox("대상 조장 ID", list(_db["users_master"].keys()), key="pw_reset_select")
                new_pw = st.text_input("새 비밀번호", placeholder="새 비밀번호 입력", key="new_pw_input")
                if st.button("🔒 비밀번호 변경", type="primary"):
                    if new_pw.strip():
                        _db2 = load_all_data()
                        _db2["users_master"][target_leader]["pw"] = new_pw.strip()
                        save_all_data(_db2)
                        st.success(f"✅ [{target_leader}] 비밀번호가 변경되었습니다.")
                        st.rerun()

            with col_pw2:
                st.markdown("#### 🔗 초대 링크 재발급")
                host_val = st.context.headers.get("Host", "localhost:8501")
                protocol_val = "https" if "localhost" not in host_val else "http"
                link_target = st.selectbox("초대링크 생성할 팀 선택", list(_db["users_master"].keys()), key="invite_link_select")
                if link_target:
                    t_id_link = _db["users_master"][link_target]["team_id"]
                    gen_link = f"{protocol_val}://{host_val}/?invite=true&team_id={t_id_link}"
                    st.code(gen_link)
                    st.caption("위 링크를 복사하여 해당 팀 조원들에게 전달하세요.")

    # --- 관리자 탭 2: 팀 직접 편집 ---
    with admin_tabs[2]:
        st.subheader("🗂️ 팀 정보 직접 편집")
        _db = load_all_data()

        if not _db["users_master"]:
            st.info("등록된 팀이 없습니다.")
        else:
            team_options = {}
            for l_id, u_info in _db["users_master"].items():
                t_id = u_info["team_id"]
                t_info = _db["teams_master"].get(t_id, {})
                label = f"{t_info.get('team_name', '설정중')} (조장: {l_id})"
                team_options[label] = t_id

            sel_label = st.selectbox("편집할 팀 선택", list(team_options.keys()))
            edit_t_id = team_options[sel_label]
            edit_team = _db["teams_master"].get(edit_t_id, {})

            if not edit_team:
                st.warning("해당 팀 데이터 없음 (초기 설정 미완료)")
            else:
                st.write("---")
                st.markdown("#### 📝 기본 팀 정보")
                with st.form("admin_edit_team_form"):
                    new_tname = st.text_input("조 이름", value=edit_team.get("team_name", ""))
                    new_subj = st.text_input("프로젝트 주제", value=edit_team.get("subject", ""))
                    try:
                        default_end = date_type.fromisoformat(edit_team.get("end_date", str(date_type.today())))
                    except Exception:
                        default_end = date_type.today()
                    new_end = st.date_input("마감 기한", value=default_end)
                    if st.form_submit_button("💾 저장"):
                        _db2 = load_all_data()
                        _db2["teams_master"][edit_t_id]["team_name"] = new_tname.strip() or edit_team.get("team_name", "우리팀")
                        _db2["teams_master"][edit_t_id]["subject"] = new_subj.strip()
                        _db2["teams_master"][edit_t_id]["end_date"] = str(new_end)
                        save_all_data(_db2)
                        st.success("✅ 저장 완료")
                        st.rerun()

                st.write("---")
                st.markdown("#### 👥 조원 명단 수정")
                members = edit_team.get("members", [])
                if members:
                    with st.form("admin_edit_members_form"):
                        updated = []
                        names_for_leader = []
                        for i, m in enumerate(members):
                            c1, c2, c3 = st.columns(3)
                            with c1: mn = st.text_input("이름", value=m.get("이름",""), key=f"adm_n_{edit_t_id}_{i}")
                            with c2: mc = st.text_input("연락처", value=m.get("연락처",""), key=f"adm_c_{edit_t_id}_{i}")
                            with c3: mr = st.text_input("역할", value=m.get("역할",""), key=f"adm_r_{edit_t_id}_{i}")
                            updated.append({"이름": mn, "연락처": mc, "역할": mr})
                            names_for_leader.append(mn or f"조원 {i+1}")
                        cur_li = edit_team.get("leader_idx", 0)
                        new_li = st.selectbox("👑 조장", range(len(updated)),
                                              index=min(cur_li, len(updated)-1),
                                              format_func=lambda x: names_for_leader[x])
                        if st.form_submit_button("💾 명단 저장"):
                            _db2 = load_all_data()
                            _db2["teams_master"][edit_t_id]["members"] = updated
                            _db2["teams_master"][edit_t_id]["leader_idx"] = new_li
                            save_all_data(_db2)
                            st.success("✅ 명단 저장 완료")
                            st.rerun()

    # --- 관리자 탭 3: SOS 수신함 ---
    with admin_tabs[3]:
        st.subheader("📥 SOS 버그 제보 수신함")

        @st.fragment(run_every=8)
        def show_admin_sos():
            fresh = load_all_data()
            reports = fresh["admin_master"].get("bug_reports", [])

            if not reports:
                st.info("✅ 접수된 문의가 없습니다.")
                return

            # 필터
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                filter_status = st.selectbox("상태 필터", ["전체", "대기중", "처리완료"], key="sos_filter")
            with col_f2:
                filter_team = st.selectbox("팀 필터", ["전체"] + list(set(r["team_name"] for r in reports)), key="sos_team_filter")

            filtered = reports
            if filter_status == "대기중":
                filtered = [r for r in filtered if r["status"] != "✔️ 처리완료"]
            elif filter_status == "처리완료":
                filtered = [r for r in filtered if r["status"] == "✔️ 처리완료"]
            if filter_team != "전체":
                filtered = [r for r in filtered if r["team_name"] == filter_team]

            st.caption(f"총 {len(filtered)}건 표시 중")

            for idx, rep in enumerate(reversed(filtered)):
                true_idx = reports.index(rep)
                with st.container(border=True):
                    col_r1, col_r2 = st.columns([3, 1])
                    with col_r1:
                        badge = "🟢 완료" if rep["status"] == "✔️ 처리완료" else "⏳ 대기"
                        st.markdown(f"### [{badge}] {rep['team_name']} · {rep['sender']}")
                        st.caption(f"📅 {rep['time']}")
                        st.warning(f"💬 {rep['content']}")
                    with col_r2:
                        if rep.get("image_bytes"):
                            img_data = base64.b64decode(rep["image_bytes"]) if isinstance(rep["image_bytes"], str) else rep["image_bytes"]
                            st.image(img_data, use_container_width=True)
                        else:
                            st.caption("첨부 없음")

                    if rep.get("reply"):
                        st.info(f"👑 답변: {rep['reply']}")

                    with st.form(f"sos_reply_{rep['report_id']}", clear_on_submit=True):
                        reply_text = st.text_input("답변 작성", key=f"sos_rep_{rep['report_id']}")
                        c_b1, c_b2 = st.columns(2)
                        with c_b1:
                            if st.form_submit_button("🚀 답변 전송"):
                                _db2 = load_all_data()
                                _db2["admin_master"]["bug_reports"][true_idx]["reply"] = reply_text.strip()
                                _db2["admin_master"]["bug_reports"][true_idx]["status"] = "✔️ 처리완료"
                                save_all_data(_db2)
                                st.rerun()
                        with c_b2:
                            if st.form_submit_button("🗑️ 삭제"):
                                _db2 = load_all_data()
                                _db2["admin_master"]["bug_reports"].pop(true_idx)
                                save_all_data(_db2)
                                st.rerun()

        show_admin_sos()

    # --- 관리자 탭 4: 전사 공지 ---
    with admin_tabs[4]:
        st.subheader("📢 전사 공지 송출")
        st.caption("이곳에서 작성한 공지는 모든 팀 대시보드 최상단에 즉시 표시됩니다.")

        with st.form("sys_notice_form", clear_on_submit=True):
            sys_msg = st.text_area("공지 내용", placeholder="예: 오늘 오후 2시 서버 점검 예정입니다.")
            notice_type = st.radio("공지 유형", ["🚨 긴급", "📢 일반", "✅ 완료"], horizontal=True)
            if st.form_submit_button("📢 전체 공지 송출", type="primary"):
                if sys_msg.strip():
                    _db2 = load_all_data()
                    _db2["admin_master"].setdefault("system_notices", []).insert(0, {
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "msg": sys_msg.strip(),
                        "type": notice_type
                    })
                    save_all_data(_db2)
                    st.success("✅ 공지가 전체 배포되었습니다!")
                    st.rerun()

        st.write("---")
        st.markdown("#### 📜 송출 중인 공지 목록")
        _db = load_all_data()
        for idx, sn in enumerate(_db["admin_master"].get("system_notices", [])):
            with st.container(border=True):
                col_n1, col_n2 = st.columns([4, 1])
                with col_n1:
                    st.caption(f"📅 {sn['time']} | {sn.get('type', '📢 일반')}")
                    st.write(sn["msg"])
                with col_n2:
                    if st.button("🗑️ 삭제", key=f"del_sn_{idx}"):
                        _db["admin_master"]["system_notices"].pop(idx)
                        save_all_data(_db)
                        st.rerun()

    # --- 관리자 탭 5: 활동 분석 (신규) ---
    with admin_tabs[5]:
        st.subheader("📈 팀별 활동 분석")
        _db = load_all_data()

        if not _db["users_master"]:
            st.info("등록된 팀이 없습니다.")
        else:
            analysis_options = {}
            for l_id, u_info in _db["users_master"].items():
                t_id = u_info["team_id"]
                t_info = _db["teams_master"].get(t_id, {})
                label = f"{t_info.get('team_name', '설정중')} (조장: {l_id})"
                analysis_options[label] = t_id

            sel_analysis = st.selectbox("분석할 팀 선택", list(analysis_options.keys()), key="analysis_team_sel")
            a_t_id = analysis_options[sel_analysis]
            a_team = _db["teams_master"].get(a_t_id, {})

            if a_team:
                st.write("---")
                col_a1, col_a2 = st.columns(2)

                with col_a1:
                    st.markdown("#### 📊 조원별 기여도 현황")
                    stocks = a_team.get("stocks", {})
                    if stocks:
                        stock_data = {name: vals[-1] for name, vals in stocks.items() if vals}
                        stock_df = pd.DataFrame(list(stock_data.items()), columns=["조원", "기여도(P)"])
                        stock_df = stock_df.sort_values("기여도(P)", ascending=False)
                        st.dataframe(stock_df, use_container_width=True)
                        st.bar_chart(stock_df.set_index("조원"))
                    else:
                        st.caption("기여도 데이터 없음")

                with col_a2:
                    st.markdown("#### 📅 업무 현황")
                    all_tasks = []
                    for d, evs in a_team.get("calendar_events", {}).items():
                        for ev in evs:
                            all_tasks.append({
                                "날짜": d,
                                "담당자": ev.get("worker", "-"),
                                "내용": ev.get("content", "")[:30],
                                "상태": "✔️ 완료" if "✔️" in ev.get("status","") else "❌ 반려" if "❌" in ev.get("status","") else "⏳ 대기"
                            })
                    if all_tasks:
                        task_df = pd.DataFrame(all_tasks)
                        status_counts = task_df["상태"].value_counts()
                        st.dataframe(task_df, use_container_width=True)
                        st.write("**업무 상태 분포:**")
                        st.bar_chart(status_counts)
                    else:
                        st.caption("등록된 업무 없음")

                st.write("---")
                st.markdown("#### 💬 채팅 활동 분석")
                chats = a_team.get("chats_archive", [])
                if chats:
                    sender_counts = {}
                    for c in chats:
                        s = c.get("sender", "?")
                        sender_counts[s] = sender_counts.get(s, 0) + 1
                    chat_df = pd.DataFrame(list(sender_counts.items()), columns=["조원", "메시지 수"])
                    st.bar_chart(chat_df.set_index("조원"))
                else:
                    st.caption("채팅 데이터 없음")

                st.write("---")
                st.markdown("#### 📬 팀 전용 관리자 메시지 발송 (신규)")
                with st.form(f"admin_team_msg_{a_t_id}", clear_on_submit=True):
                    admin_msg_content = st.text_area("해당 팀에게 보낼 공지/메시지", placeholder="팀 전용 메시지를 입력하세요")
                    if st.form_submit_button("📨 팀 전용 공지 발송"):
                        if admin_msg_content.strip():
                            _db2 = load_all_data()
                            _db2["teams_master"][a_t_id].setdefault("notices", []).insert(0, {
                                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "content": f"[📢 관리자 메시지] {admin_msg_content.strip()}",
                                "file_name": "없음",
                                "file_bytes": None
                            })
                            save_all_data(_db2)
                            st.success("✅ 해당 팀 공지사항에 메시지가 전달되었습니다.")
                            st.rerun()

    # --- 관리자 탭 6: 데이터 관리 ---
    with admin_tabs[6]:
        st.subheader("🧹 팀 데이터 관리")
        _db = load_all_data()

        if not _db["users_master"]:
            st.info("등록된 팀이 없습니다.")
        else:
            mgmt_opts = {}
            for l_id, u_info in _db["users_master"].items():
                t_id = u_info["team_id"]
                t_info = _db["teams_master"].get(t_id, {})
                mgmt_opts[f"{t_info.get('team_name', '설정중')} (조장: {l_id})"] = (l_id, t_id)

            sel_mgmt = st.selectbox("관리 대상 팀", list(mgmt_opts.keys()), key="mgmt_sel")
            mgmt_lid, mgmt_tid = mgmt_opts[sel_mgmt]

            st.write("---")
            col_d1, col_d2 = st.columns(2)

            with col_d1:
                st.markdown("#### 🗑️ 항목별 초기화")
                st.warning("초기화는 복구 불가능합니다.")
                if st.button("💬 채팅 초기화", use_container_width=True):
                    _db2 = load_all_data()
                    _db2["teams_master"][mgmt_tid]["chats_archive"] = []
                    save_all_data(_db2)
                    st.success("✅ 채팅 초기화 완료")
                    st.rerun()
                if st.button("✨ 스토리 초기화", use_container_width=True):
                    _db2 = load_all_data()
                    _db2["teams_master"][mgmt_tid]["stories"] = []
                    save_all_data(_db2)
                    st.success("✅ 스토리 초기화 완료")
                    st.rerun()
                if st.button("📢 팀 공지 초기화", use_container_width=True):
                    _db2 = load_all_data()
                    _db2["teams_master"][mgmt_tid]["notices"] = []
                    save_all_data(_db2)
                    st.success("✅ 공지 초기화 완료")
                    st.rerun()
                if st.button("🚪 채팅방 초기화", use_container_width=True):
                    _db2 = load_all_data()
                    _db2["teams_master"][mgmt_tid]["chat_rooms"] = []
                    _db2["teams_master"][mgmt_tid]["chats_archive"] = []
                    save_all_data(_db2)
                    st.success("✅ 채팅방 초기화 완료")
                    st.rerun()
                if st.button("📅 캘린더 초기화", use_container_width=True):
                    _db2 = load_all_data()
                    _db2["teams_master"][mgmt_tid]["calendar_events"] = {}
                    save_all_data(_db2)
                    st.success("✅ 캘린더 초기화 완료")
                    st.rerun()
                if st.button("📊 기여도 초기화", use_container_width=True):
                    _db2 = load_all_data()
                    t_data = _db2["teams_master"].get(mgmt_tid, {})
                    for m in t_data.get("members", []):
                        if m.get("이름"):
                            t_data["stocks"][m["이름"]] = [10000]
                            t_data["stock_logs"][m["이름"]] = []
                    save_all_data(_db2)
                    st.success("✅ 기여도 초기화 완료")
                    st.rerun()

            with col_d2:
                st.markdown("#### ☣️ 팀 완전 삭제")
                st.error("삭제 시 모든 데이터가 영구 삭제됩니다.")
                confirm_del = st.checkbox(f"'{sel_mgmt}' 삭제에 동의합니다", key="confirm_del_cb")
                if st.button("🗑️ 팀 완전 삭제", use_container_width=True):
                    if confirm_del:
                        _db2 = load_all_data()
                        _db2["users_master"].pop(mgmt_lid, None)
                        _db2["teams_master"].pop(mgmt_tid, None)
                        save_all_data(_db2)
                        st.success("✅ 삭제 완료")
                        st.rerun()
                    else:
                        st.warning("삭제 동의 체크박스를 체크하세요.")

                st.write("---")
                st.markdown("#### 📬 처리완료 SOS 일괄 삭제")
                if st.button("🧹 처리완료 SOS 삭제", use_container_width=True):
                    _db2 = load_all_data()
                    _db2["admin_master"]["bug_reports"] = [
                        r for r in _db2["admin_master"].get("bug_reports", [])
                        if r["status"] != "✔️ 처리완료"
                    ]
                    save_all_data(_db2)
                    st.success("✅ 정리 완료")
                    st.rerun()

    # --- 관리자 탭 7: 보안 설정 ---
    with admin_tabs[7]:
        st.subheader("⚙️ 마스터 계정 설정")
        _db = load_all_data()

        with st.form("admin_profile_form"):
            new_ad_id = st.text_input("새 관리자 ID", value=_db["admin_master"]["admin_id"]).strip()
            new_ad_pw = st.text_input("새 관리자 비밀번호", value=_db["admin_master"]["admin_pw"], type="password").strip()
            if st.form_submit_button("💾 계정 정보 변경"):
                if new_ad_id and new_ad_pw:
                    _db["admin_master"]["admin_id"] = new_ad_id
                    _db["admin_master"]["admin_pw"] = new_ad_pw
                    save_all_data(_db)
                    st.success("✅ 관리자 계정이 변경되었습니다.")
                    st.rerun()

        st.write("---")
        st.error("☣️ 위험 구역 — DB 전체 포맷")
        st.caption("이 버튼을 누르면 모든 팀 데이터가 영구 삭제됩니다.")
        confirm_fmt = st.checkbox("모든 책임을 지며 DB를 전체 포맷하겠습니다.")
        if st.button("⚠️ DB 전체 포맷"):
            if confirm_fmt:
                _db = load_all_data()
                reset_db = {
                    "users_master": {},
                    "teams_master": {},
                    "admin_master": {
                        "admin_id": _db["admin_master"]["admin_id"],
                        "admin_pw": _db["admin_master"]["admin_pw"],
                        "system_notices": [],
                        "bug_reports": []
                    }
                }
                save_all_data(reset_db)
                for k in list(st.session_state.keys()):
                    del st.session_state[k]
                st.query_params.clear()
                st.rerun()
            else:
                st.warning("동의 체크박스를 체크해야 합니다.")

# =============================================
# [분기 6] 메인 워크스페이스
# =============================================
else:
    if not team_data:
        st.error("세션 만료 또는 유효하지 않은 팀 ID입니다.")
        if st.button("로그인으로 돌아가기"):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()
        st.stop()

    current_name = st.session_state.current_user
    is_leader = (st.session_state.user_role == "leader")
    my_chat_name = leader_name if (is_leader and leader_name != "미정") else current_name

    # 전사 긴급 공지 배너 (run_every 주기를 길게 조정)
    @st.fragment(run_every=15)
    def show_system_notice_banner():
        fresh = load_all_data()
        notices = fresh["admin_master"].get("system_notices", [])
        if notices:
            n = notices[0]
            ntype = n.get("type", "📢 일반")
            if "🚨" in ntype:
                st.error(f"📢 **[전사 긴급 공지 - {n['time']}]** {n['msg']}")
            else:
                st.info(f"📢 **[공지 - {n['time']}]** {n['msg']}")

    show_system_notice_banner()

    st.title(f"🌳 {team_data.get('team_name', '우리팀')} 워크스페이스")
    st.markdown(
        f"**🎯 주제:** {team_data.get('subject', '미정')} | "
        f"**👑 조장:** {leader_name} | "
        f"**👤 접속자:** {my_chat_name} ({'조장' if is_leader else '조원'})"
    )

    # D-day 표시
    try:
        end_d = date_type.fromisoformat(team_data.get("end_date", str(date_type.today())))
        dday = (end_d - date_type.today()).days
        if dday > 0:
            st.caption(f"📅 프로젝트 마감까지 **D-{dday}**")
        elif dday == 0:
            st.warning("⚠️ 오늘이 프로젝트 마감일입니다!")
        else:
            st.error(f"⏰ 프로젝트 마감일이 {abs(dday)}일 지났습니다.")
    except Exception:
        pass

    st.write("---")

    tab_titles = ["📢 공지사항", "✨ 스토리 피드", "📊 기여도", "📅 일정 관리", "💬 채팅방", "🚨 SOS 고객센터"]
    if is_leader:
        tab_titles.insert(4, "👥 팀 관리")

    tabs = st.tabs(tab_titles)
    tab_map = {t: tabs[i] for i, t in enumerate(tab_titles)}

    # --- 탭: 공지사항 ---
    with tab_map["📢 공지사항"]:
        st.subheader("📌 팀 공지사항")

        if is_leader:
            with st.form("notice_form", clear_on_submit=True):
                notice_text = st.text_area("새 공지 작성")
                uploaded_file = st.file_uploader("파일 첨부 (선택)")
                if st.form_submit_button("📢 공지 게시", type="primary"):
                    if notice_text.strip():
                        file_name = "없음"
                        file_b64 = None
                        if uploaded_file:
                            file_name = uploaded_file.name
                            file_b64 = base64.b64encode(uploaded_file.read()).decode("utf-8")
                        _db2 = load_all_data()
                        _db2["teams_master"][st.session_state.current_team_id].setdefault("notices", []).insert(0, {
                            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "content": notice_text,
                            "file_name": file_name,
                            "file_bytes": file_b64
                        })
                        save_all_data(_db2)
                        st.success("✅ 공지가 게시되었습니다.")
                        st.rerun()
        else:
            st.caption("공지사항 편집 권한은 조장 전용입니다.")

        st.write("---")

        @st.fragment(run_every=15)
        def show_notices_live():
            fresh = load_all_data()
            fresh_team = fresh["teams_master"].get(st.session_state.current_team_id, {})
            notices = fresh_team.get("notices", [])
            if not notices:
                st.caption("등록된 공지사항이 없습니다.")
            for idx, n in enumerate(notices):
                with st.container(border=True):
                    col_nt, col_nd = st.columns([5, 1])
                    with col_nt:
                        st.caption(f"📅 {n['date']}")
                        st.write(n["content"])
                        if n.get("file_bytes"):
                            file_data = base64.b64decode(n["file_bytes"]) if isinstance(n["file_bytes"], str) else n["file_bytes"]
                            st.download_button(f"📎 {n['file_name']}", data=file_data, file_name=n["file_name"], key=f"notice_dl_{idx}")
                    with col_nd:
                        if is_leader:
                            if st.button("🗑️", key=f"del_notice_{idx}"):
                                _db2 = load_all_data()
                                _db2["teams_master"][st.session_state.current_team_id]["notices"].pop(idx)
                                save_all_data(_db2)
                                st.rerun()

        show_notices_live()

    # --- 탭: 스토리 피드 ---
    with tab_map["✨ 스토리 피드"]:
        st.subheader("📸 팀 스토리 피드")
        col_up, col_view = st.columns([2, 3])

        with col_up:
            with st.form("story_form", clear_on_submit=True):
                st_text = st.text_area("업무 피드 작성")
                st_media = st.file_uploader("미디어 첨부", type=["png", "jpg", "jpeg", "mp4", "mp3", "wav"])
                if st.form_submit_button("📤 피드 게시") and st_text.strip():
                    media_type = None
                    media_data = None
                    if st_media:
                        raw = st_media.read()
                        # 이미지만 base64, 나머지는 크기 제한 안내
                        if st_media.name.lower().endswith((".png", ".jpg", ".jpeg")):
                            media_type = "image"
                            media_data = base64.b64encode(raw).decode("utf-8")
                        elif st_media.name.lower().endswith(".mp4"):
                            media_type = "video"
                            media_data = base64.b64encode(raw).decode("utf-8")
                        elif st_media.name.lower().endswith((".mp3", ".wav")):
                            media_type = "audio"
                            media_data = base64.b64encode(raw).decode("utf-8")
                    _db2 = load_all_data()
                    _db2["teams_master"][st.session_state.current_team_id].setdefault("stories", []).insert(0, {
                        "story_id": str(uuid.uuid4()),
                        "user": my_chat_name,
                        "content": st_text,
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "media_type": media_type,
                        "media_data": media_data,
                        "likes": 0,
                        "liked_by": [],
                        "comments": []
                    })
                    save_all_data(_db2)
                    st.rerun()

        with col_view:
            @st.fragment(run_every=15)
            def show_stories_live():
                fresh = load_all_data()
                fresh_team = fresh["teams_master"].get(st.session_state.current_team_id, {})
                for s in fresh_team.get("stories", []):
                    s_id = s.get("story_id", s.get("time", ""))
                    with st.container(border=True):
                        col_sh, col_sdel = st.columns([5, 1])
                        with col_sh:
                            st.markdown(f"**{s['user']}** · *{s['time']}*")
                        with col_sdel:
                            if is_leader or s.get("user") == my_chat_name:
                                if st.button("🗑️", key=f"del_story_{s_id}"):
                                    _db2 = load_all_data()
                                    _db2["teams_master"][st.session_state.current_team_id]["stories"] = [
                                        x for x in _db2["teams_master"][st.session_state.current_team_id].get("stories", [])
                                        if x.get("story_id") != s_id
                                    ]
                                    save_all_data(_db2)
                                    st.rerun()

                        st.write(s["content"])
                        if s.get("media_type") == "image":
                            st.image(base64.b64decode(s["media_data"]) if isinstance(s["media_data"], str) else s["media_data"], use_container_width=True)
                        elif s.get("media_type") == "video":
                            st.video(base64.b64decode(s["media_data"]) if isinstance(s["media_data"], str) else s["media_data"])
                        elif s.get("media_type") == "audio":
                            st.audio(base64.b64decode(s["media_data"]) if isinstance(s["media_data"], str) else s["media_data"])

                        liked_by = s.get("liked_by", [])
                        already_liked = my_chat_name in liked_by
                        like_label = f"❤️ {s.get('likes', 0)}" + (" (내가 좋아요)" if already_liked else "")
                        if st.button(like_label, key=f"like_{s_id}", disabled=already_liked):
                            _db2 = load_all_data()
                            for os_ in _db2["teams_master"][st.session_state.current_team_id].get("stories", []):
                                if os_.get("story_id") == s_id:
                                    os_["likes"] = os_.get("likes", 0) + 1
                                    os_.setdefault("liked_by", []).append(my_chat_name)
                                    break
                            save_all_data(_db2)
                            st.rerun()

                        for cm in s.get("comments", []):
                            st.markdown(f"💬 **{cm['writer']}**: {cm['text']}")

                        with st.form(f"comment_{s_id}", clear_on_submit=True):
                            c_text = st.text_input("댓글", key=f"cm_{s_id}")
                            if st.form_submit_button("댓글 달기") and c_text.strip():
                                _db2 = load_all_data()
                                for os_ in _db2["teams_master"][st.session_state.current_team_id].get("stories", []):
                                    if os_.get("story_id") == s_id:
                                        os_.setdefault("comments", []).append({"writer": my_chat_name, "text": c_text.strip()})
                                        break
                                save_all_data(_db2)
                                st.rerun()

            show_stories_live()

    # --- 탭: 기여도 ---
    with tab_map["📊 기여도"]:
        st.subheader("📊 기여도 주식 대시보드")

        if is_leader:
            with st.expander("⚙️ 기여도 수동 조정 (조장 전용)"):
                _db = load_all_data()
                cur_stocks = _db["teams_master"].get(st.session_state.current_team_id, {}).get("stocks", {})
                if cur_stocks:
                    adj_target = st.selectbox("조원 선택", list(cur_stocks.keys()), key="adj_stock_target")
                    adj_val = st.number_input("조정값 (양수: 증가, 음수: 감소)", value=1000, step=500, key="adj_stock_val")
                    adj_reason = st.text_input("사유", placeholder="예: 발표 준비 추가 기여", key="adj_reason")
                    if st.button("기여도 조정 적용"):
                        _db2 = load_all_data()
                        t = _db2["teams_master"][st.session_state.current_team_id]
                        cur_val = t["stocks"][adj_target][-1]
                        new_val = max(0, cur_val + adj_val)
                        t["stocks"][adj_target].append(new_val)
                        t.setdefault("stock_logs", {}).setdefault(adj_target, []).append({
                            "type": "plus" if adj_val >= 0 else "minus",
                            "val": abs(adj_val),
                            "reason": adj_reason or "수동 조정"
                        })
                        save_all_data(_db2)
                        st.success(f"✅ {adj_target}: {cur_val:,}P → {new_val:,}P")
                        st.rerun()

        @st.fragment(run_every=15)
        def show_stocks_live():
            fresh = load_all_data()
            fresh_team = fresh["teams_master"].get(st.session_state.current_team_id, {})
            stocks = fresh_team.get("stocks", {})

            if not stocks:
                st.info("기여도 데이터가 없습니다. 팀 설정을 완료해주세요.")
                return

            # 랭킹 표시
            ranked = sorted(stocks.items(), key=lambda x: x[1][-1] if x[1] else 0, reverse=True)
            rank_cols = st.columns(min(len(ranked), 4))
            for i, (name, vals) in enumerate(ranked):
                with rank_cols[i % len(rank_cols)]:
                    cur_val = vals[-1] if vals else 0
                    logs = fresh_team.get("stock_logs", {}).get(name, [])
                    rank_emoji = ["🥇", "🥈", "🥉"] + ["🏅"] * 10
                    with st.container(border=True):
                        st.markdown(f"{rank_emoji[i]} **{name}**")
                        st.metric("기여도", f"{cur_val:,}P",
                                  delta=f"{'+' if logs and logs[-1]['type']=='plus' else '-'}{logs[-1]['val']:,}P" if logs else None)

            st.write("---")
            sel_user = st.selectbox("추이 조회", list(stocks.keys()), key="stock_detail_sel")
            if sel_user and stocks.get(sel_user):
                chart_df = pd.DataFrame({"기여도(P)": stocks[sel_user]})
                st.line_chart(chart_df)

                logs = fresh_team.get("stock_logs", {}).get(sel_user, [])
                if logs:
                    st.markdown("**최근 변동 이력**")
                    log_df = pd.DataFrame(reversed(logs[-10:]))
                    st.dataframe(log_df, use_container_width=True)

        show_stocks_live()

    # --- 탭: 일정 관리 ---
    with tab_map["📅 일정 관리"]:
        st.subheader("📅 팀 업무 타임라인")

        start_d_str = team_data.get("start_date", str(datetime.today().date()))
        end_d_str = team_data.get("end_date", str(datetime.today().date()))
        try:
            start_d_val = date_type.fromisoformat(start_d_str) if isinstance(start_d_str, str) else start_d_str
            end_d_val = date_type.fromisoformat(end_d_str) if isinstance(end_d_str, str) else end_d_str
        except Exception:
            start_d_val = date_type.today()
            end_d_val = date_type.today()

        date_list = [start_d_val + timedelta(days=i) for i in range((end_d_val - start_d_val).days + 1)]
        date_strs = [str(d) for d in date_list]

        if is_leader:
            with st.expander("➕ 새 업무 추가", expanded=True):
                col_r1, col_r2, col_r3 = st.columns([2, 2, 4])
                with col_r1:
                    sel_date = st.selectbox("날짜", date_strs, key="cal_sel_date")
                with col_r2:
                    sel_worker = st.selectbox("담당자", m_names if m_names else ["없음"], key="cal_sel_worker")
                with col_r3:
                    sel_content = st.text_input("업무 내용", key="cal_content")
                if st.button("➕ 업무 추가", type="primary"):
                    if sel_content.strip():
                        _db2 = load_all_data()
                        cal = _db2["teams_master"][st.session_state.current_team_id].setdefault("calendar_events", {})
                        cal.setdefault(sel_date, []).append({
                            "id": str(uuid.uuid4()),
                            "content": sel_content.strip(),
                            "status": "⏳",
                            "worker": sel_worker
                        })
                        save_all_data(_db2)
                        st.success("✅ 업무가 추가되었습니다.")
                        st.rerun()

        st.write("---")

        @st.fragment(run_every=15)
        def show_calendar_live():
            fresh = load_all_data()
            fresh_team = fresh["teams_master"].get(st.session_state.current_team_id, {})

            # 오늘 날짜 하이라이트
            today_str = str(date_type.today())

            for d_str in date_strs:
                day_events = fresh_team.get("calendar_events", {}).get(d_str, [])
                is_today = (d_str == today_str)
                header_label = f"{'🔴 ' if is_today else ''}{d_str}{'  ← 오늘' if is_today else ''}"

                if day_events:
                    with st.expander(f"{header_label} ({len(day_events)}건)", expanded=is_today):
                        for idx, ev in enumerate(day_events):
                            c_d, c_w, c_c, c_s, c_ops = st.columns([1.5, 1.5, 4, 1.2, 1.8])
                            c_d.write(d_str)
                            c_w.write(f"👤 {ev.get('worker','?')}")
                            c_c.write(ev.get("content", ""))
                            status = ev.get("status", "⏳")
                            c_s.write("✔️ 완료" if "✔️" in status else "❌ 반려" if "❌" in status else "⏳ 대기")
                            if is_leader:
                                with c_ops:
                                    b1, b2, b3 = st.columns(3)
                                    ev_id = ev.get("id", f"{d_str}_{idx}")
                                    with b1:
                                        if st.button("✔️", key=f"v_{ev_id}"):
                                            _db2 = load_all_data()
                                            t2 = _db2["teams_master"][st.session_state.current_team_id]
                                            for ev2 in t2.get("calendar_events", {}).get(d_str, []):
                                                if ev2.get("id") == ev_id:
                                                    ev2["status"] = "✔️"
                                                    tw = ev2["worker"]
                                                    if tw in t2.get("stocks", {}):
                                                        t2["stocks"][tw].append(t2["stocks"][tw][-1] + 3000)
                                                        t2.setdefault("stock_logs", {}).setdefault(tw, []).append({"type": "plus", "val": 3000, "reason": f"{d_str} 결재"})
                                                    break
                                            save_all_data(_db2)
                                            st.rerun()
                                    with b2:
                                        if st.button("❌", key=f"x_{ev_id}"):
                                            _db2 = load_all_data()
                                            t2 = _db2["teams_master"][st.session_state.current_team_id]
                                            for ev2 in t2.get("calendar_events", {}).get(d_str, []):
                                                if ev2.get("id") == ev_id:
                                                    ev2["status"] = "❌"
                                                    tw = ev2["worker"]
                                                    if tw in t2.get("stocks", {}):
                                                        t2["stocks"][tw].append(max(0, t2["stocks"][tw][-1] - 3000))
                                                        t2.setdefault("stock_logs", {}).setdefault(tw, []).append({"type": "minus", "val": 3000, "reason": f"{d_str} 반려"})
                                                    break
                                            save_all_data(_db2)
                                            st.rerun()
                                    with b3:
                                        if st.button("🗑️", key=f"del_{ev_id}"):
                                            _db2 = load_all_data()
                                            cal = _db2["teams_master"][st.session_state.current_team_id].get("calendar_events", {})
                                            cal[d_str] = [x for x in cal.get(d_str, []) if x.get("id") != ev_id]
                                            save_all_data(_db2)
                                            st.rerun()
                            else:
                                c_ops.write("🔒")
                else:
                    if is_today:
                        st.markdown(f"**{header_label}** — 오늘 등록된 업무가 없습니다.")

        show_calendar_live()

    # --- 탭: 팀 관리 (조장 전용) ---
    if is_leader:
        with tab_map["👥 팀 관리"]:
            st.subheader("👥 팀 관리")

            host = st.context.headers.get("Host", "localhost:8501")
            protocol = "https" if "localhost" not in host else "http"
            invite_link = f"{protocol}://{host}/?invite=true&team_id={st.session_state.current_team_id}"

            st.markdown("#### 🔗 조원 초대 링크")
            st.info(invite_link)
            st.caption("이 링크를 조원들에게 공유하면 워크스페이스에 입장할 수 있습니다.")
            st.write("---")

            st.markdown("#### ⚙️ 팀 기본 정보")
            edit_tname = st.text_input("조 이름", value=team_data.get("team_name", ""), key="edit_tname")
            edit_subj = st.text_input("프로젝트 주제", value=team_data.get("subject", ""), key="edit_subj")
            if st.button("💾 기본 정보 저장"):
                _db2 = load_all_data()
                _db2["teams_master"][st.session_state.current_team_id]["team_name"] = edit_tname.strip() or team_data.get("team_name", "우리팀")
                _db2["teams_master"][st.session_state.current_team_id]["subject"] = edit_subj.strip()
                save_all_data(_db2)
                st.success("✅ 저장 완료")
                st.rerun()

            st.write("---")
            st.markdown("#### 👥 조원 명부 수정")
            updated_members = []
            name_changes = {}

            for i, m in enumerate(team_data.get("members", [])):
                is_ldr = " 👑" if i == team_data.get("leader_idx", 0) else ""
                st.markdown(f"**조원 {i+1}{is_ldr}**")
                c1, c2, c3 = st.columns(3)
                old_name = m["이름"]
                with c1: new_name = st.text_input("이름", value=old_name, key=f"mn_{i}").strip()
                with c2: new_contact = st.text_input("연락처", value=m["연락처"], key=f"mc_{i}")
                with c3: new_role = st.text_input("역할", value=m["역할"], key=f"mr_{i}")
                updated_members.append({"이름": new_name, "연락처": new_contact, "역할": new_role})
                if old_name and new_name and old_name != new_name:
                    name_changes[old_name] = new_name

            if st.button("💾 명부 저장 및 이름 변경 반영", type="primary"):
                _db2 = load_all_data()
                t2 = _db2["teams_master"][st.session_state.current_team_id]
                # 이름 변경 일괄 반영
                for old_n, new_n in name_changes.items():
                    for key in ["stocks", "stock_logs"]:
                        if old_n in t2.get(key, {}):
                            t2[key][new_n] = t2[key].pop(old_n)
                    for room in t2.get("chat_rooms", []):
                        room["members"] = [new_n if m == old_n else m for m in room.get("members", [])]
                    for chat in t2.get("chats_archive", []):
                        if chat.get("sender") == old_n:
                            chat["sender"] = new_n
                    for evs in t2.get("calendar_events", {}).values():
                        for ev in evs:
                            if ev.get("worker") == old_n:
                                ev["worker"] = new_n
                    for story in t2.get("stories", []):
                        if story.get("user") == old_n:
                            story["user"] = new_n
                        for cm in story.get("comments", []):
                            if cm.get("writer") == old_n:
                                cm["writer"] = new_n
                    if st.session_state.current_user == old_n:
                        st.session_state.current_user = new_n

                t2["members"] = updated_members
                # 새 조원 주식 초기화
                for m in t2["members"]:
                    if m["이름"] and m["이름"] not in t2.setdefault("stocks", {}):
                        t2["stocks"][m["이름"]] = [10000]
                        t2.setdefault("stock_logs", {})[m["이름"]] = []
                save_all_data(_db2)
                st.success("✅ 명부가 저장되었습니다.")
                st.rerun()

    # --- 탭: 채팅방 ---
    with tab_map["💬 채팅방"]:
        st.subheader("💬 팀 채팅방")

        all_associates = [p for p in m_names if p.strip()]
        if leader_name not in all_associates and leader_name != "미정":
            all_associates.append(leader_name)

        with st.expander("➕ 새 채팅방 만들기"):
            choose_members = st.multiselect("참여 멤버 선택", all_associates, default=[my_chat_name] if my_chat_name in all_associates else [])
            room_title = st.text_input("채팅방 이름", placeholder="예: 개발팀 단톡, 디자인 파트 등")
            if st.button("🚀 채팅방 개설"):
                if len(choose_members) < 1:
                    st.error("최소 1명 이상 선택하세요.")
                else:
                    if my_chat_name not in choose_members:
                        choose_members.append(my_chat_name)
                    choose_members = list(set(choose_members))
                    if not room_title.strip():
                        others = [p for p in choose_members if p != my_chat_name]
                        room_title = (", ".join(others) + " 님과의 채팅방") if others else "나만의 메모장"
                    _db2 = load_all_data()
                    _db2["teams_master"][st.session_state.current_team_id].setdefault("chat_rooms", []).append({
                        "room_id": str(uuid.uuid4()),
                        "title": room_title,
                        "members": choose_members
                    })
                    save_all_data(_db2)
                    st.success(f"✅ '{room_title}' 채팅방이 생성되었습니다!")
                    st.rerun()

        st.write("---")

        @st.fragment(run_every=8)
        def show_chat_live():
            fresh = load_all_data()
            fresh_team = fresh["teams_master"].get(st.session_state.current_team_id, {})
            my_rooms = [r for r in fresh_team.get("chat_rooms", []) if my_chat_name in r.get("members", [])]

            col_rooms, col_chat = st.columns([1, 2])

            with col_rooms:
                st.markdown("**내 채팅방**")
                if not my_rooms:
                    st.caption("참여 중인 채팅방이 없습니다.")
                for rm in my_rooms:
                    is_active = (st.session_state.active_chat_room_id == rm["room_id"])
                    # 미읽 메시지 수 (간단히 표시)
                    label = f"{'🟢 ' if is_active else '💬 '}{rm['title']} ({len(rm['members'])}명)"
                    if st.button(label, key=f"room_{rm['room_id']}", use_container_width=True,
                                 type="primary" if is_active else "secondary"):
                        st.session_state.active_chat_room_id = rm["room_id"]
                        st.rerun()

            with col_chat:
                active_id = st.session_state.active_chat_room_id
                target_room = next((r for r in my_rooms if r["room_id"] == active_id), None)

                if target_room is None:
                    st.info("👈 채팅방을 선택하세요.")
                else:
                    col_ct, col_ce = st.columns([3, 1])
                    with col_ct:
                        st.markdown(f"### 💬 {target_room['title']}")
                        st.caption(f"👥 {', '.join(target_room['members'])}")
                    with col_ce:
                        if st.button("🚪 나가기", key=f"exit_{target_room['room_id']}"):
                            _db2 = load_all_data()
                            for r in _db2["teams_master"][st.session_state.current_team_id].get("chat_rooms", []):
                                if r["room_id"] == target_room["room_id"] and my_chat_name in r["members"]:
                                    r["members"].remove(my_chat_name)
                                    break
                            save_all_data(_db2)
                            st.session_state.active_chat_room_id = None
                            st.rerun()

                    msg_box = st.container(height=320)
                    with msg_box:
                        room_msgs = [c for c in fresh_team.get("chats_archive", []) if c.get("room_id") == target_room["room_id"]]
                        for chat in room_msgs:
                            is_me = (chat["sender"] == my_chat_name)
                            if is_me:
                                st.markdown(f"<div style='text-align:right;margin-bottom:6px;'><span style='background:#ffe600;color:black;padding:5px 10px;border-radius:12px;display:inline-block;max-width:70%;text-align:left;'><b>나</b><br>{chat['msg']}<br><small style='color:gray;font-size:10px;'>{chat['time']}</small></span></div>", unsafe_allow_html=True)
                            else:
                                st.markdown(f"<div style='text-align:left;margin-bottom:6px;'><span style='background:#f1f1f1;color:black;padding:5px 10px;border-radius:12px;display:inline-block;max-width:70%;'><b>{chat['sender']}</b><br>{chat['msg']}<br><small style='color:gray;font-size:10px;'>{chat['time']}</small></span></div>", unsafe_allow_html=True)

                    with st.form(f"chat_form_{target_room['room_id']}", clear_on_submit=True):
                        msg_in = st.text_input("메시지 입력", placeholder="메시지를 입력하세요")
                        if st.form_submit_button("전송 →") and msg_in.strip():
                            _db2 = load_all_data()
                            _db2["teams_master"][st.session_state.current_team_id].setdefault("chats_archive", []).append({
                                "room_id": target_room["room_id"],
                                "sender": my_chat_name,
                                "msg": msg_in.strip(),
                                "time": datetime.now().strftime("%H:%M")
                            })
                            save_all_data(_db2)
                            st.rerun()

        show_chat_live()

    # --- 탭: SOS 고객센터 ---
    with tab_map["🚨 SOS 고객센터"]:
        st.subheader("🚨 버그 제보 및 1:1 문의")

        col_s1, col_s2 = st.columns([2, 3])

        with col_s1:
            st.markdown("#### 🛠️ 문의 접수")
            with st.form("sos_form", clear_on_submit=True):
                bug_content = st.text_area("문의 내용", placeholder="어떤 문제가 발생했는지 상세히 작성해주세요.")
                bug_img = st.file_uploader("오류 스크린샷 (선택)", type=["png", "jpg", "jpeg"])
                if st.form_submit_button("🚨 SOS 전송", type="primary"):
                    if bug_content.strip():
                        img_b64 = None
                        img_name = "없음"
                        if bug_img:
                            img_b64 = base64.b64encode(bug_img.read()).decode("utf-8")
                            img_name = bug_img.name
                        _db2 = load_all_data()
                        _db2["admin_master"].setdefault("bug_reports", []).append({
                            "report_id": str(uuid.uuid4()),
                            "team_id": st.session_state.current_team_id,
                            "team_name": team_data.get("team_name", "우리팀"),
                            "sender": my_chat_name,
                            "content": bug_content.strip(),
                            "image_bytes": img_b64,
                            "image_name": img_name,
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "reply": None,
                            "status": "⏳ 대기중"
                        })
                        save_all_data(_db2)
                        st.success("✅ 관리자에게 전송되었습니다!")
                        st.rerun()

        with col_s2:
            st.markdown("#### 📬 내 문의 처리 현황")

            @st.fragment(run_every=10)
            def show_sos_status():
                fresh = load_all_data()
                my_reports = [r for r in fresh["admin_master"].get("bug_reports", [])
                              if r["team_id"] == st.session_state.current_team_id]
                if not my_reports:
                    st.caption("접수한 문의가 없습니다.")
                    return
                for rep in reversed(my_reports):
                    with st.container(border=True):
                        done = rep["status"] == "✔️ 처리완료"
                        st.markdown(f"**{'🟢 처리완료' if done else '⏳ 검토중'}** | {rep['time']}")
                        st.write(rep["content"])
                        if rep.get("reply"):
                            st.info(f"👑 **관리자 답변:** {rep['reply']}")
                        else:
                            st.caption("관리자 답변 대기 중...")

            show_sos_status()
