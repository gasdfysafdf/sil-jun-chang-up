import streamlit as st
import pandas as pd
import os
import uuid
import json
import base64
from datetime import datetime, timedelta, date as date_type

st.set_page_config(page_title="스타트리 (Startree)", page_icon="🌳", layout="wide")

# =============================================
# [용량 최적화 유틸리티]
# =============================================
MAX_IMAGE_KB  = 150     # 이미지 최대 150KB (압축 강화)
MAX_VIDEO_KB  = 2000    # 영상 최대 2MB
MAX_AUDIO_KB  = 1500    # 음성 최대 1.5MB
MAX_FILE_KB   = 800     # 첨부파일 최대 800KB
MAX_CHAT_MSGS = 150     # 채팅방당 최대 보관 메시지
MAX_STORIES   = 20      # 팀당 최대 스토리 수
MAX_NOTICES   = 30      # 팀당 최대 공지 수
MAX_SOS_TOTAL = 200     # SOS 전체 최대 보관 수
SUPABASE_LIMIT_BYTES = 900_000  # Supabase JSONB 실질 안전 한계 ~900KB

def estimate_db_size(db: dict) -> int:
    try:
        return len(json.dumps(db, ensure_ascii=False).encode("utf-8"))
    except Exception:
        return 0

def db_size_label(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes/1024:.1f} KB"
    else:
        return f"{size_bytes/1024/1024:.2f} MB"

def auto_trim_db(db: dict) -> dict:
    for tid, t in db.get("teams_master", {}).items():
        chats = t.get("chats_archive", [])
        if len(chats) > MAX_CHAT_MSGS:
            t["chats_archive"] = chats[-MAX_CHAT_MSGS:]
        stories = t.get("stories", [])
        if len(stories) > MAX_STORIES:
            t["stories"] = stories[:MAX_STORIES]
        notices = t.get("notices", [])
        if len(notices) > MAX_NOTICES:
            t["notices"] = notices[:MAX_NOTICES]
    reports = db.get("admin_master", {}).get("bug_reports", [])
    if len(reports) > MAX_SOS_TOTAL:
        done = [r for r in reports if r["status"] == "✔️ 처리완료"]
        pending = [r for r in reports if r["status"] != "✔️ 처리완료"]
        trimmed = pending + done[-(MAX_SOS_TOTAL - len(pending)):]
        db["admin_master"]["bug_reports"] = trimmed
    return db


def _auto_trim_team(t: dict) -> dict:
    """팀 1개 단위 트림 (save_team_data 에서 호출)."""
    chats = t.get("chats_archive", [])
    if len(chats) > MAX_CHAT_MSGS:
        t["chats_archive"] = chats[-MAX_CHAT_MSGS:]
    stories = t.get("stories", [])
    if len(stories) > MAX_STORIES:
        t["stories"] = stories[:MAX_STORIES]
    notices = t.get("notices", [])
    if len(notices) > MAX_NOTICES:
        t["notices"] = notices[:MAX_NOTICES]
    return t

def compress_image_b64(raw_bytes: bytes, max_kb: int = MAX_IMAGE_KB) -> str:
    """PIL로 이미지를 리사이즈·압축 후 base64 반환. PIL 없으면 그냥 b64 반환."""
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(raw_bytes))
        # EXIF 회전 보정
        try:
            from PIL import ImageOps
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass
        # RGBA → RGB 변환 (JPEG 저장 위해)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        # 가로 최대 1200px 리사이즈
        if img.width > 1200:
            ratio = 1200 / img.width
            img = img.resize((1200, int(img.height * ratio)), Image.LANCZOS)
        # 품질 조절로 max_kb 이하 맞추기
        quality = 85
        while quality >= 40:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            if buf.tell() <= max_kb * 1024:
                break
            quality -= 10
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        # PIL 없거나 오류 시 그냥 인코딩
        return base64.b64encode(raw_bytes).decode("utf-8")

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

# =============================================
# [DB 핵심 - v3.0 분리 구조]
# startree_meta  : id="main" 단일 row → users_master / admin_master / teams_index
# startree_teams : id=team_id 팀별 row → 해당 팀 전체 데이터
#
# 기존 load_all_data() / save_all_data() 를 대체.
#  - get_cached_meta()              : 메타(관리자·유저·팀목록)만 로드
#  - get_cached_team(team_id)       : 특정 팀 데이터만 로드
#  - save_meta_data(meta_db)        : 메타 저장 + 메타 캐시 초기화
#  - save_team_data(team_id, data)  : 팀 저장 + teams_index 갱신 + 캐시 초기화
# =============================================

DEFAULT_META = {
    "users_master": {},
    "admin_master": {
        "admin_id": ADMIN_ID,
        "admin_pw": ADMIN_PW,
        "system_notices": [],
        "bug_reports": [],
    },
    # 전체 팀 목록(가벼운 인덱스). 팀 본문은 startree_teams 에 있음.
    # {team_id: {"team_name", "leader_id", "members", "notices",
    #            "stories", "chats", "pending"}}  ← 요약 수치만 보관
    "teams_index": {},
}

DEFAULT_TEAM = {
    "team_name": "",
    "subject": "",
    "members": [],
    "leader_idx": 0,
    "notices": [],
    "stories": [],
    "chats_archive": [],
    "chat_rooms": [],
    "calendar_events": {},
    "stocks": {},
    "stock_logs": {},
}

# --- 메타 ----------------------------------------------------------------
@st.cache_data(ttl=5)
def get_cached_meta():
    """관리자 정보 + 유저 마스터 + 팀 목록(인덱스)만 로드."""
    try:
        res = supabase.table("startree_meta").select("data").eq("id", "main").execute()
        if res.data and len(res.data) > 0:
            meta = res.data[0]["data"]
            meta.setdefault("users_master", {})
            meta.setdefault("teams_index", {})
            if "admin_master" not in meta:
                meta["admin_master"] = DEFAULT_META["admin_master"].copy()
            return meta
        supabase.table("startree_meta").insert({"id": "main", "data": DEFAULT_META}).execute()
        return json.loads(json.dumps(DEFAULT_META))  # deep copy
    except Exception as e:
        st.error(f"메타 DB 연결 오류: {e}")
        return json.loads(json.dumps(DEFAULT_META))


def save_meta_data(meta_db):
    """메타 저장 후 메타 캐시 초기화."""
    try:
        supabase.table("startree_meta").upsert({"id": "main", "data": meta_db}).execute()
        get_cached_meta.clear()
    except Exception as e:
        st.error(f"메타 DB 저장 오류: {e}")


# --- 팀 ------------------------------------------------------------------
@st.cache_data(ttl=5)
def get_cached_team(team_id):
    """특정 팀 데이터만 로드. 없으면 None."""
    if not team_id:
        return None
    try:
        res = supabase.table("startree_teams").select("data").eq("id", team_id).execute()
        if res.data and len(res.data) > 0:
            team = res.data[0]["data"]
            for k, v in DEFAULT_TEAM.items():
                team.setdefault(k, json.loads(json.dumps(v)))
            return team
        return None
    except Exception as e:
        st.error(f"팀 DB 연결 오류: {e}")
        return None


@st.cache_data(ttl=5)
def get_all_teams():
    """모든 팀을 한 번의 쿼리로 로드 (관리자 집계 화면 전용). {team_id: team_data}."""
    try:
        res = supabase.table("startree_teams").select("id,data").execute()
        out = {}
        for row in (res.data or []):
            t = row["data"]
            for k, v in DEFAULT_TEAM.items():
                t.setdefault(k, json.loads(json.dumps(v)))
            out[row["id"]] = t
        return out
    except Exception as e:
        st.error(f"전체 팀 로드 오류: {e}")
        return {}


def _team_summary(team_data: dict) -> dict:
    """관리자 대시보드용 요약 수치. 팀 저장 시 teams_index 에 함께 기록."""
    pending = sum(
        1
        for evs in team_data.get("calendar_events", {}).values()
        for ev in evs
        if "⏳" in ev.get("status", "⏳")
    )
    return {
        "team_name": team_data.get("team_name", "설정중"),
        "members": len(team_data.get("members", [])),
        "notices": len(team_data.get("notices", [])),
        "stories": len(team_data.get("stories", [])),
        "chats": len(team_data.get("chats_archive", [])),
        "pending": pending,
    }


def save_team_data(team_id, team_data):
    """팀 저장 + 메타의 teams_index 요약 갱신 + 관련 캐시 초기화."""
    if not team_id:
        return
    try:
        team_data = _auto_trim_team(team_data)  # 기존 auto_trim_db 의 팀 단위 버전
        supabase.table("startree_teams").upsert({"id": team_id, "data": team_data}).execute()

        # teams_index 요약 동기화 (관리자 화면이 메타만 읽고도 합계를 낼 수 있게)
        meta = get_cached_meta()
        meta.setdefault("teams_index", {})
        entry = meta["teams_index"].get(team_id, {})
        entry.update(_team_summary(team_data))
        entry.setdefault("leader_id", entry.get("leader_id"))
        meta["teams_index"][team_id] = entry
        save_meta_data(meta)  # 내부에서 메타 캐시 clear

        get_cached_team.clear()
        get_all_teams.clear()
    except Exception as e:
        st.error(f"팀 DB 저장 오류: {e}")


def delete_team_data(team_id):
    """팀 삭제 + teams_index 에서 제거."""
    try:
        supabase.table("startree_teams").delete().eq("id", team_id).execute()
        meta = get_cached_meta()
        meta.get("teams_index", {}).pop(team_id, None)
        save_meta_data(meta)
        get_cached_team.clear()
        get_all_teams.clear()
    except Exception as e:
        st.error(f"팀 삭제 오류: {e}")

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
    meta_db = get_cached_meta()
    target_team = qp["team_id"]
    if target_team in meta_db["teams_index"]:
        if st.session_state.current_user is None and st.session_state.step not in ("main_home", "admin_dashboard"):
            st.session_state.current_team_id = target_team
            st.session_state.user_role = "member"
            st.session_state.step = "member_auth"

# 현재 팀 데이터 매핑
team_data = get_cached_team(st.session_state.current_team_id)
m_names = []
leader_name = "미정"
if team_data:
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
        get_cached_meta.clear()
        get_cached_team.clear()
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
    # 사이드바 D-day 표시
    if st.session_state.current_user and st.session_state.user_role != "admin" and team_data:
        try:
            _end = date_type.fromisoformat(team_data.get("end_date", str(date_type.today())))
            _dd = (_end - date_type.today()).days
            if _dd > 0:
                st.caption(f"📅 D-{_dd} 마감")
            elif _dd == 0:
                st.warning("⚠️ 오늘 마감!")
            else:
                st.error(f"⏰ 마감 {abs(_dd)}일 초과")
        except Exception:
            pass
    st.caption("⚙️ Startree v2.2 · 2026")

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
                _db = get_cached_meta()
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
                    st.session_state.step = "main_home" if user_info["team_id"] in _db["teams_index"] else "setup_1"
                    st.rerun()
                else:
                    st.error("아이디 또는 비밀번호가 잘못되었습니다.")
        with col_l2:
            _db_sec = get_cached_meta()
            _team_lock = _db_sec["admin_master"].get("security_settings", {}).get("new_team_lock", False)
            if _team_lock:
                st.button("🔒 팀 등록 잠김 (관리자 설정)", use_container_width=True, disabled=True)
            else:
                if st.button("새 팀 개설 (조장 가입)", use_container_width=True):
                    st.session_state.step = "auth_register"
                    st.rerun()

        st.write("---")
        with st.expander("🔍 ID / 비밀번호 찾기"):
            find_tab = st.radio("", ["아이디 찾기", "비밀번호 찾기"], horizontal=True, key="find_tab_radio")
            _db = get_cached_meta()

            if find_tab == "아이디 찾기":
                find_pw = st.text_input("비밀번호", type="password", key="find_pw_input").strip()
                find_team = st.text_input("조 이름", key="find_team_name_id").strip()
                if st.button("아이디 찾기", key="find_id_btn"):
                    found = None
                    for uid, uinfo in _db["users_master"].items():
                        if uinfo["pw"] == find_pw:
                            t_info = _db["teams_index"].get(uinfo["team_id"], {})
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
                        t_info = _db["teams_index"].get(uinfo["team_id"], {})
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
            _db = get_cached_meta()
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
                _db = get_cached_meta()
                _db["users_master"][reg_id] = {"pw": reg_pw, "team_id": new_team_id}
                save_meta_data(_db)
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
        _db = get_cached_team(st.session_state.current_team_id)
        _db = {
            "member_count": count,
            "members": [{"이름": "", "연락처": "", "역할": ""} for _ in range(count)],
            "leader_idx": 0, "team_name": "", "subject": "",
            "start_date": str(datetime.today().date()),
            "end_date": str((datetime.today() + timedelta(days=7)).date()),
            "calendar_events": {}, "notices": [], "chat_rooms": [],
            "chats_archive": [], "stories": [], "stocks": {}, "stock_logs": {}
        }
        save_team_data(st.session_state.current_team_id, _db)
        st.session_state.step = "setup_2"
        st.rerun()

elif st.session_state.step == "setup_2":
    st.title("🚀 팀 초기 설정")
    st.subheader("2단계: 팀원 명부 작성")
    _db = get_cached_team(st.session_state.current_team_id)
    current_team = _db
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
        if any(not m.get("이름","").strip() for m in current_team["members"]):
            st.error("❌ 모든 조원의 이름을 입력해주세요.")
        else:
            save_team_data(st.session_state.current_team_id, _db)
            st.session_state.step = "setup_3"
            st.rerun()

elif st.session_state.step == "setup_3":
    st.title("🚀 팀 초기 설정")
    st.subheader("3단계: 팀 기본 정보 입력")
    _db = get_cached_team(st.session_state.current_team_id)
    current_team = _db

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
        save_team_data(st.session_state.current_team_id, _db)
        st.session_state.step = "setup_4"
        st.rerun()

elif st.session_state.step == "setup_4":
    st.title("🚀 팀 초기 설정")
    st.subheader("4단계: 주식(기여도) 시스템 초기화")
    _db = get_cached_team(st.session_state.current_team_id)
    current_team = _db

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
        save_team_data(st.session_state.current_team_id, _db)
        st.session_state.step = "setup_5"
        st.rerun()

elif st.session_state.step == "setup_5":
    st.title("🚀 팀 초기 설정")
    st.subheader("5단계: 초대 링크 발급 완료!")
    _db = get_cached_team(st.session_state.current_team_id)
    t_info = (_db or {})

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
    @st.fragment(run_every=5)
    def _admin_clock():
        st.markdown(f"**⚡ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}** | 관리자: **{st.session_state.current_user}**")
    _admin_clock()
    st.write("---")

    admin_tabs = st.tabs([
        "📊 전체 현황",       # 0
        "👥 팀 관리",          # 1
        "🗂️ 팀 직접 편집",    # 2
        "🚨 SOS 수신함",       # 3
        "📢 전사 공지",        # 4
        "📈 활동 분석",        # 5
        "🧹 데이터 관리",      # 6
        "💾 용량 관리",        # 7
        "🔍 채팅 모니터링",    # 8  ← 신규 (활동 로그 대체)
        "📋 활동 로그",        # 9  ← 신규 구현
        "⚙️ 보안 설정"         # 10 ← 신규 구현
    ])

    # --- 관리자 탭 0: 전체 현황 대시보드 ---
    with admin_tabs[0]:
        st.subheader("📊 플랫폼 전체 현황")
        if st.button("🔄 현황 새로고침", key="admin_stat_refresh"):
            get_cached_meta.clear()
            get_cached_team.clear()
            get_all_teams.clear()
            st.rerun()

        _db = get_cached_meta()
        total_teams = len(_db["users_master"])
        total_members = sum(len(v.get("members", [])) for v in get_all_teams().values())
        total_bugs = len(_db["admin_master"].get("bug_reports", []))
        pending_bugs = len([r for r in _db["admin_master"].get("bug_reports", []) if r["status"] != "✔️ 처리완료"])
        total_notices = len(_db["admin_master"].get("system_notices", []))
        total_chats = sum(len(v.get("chats_archive", [])) for v in get_all_teams().values())
        total_stories = sum(len(v.get("stories", [])) for v in get_all_teams().values())
        total_calendar = sum(sum(len(ev) for ev in v.get("calendar_events", {}).values()) for v in get_all_teams().values())

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
                    t_info = get_all_teams().get(t_id, {})
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

        _db = get_cached_meta()
        if not _db["users_master"]:
            st.info("등록된 팀이 없습니다.")
        else:
            records = []
            for l_id, u_info in _db["users_master"].items():
                t_id = u_info["team_id"]
                t_info = get_all_teams().get(t_id, {})
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
                        _db2 = get_cached_meta()
                        _db2["users_master"][target_leader]["pw"] = new_pw.strip()
                        _db2["admin_master"].setdefault("activity_logs", []).insert(0, {
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "admin": st.session_state.current_user,
                            "action": f"비밀번호 강제 변경",
                            "target": target_leader
                        })
                        save_meta_data(_db2)
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
        _db = get_cached_meta()

        if not _db["users_master"]:
            st.info("등록된 팀이 없습니다.")
        else:
            team_options = {}
            for l_id, u_info in _db["users_master"].items():
                t_id = u_info["team_id"]
                t_info = get_all_teams().get(t_id, {})
                label = f"{t_info.get('team_name', '설정중')} (조장: {l_id})"
                team_options[label] = t_id

            sel_label = st.selectbox("편집할 팀 선택", list(team_options.keys()))
            edit_t_id = team_options[sel_label]
            edit_team = get_cached_team(edit_t_id) or {}

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
                        edit_obj = get_cached_team(edit_t_id) or {}
                        edit_obj["team_name"] = new_tname.strip() or edit_team.get("team_name", "우리팀")
                        edit_obj["subject"] = new_subj.strip()
                        edit_obj["end_date"] = str(new_end)
                        save_team_data(edit_t_id, edit_obj)
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
                            edit_obj = get_cached_team(edit_t_id) or {}
                            edit_obj["members"] = updated
                            edit_obj["leader_idx"] = new_li
                            save_team_data(edit_t_id, edit_obj)
                            st.success("✅ 명단 저장 완료")
                            st.rerun()

    # --- 관리자 탭 3: SOS 수신함 ---
    with admin_tabs[3]:
        st.subheader("📥 SOS 버그 제보 수신함")

        @st.fragment(run_every=8)
        def show_admin_sos():
            fresh = get_cached_meta()
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
                                _db2 = get_cached_meta()
                                _db2["admin_master"]["bug_reports"][true_idx]["reply"] = reply_text.strip()
                                _db2["admin_master"]["bug_reports"][true_idx]["status"] = "✔️ 처리완료"
                                save_meta_data(_db2)
                                st.rerun()
                        with c_b2:
                            if st.form_submit_button("🗑️ 삭제"):
                                _db2 = get_cached_meta()
                                _db2["admin_master"]["bug_reports"].pop(true_idx)
                                save_meta_data(_db2)
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
                    _db2 = get_cached_meta()
                    _db2["admin_master"].setdefault("system_notices", []).insert(0, {
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "msg": sys_msg.strip(),
                        "type": notice_type
                    })
                    save_meta_data(_db2)
                    st.success("✅ 공지가 전체 배포되었습니다!")
                    st.rerun()

        st.write("---")
        st.markdown("#### 📜 송출 중인 공지 목록")
        _db = get_cached_meta()
        for idx, sn in enumerate(_db["admin_master"].get("system_notices", [])):
            with st.container(border=True):
                col_n1, col_n2 = st.columns([4, 1])
                with col_n1:
                    st.caption(f"📅 {sn['time']} | {sn.get('type', '📢 일반')}")
                    st.write(sn["msg"])
                with col_n2:
                    if st.button("🗑️ 삭제", key=f"del_sn_{idx}"):
                        _db["admin_master"]["system_notices"].pop(idx)
                        save_meta_data(_db)
                        st.rerun()

    # --- 관리자 탭 5: 활동 분석 (신규) ---
    with admin_tabs[5]:
        st.subheader("📈 팀별 활동 분석")
        _db = get_cached_meta()

        if not _db["users_master"]:
            st.info("등록된 팀이 없습니다.")
        else:
            analysis_options = {}
            for l_id, u_info in _db["users_master"].items():
                t_id = u_info["team_id"]
                t_info = get_all_teams().get(t_id, {})
                label = f"{t_info.get('team_name', '설정중')} (조장: {l_id})"
                analysis_options[label] = t_id

            sel_analysis = st.selectbox("분석할 팀 선택", list(analysis_options.keys()), key="analysis_team_sel")
            a_t_id = analysis_options[sel_analysis]
            a_team = get_cached_team(a_t_id) or {}

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
                            team_obj = get_cached_team(a_t_id) or {}
                            team_obj.setdefault("notices", []).insert(0, {
                                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "content": f"[📢 관리자 메시지] {admin_msg_content.strip()}",
                                "file_name": "없음",
                                "file_bytes": None
                            })
                            save_team_data(a_t_id, team_obj)
                            st.success("✅ 해당 팀 공지사항에 메시지가 전달되었습니다.")
                            st.rerun()

    # --- 관리자 탭 6: 데이터 관리 ---
    with admin_tabs[6]:
        st.subheader("🧹 팀 데이터 관리")
        _db = get_cached_meta()

        if not _db["users_master"]:
            st.info("등록된 팀이 없습니다.")
        else:
            mgmt_opts = {}
            for l_id, u_info in _db["users_master"].items():
                t_id = u_info["team_id"]
                t_info = get_all_teams().get(t_id, {})
                mgmt_opts[f"{t_info.get('team_name', '설정중')} (조장: {l_id})"] = (l_id, t_id)

            sel_mgmt = st.selectbox("관리 대상 팀", list(mgmt_opts.keys()), key="mgmt_sel")
            mgmt_lid, mgmt_tid = mgmt_opts[sel_mgmt]

            st.write("---")
            col_d1, col_d2 = st.columns(2)

            with col_d1:
                st.markdown("#### 🗑️ 항목별 초기화")
                st.warning("초기화는 복구 불가능합니다.")
                if st.button("💬 채팅 초기화", use_container_width=True):
                    team_obj = get_cached_team(mgmt_tid) or {}
                    team_obj["chats_archive"] = []
                    save_team_data(mgmt_tid, team_obj)
                    st.success("✅ 채팅 초기화 완료")
                    st.rerun()
                if st.button("✨ 스토리 초기화", use_container_width=True):
                    team_obj = get_cached_team(mgmt_tid) or {}
                    team_obj["stories"] = []
                    save_team_data(mgmt_tid, team_obj)
                    st.success("✅ 스토리 초기화 완료")
                    st.rerun()
                if st.button("📢 팀 공지 초기화", use_container_width=True):
                    team_obj = get_cached_team(mgmt_tid) or {}
                    team_obj["notices"] = []
                    save_team_data(mgmt_tid, team_obj)
                    st.success("✅ 공지 초기화 완료")
                    st.rerun()
                if st.button("🚪 채팅방 초기화", use_container_width=True):
                    team_obj = get_cached_team(mgmt_tid) or {}
                    team_obj["chat_rooms"] = []
                    team_obj["chats_archive"] = []
                    save_team_data(mgmt_tid, team_obj)
                    st.success("✅ 채팅방 초기화 완료")
                    st.rerun()
                if st.button("📅 캘린더 초기화", use_container_width=True):
                    team_obj = get_cached_team(mgmt_tid) or {}
                    team_obj["calendar_events"] = {}
                    save_team_data(mgmt_tid, team_obj)
                    st.success("✅ 캘린더 초기화 완료")
                    st.rerun()
                if st.button("📊 기여도 초기화", use_container_width=True):
                    t_data = get_cached_team(mgmt_tid) or {}
                    for m in t_data.get("members", []):
                        if m.get("이름"):
                            t_data.setdefault("stocks", {})[m["이름"]] = [10000]
                            t_data.setdefault("stock_logs", {})[m["이름"]] = []
                    save_team_data(mgmt_tid, t_data)
                    st.success("✅ 기여도 초기화 완료")
                    st.rerun()

            with col_d2:
                st.markdown("#### ☣️ 팀 완전 삭제")
                st.error("삭제 시 모든 데이터가 영구 삭제됩니다.")
                confirm_del = st.checkbox(f"'{sel_mgmt}' 삭제에 동의합니다", key="confirm_del_cb")
                if st.button("🗑️ 팀 완전 삭제", use_container_width=True):
                    if confirm_del:
                        _team_for_del = get_cached_team(mgmt_tid) or {}
                        team_name_del = _team_for_del.get("team_name", mgmt_tid)
                        meta_db = get_cached_meta()
                        meta_db["users_master"].pop(mgmt_lid, None)
                        meta_db["admin_master"].setdefault("activity_logs", []).insert(0, {
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "admin": st.session_state.current_user,
                            "action": f"팀 완전 삭제",
                            "target": f"{team_name_del} (조장: {mgmt_lid})"
                        })
                        save_meta_data(meta_db)
                        delete_team_data(mgmt_tid)
                        st.success("✅ 삭제 완료")
                        st.rerun()
                    else:
                        st.warning("삭제 동의 체크박스를 체크하세요.")

                st.write("---")
                st.markdown("#### 📬 처리완료 SOS 일괄 삭제")
                if st.button("🧹 처리완료 SOS 삭제", use_container_width=True):
                    _db2 = get_cached_meta()
                    _db2["admin_master"]["bug_reports"] = [
                        r for r in _db2["admin_master"].get("bug_reports", [])
                        if r["status"] != "✔️ 처리완료"
                    ]
                    save_meta_data(_db2)
                    st.success("✅ 정리 완료")
                    st.rerun()

    # --- 관리자 탭 7: 용량 관리 ---
    with admin_tabs[7]:
        st.subheader("💾 DB 용량 관리")
        _db = get_cached_meta()
        _all_teams = get_all_teams()
        size = estimate_db_size(_db) + sum(estimate_db_size(t) for t in _all_teams.values())
        pct = min(size / SUPABASE_LIMIT_BYTES * 100, 100)
        bar_color = "#e74c3c" if pct > 85 else "#f39c12" if pct > 60 else "#2ecc71"
        st.markdown(f"""
        <div style="background:#1e1e1e;border-radius:8px;padding:16px;margin-bottom:12px;">
          <b>현재 DB 사용량:</b> {db_size_label(size)} / {db_size_label(SUPABASE_LIMIT_BYTES)}
          <div style="background:#333;border-radius:4px;height:16px;margin-top:8px;">
            <div style="background:{bar_color};width:{pct:.1f}%;height:16px;border-radius:4px;"></div>
          </div>
          <small style="color:gray;">{pct:.1f}% 사용 중</small>
        </div>
        """, unsafe_allow_html=True)

        if pct > 85:
            st.error("🚨 DB 용량이 위험 수준입니다. 즉시 정리가 필요합니다.")
        elif pct > 60:
            st.warning("⚠️ DB 용량이 60%를 넘었습니다. 미디어/채팅 정리를 권장합니다.")

        st.write("---")
        col_cap1, col_cap2 = st.columns(2)
        with col_cap1:
            st.markdown("#### ⚙️ 용량 제한 설정")
            st.caption("변경 사항은 코드 상단 상수값을 수정해야 영구 적용됩니다.")
            st.info(f"""
            현재 설정:
            - 이미지 최대: {MAX_IMAGE_KB}KB
            - 채팅 보관: 방당 {MAX_CHAT_MSGS}개
            - 스토리 보관: 팀당 {MAX_STORIES}개
            - 공지 보관: 팀당 {MAX_NOTICES}개
            """)

        with col_cap2:
            st.markdown("#### 🧹 자동 트림 실행")
            st.caption("오래된 데이터를 설정 한도에 맞게 자동으로 정리합니다.")
            if st.button("🔄 자동 트림 즉시 실행", use_container_width=True, type="primary"):
                _teams_now = get_all_teams()
                _meta_now = get_cached_meta()
                before = estimate_db_size(_meta_now) + sum(estimate_db_size(t) for t in _teams_now.values())
                # 팀별 트림
                for _tid, _tdata in _teams_now.items():
                    save_team_data(_tid, _auto_trim_team(_tdata))
                # 메타의 SOS(bug_reports) 트림
                reports = _meta_now.get("admin_master", {}).get("bug_reports", [])
                if len(reports) > MAX_SOS_TOTAL:
                    done = [r for r in reports if r["status"] == "✔️ 처리완료"]
                    pending = [r for r in reports if r["status"] != "✔️ 처리완료"]
                    _meta_now["admin_master"]["bug_reports"] = pending + done[-(MAX_SOS_TOTAL - len(pending)):]
                    save_meta_data(_meta_now)
                get_all_teams.clear(); get_cached_team.clear()
                after = estimate_db_size(get_cached_meta()) + sum(estimate_db_size(t) for t in get_all_teams().values())
                freed = before - after
                st.success(f"✅ 완료! {db_size_label(freed)} 절약됨 ({db_size_label(before)} → {db_size_label(after)})")
                st.rerun()

        st.write("---")
        st.markdown("#### 📊 팀별 용량 점유율")
        size_rows = []
        for l_id, u_info in _db.get("users_master", {}).items():
            t_id = u_info["team_id"]
            t_info = get_all_teams().get(t_id, {})
            t_size = estimate_db_size(t_info)
            chat_size = estimate_db_size({"c": t_info.get("chats_archive", [])})
            story_size = estimate_db_size({"s": t_info.get("stories", [])})
            size_rows.append({
                "조 이름": t_info.get("team_name", "설정중"),
                "전체": db_size_label(t_size),
                "채팅": db_size_label(chat_size),
                "스토리": db_size_label(story_size),
                "채팅 수": len(t_info.get("chats_archive", [])),
                "스토리 수": len(t_info.get("stories", [])),
                "바이트": t_size
            })
        if size_rows:
            size_df = pd.DataFrame(size_rows).sort_values("바이트", ascending=False).drop(columns="바이트")
            st.dataframe(size_df, use_container_width=True)

    # =========================================================
    # --- 관리자 탭 8: 채팅 모니터링 (DM 감시 + 욕설 탐지) ---
    # =========================================================
    with admin_tabs[8]:
        st.subheader("🔍 채팅 모니터링 센터")
        st.caption("모든 팀의 채팅방 대화 내용을 열람하고 욕설/불량 키워드를 탐지합니다.")

        # 욕설/불량 키워드 목록 (관리자가 편집 가능)
        _db = get_cached_meta()
        default_bad_words = _db["admin_master"].get("bad_words",
            ["욕설1", "욕설2", "병신", "씨발", "개새끼", "지랄", "ㅅㅂ", "ㅂㅅ", "새끼", "미친놈", "꺼져"])

        with st.expander("⚙️ 욕설 키워드 목록 편집", expanded=False):
            bad_words_input = st.text_area(
                "탐지할 단어/구문 목록 (쉼표로 구분)",
                value=", ".join(default_bad_words),
                key="bad_words_editor"
            )
            if st.button("💾 키워드 저장", key="save_bad_words"):
                new_bw = [w.strip() for w in bad_words_input.split(",") if w.strip()]
                _db2 = get_cached_meta()
                _db2["admin_master"]["bad_words"] = new_bw
                save_meta_data(_db2)
                st.success(f"✅ {len(new_bw)}개 키워드 저장 완료")
                st.rerun()

        def detect_bad_words(text: str, bad_words: list) -> list:
            found = []
            t_lower = text.lower()
            for w in bad_words:
                if w.lower() in t_lower:
                    found.append(w)
            return found

        st.write("---")
        col_mon1, col_mon2 = st.columns([1, 2])

        # 팀/방 선택
        with col_mon1:
            st.markdown("#### 🏢 팀 선택")
            if not _db["users_master"]:
                st.info("등록된 팀이 없습니다.")
            else:
                mon_team_opts = {}
                for l_id, u_info in _db["users_master"].items():
                    t_id = u_info["team_id"]
                    t_info = get_all_teams().get(t_id, {})
                    lbl = f"{t_info.get('team_name','설정중')} ({l_id})"
                    mon_team_opts[lbl] = t_id

                sel_mon_team = st.selectbox("팀 선택", list(mon_team_opts.keys()), key="mon_team_sel")
                mon_t_id = mon_team_opts[sel_mon_team]
                mon_team_data = get_cached_team(mon_t_id) or {}

                rooms = mon_team_data.get("chat_rooms", [])
                if rooms:
                    room_opts = {f"💬 {r['title']} ({len(r['members'])}명)": r["room_id"] for r in rooms}
                    sel_room_label = st.selectbox("채팅방 선택", ["전체 대화 보기"] + list(room_opts.keys()), key="mon_room_sel")
                else:
                    sel_room_label = "전체 대화 보기"

                # 욕설 탐지 요약
                st.write("---")
                st.markdown("#### 🚨 욕설 탐지 요약")
                all_chats = mon_team_data.get("chats_archive", [])
                flagged = []
                for c in all_chats:
                    hits = detect_bad_words(c.get("msg",""), default_bad_words)
                    if hits:
                        flagged.append({
                            "보낸사람": c.get("sender","?"),
                            "메시지": c.get("msg","")[:40],
                            "탐지어": ", ".join(hits),
                            "시간": c.get("time",""),
                            "날짜": c.get("date",""),
                        })
                if flagged:
                    st.error(f"🚨 총 **{len(flagged)}개** 불량 메시지 탐지됨")
                    flag_df = pd.DataFrame(flagged)
                    st.dataframe(flag_df, use_container_width=True)

                    # 욕설 사용자 랭킹
                    flag_sender = {}
                    for f in flagged:
                        flag_sender[f["보낸사람"]] = flag_sender.get(f["보낸사람"], 0) + 1
                    rank_df = pd.DataFrame(list(flag_sender.items()), columns=["조원", "탐지 횟수"]).sort_values("탐지 횟수", ascending=False)
                    st.markdown("**욕설 사용자 순위:**")
                    st.dataframe(rank_df, use_container_width=True)

                    if st.button("🗑️ 탐지된 욕설 메시지 전체 삭제", key="del_bad_msgs", type="primary"):
                        t2 = get_cached_team(mon_t_id) or {}
                        bw_lower = [w.lower() for w in default_bad_words]
                        t2["chats_archive"] = [
                            c for c in t2.get("chats_archive", [])
                            if not any(w in c.get("msg","").lower() for w in bw_lower)
                        ]
                        save_team_data(mon_t_id, t2)
                        # 활동 로그에 기록 (메타)
                        meta_db = get_cached_meta()
                        meta_db["admin_master"].setdefault("activity_logs", []).insert(0, {
                            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "admin": st.session_state.current_user,
                            "action": f"욕설 메시지 {len(flagged)}건 삭제",
                            "target": mon_team_data.get("team_name", mon_t_id)
                        })
                        save_meta_data(meta_db)
                        st.success(f"✅ {len(flagged)}개 메시지 삭제 완료")
                        st.rerun()
                else:
                    st.success("✅ 탐지된 욕설 없음")

        with col_mon2:
            st.markdown("#### 💬 채팅 내용 열람")
            if not _db["users_master"]:
                st.stop()

            all_chats_view = mon_team_data.get("chats_archive", [])

            # 방 필터
            if sel_room_label != "전체 대화 보기" and rooms:
                sel_room_id = room_opts[sel_room_label]
                filtered_chats = [c for c in all_chats_view if c.get("room_id") == sel_room_id]
            else:
                filtered_chats = all_chats_view

            # 키워드 검색
            col_sf1, col_sf2 = st.columns([3, 1])
            with col_sf1:
                search_kw = st.text_input("🔎 키워드 검색", placeholder="특정 단어 검색...", key="chat_search_kw")
                if search_kw.strip():
                    filtered_chats = [c for c in filtered_chats if search_kw.lower() in c.get("msg","").lower()]
            with col_sf2:
                only_bad = st.toggle("🚨 불량만 보기", value=False, key="chat_only_bad")
                if only_bad:
                    filtered_chats = [c for c in filtered_chats if detect_bad_words(c.get("msg",""), default_bad_words)]

            # 발신자 필터
            senders = list(set(c.get("sender","?") for c in all_chats_view))
            sel_sender = st.selectbox("발신자 필터", ["전체"] + senders, key="chat_sender_filter")
            if sel_sender != "전체":
                filtered_chats = [c for c in filtered_chats if c.get("sender") == sel_sender]

            bad_count = sum(1 for c in filtered_chats if detect_bad_words(c.get("msg",""), default_bad_words))
            if bad_count:
                st.markdown(f"총 **{len(filtered_chats)}개** 메시지 &nbsp;|&nbsp; 🚨 **불량 {bad_count}건**", unsafe_allow_html=True)
            else:
                st.caption(f"총 {len(filtered_chats)}개 메시지 | 불량 없음 ✅")

            chat_container = st.container(height=480)
            with chat_container:
                if not filtered_chats:
                    st.caption("표시할 메시지가 없습니다.")
                else:
                    for i, c in enumerate(reversed(filtered_chats[-100:])):
                        bad_hits = detect_bad_words(c.get("msg",""), default_bad_words)
                        bg = "#fff0f0" if bad_hits else "#f9f9f9"
                        border = "2px solid #e74c3c" if bad_hits else "1px solid #ddd"
                        flag_icon = "🚨 " if bad_hits else ""
                        # 어느 방인지 표시
                        room_name = "?"
                        for r in rooms:
                            if r["room_id"] == c.get("room_id"):
                                room_name = r["title"]
                                break
                        st.markdown(
                            f"<div style='background:{bg};border:{border};border-radius:8px;padding:8px 12px;margin-bottom:6px;color:#111111;'>"
                            f"<b style='color:#111111;'>{flag_icon}{c.get('sender','?')}</b> "
                            f"<small style='color:#555555;'>[ {room_name} · {c.get('date','')} {c.get('time','')} ]</small><br>"
                            f"<span style='color:#111111;'>{c.get('msg','')}</span>"
                            + (f"<br><small style='color:#e74c3c;'>⚠️ 탐지어: {', '.join(bad_hits)}</small>" if bad_hits else "")
                            + "</div>",
                            unsafe_allow_html=True
                        )
                        # 메시지 단건 삭제 (관리자 권한)
                        if st.button("🗑️ 삭제", key=f"del_msg_{i}_{c.get('time','')}_{c.get('sender','')}"):
                            t2_obj = get_cached_team(mon_t_id) or {}
                            t2_chats = t2_obj.get("chats_archive", [])
                            # 발신자+시간+내용으로 매칭 삭제
                            t2_obj["chats_archive"] = [
                                x for x in t2_chats
                                if not (x.get("sender") == c.get("sender") and
                                        x.get("time") == c.get("time") and
                                        x.get("msg") == c.get("msg"))
                            ]
                            save_team_data(mon_t_id, t2_obj)
                            meta_db = get_cached_meta()
                            meta_db["admin_master"].setdefault("activity_logs", []).insert(0, {
                                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "admin": st.session_state.current_user,
                                "action": f"메시지 강제 삭제: [{c.get('sender')}] {c.get('msg','')[:30]}",
                                "target": mon_team_data.get("team_name", mon_t_id)
                            })
                            save_meta_data(meta_db)
                            st.rerun()

    # =============================================
    # --- 관리자 탭 9: 활동 로그 ---
    # =============================================
    with admin_tabs[9]:
        st.subheader("📋 관리자 활동 로그")
        st.caption("관리자가 수행한 모든 작업 이력이 자동으로 기록됩니다.")

        _db = get_cached_meta()
        logs = _db["admin_master"].get("activity_logs", [])

        col_log1, col_log2 = st.columns([3, 1])
        with col_log1:
            log_filter = st.text_input("🔎 로그 검색", placeholder="작업 내용, 대상 팀 등", key="log_search")
        with col_log2:
            if st.button("🗑️ 로그 전체 삭제", key="clear_logs_btn"):
                _db2 = get_cached_meta()
                _db2["admin_master"]["activity_logs"] = []
                save_meta_data(_db2)
                st.rerun()

        filtered_logs = logs
        if log_filter.strip():
            filtered_logs = [
                l for l in logs
                if log_filter.lower() in l.get("action","").lower()
                or log_filter.lower() in l.get("target","").lower()
            ]

        if not filtered_logs:
            st.info("📋 기록된 활동 로그가 없습니다." if not logs else "검색 결과가 없습니다.")
        else:
            st.caption(f"총 {len(filtered_logs)}건 (전체 {len(logs)}건)")

            # 통계
            if logs:
                action_types = {}
                for l in logs:
                    a = l.get("action","")[:20]
                    action_types[a] = action_types.get(a, 0) + 1
                top3 = sorted(action_types.items(), key=lambda x: x[1], reverse=True)[:3]
                cols_stat = st.columns(3)
                for i, (act, cnt) in enumerate(top3):
                    cols_stat[i].metric(act, f"{cnt}회")
                st.write("---")

            for l in filtered_logs[:100]:  # 최근 100건
                with st.container(border=True):
                    c_l1, c_l2 = st.columns([4, 1])
                    with c_l1:
                        st.markdown(f"**{l.get('action','?')}**")
                        st.caption(f"👤 관리자: {l.get('admin','?')} | 🎯 대상: {l.get('target','?')} | 🕐 {l.get('time','?')}")
                    with c_l2:
                        action_text = l.get("action","")
                        if "삭제" in action_text:
                            st.error("삭제")
                        elif "변경" in action_text or "저장" in action_text:
                            st.warning("수정")
                        elif "발송" in action_text or "전송" in action_text:
                            st.info("발송")
                        else:
                            st.success("기타")

    # =============================================
    # --- 관리자 탭 10: 보안 설정 ---
    # =============================================
    with admin_tabs[10]:
        st.subheader("⚙️ 보안 및 시스템 설정")

        _db = get_cached_meta()

        # 관리자 계정 변경
        st.markdown("#### 🔑 관리자 계정 변경")
        with st.form("admin_profile_form"):
            new_ad_id = st.text_input("새 관리자 ID", value=_db["admin_master"]["admin_id"]).strip()
            new_ad_pw = st.text_input("새 관리자 비밀번호", value=_db["admin_master"]["admin_pw"], type="password").strip()
            new_ad_pw2 = st.text_input("새 비밀번호 확인", type="password").strip()
            if st.form_submit_button("💾 계정 정보 변경"):
                if not (new_ad_id and new_ad_pw):
                    st.error("ID와 비밀번호를 모두 입력하세요.")
                elif new_ad_pw != new_ad_pw2:
                    st.error("비밀번호가 일치하지 않습니다.")
                else:
                    _db2 = get_cached_meta()
                    _db2["admin_master"]["admin_id"] = new_ad_id
                    _db2["admin_master"]["admin_pw"] = new_ad_pw
                    _db2["admin_master"].setdefault("activity_logs", []).insert(0, {
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "admin": st.session_state.current_user,
                        "action": "관리자 계정 정보 변경",
                        "target": "시스템"
                    })
                    save_meta_data(_db2)
                    st.success("✅ 관리자 계정이 변경되었습니다. 다음 로그인부터 적용됩니다.")
                    st.rerun()

        st.write("---")
        st.markdown("#### 🛡️ 보안 정책 설정")

        sec_settings = _db["admin_master"].get("security_settings", {})
        col_sec1, col_sec2 = st.columns(2)
        with col_sec1:
            auto_kick_days = st.number_input(
                "비활성 팀 자동 경고 기간 (일)",
                min_value=7, max_value=365, value=sec_settings.get("auto_kick_days", 30),
                help="마지막 활동으로부터 이 기간이 지나면 현황 대시보드에 경고 표시"
            )
            max_login_attempts = st.number_input(
                "로그인 허용 최대 조원 수 (팀당)",
                min_value=1, max_value=50, value=sec_settings.get("max_members", 20),
                help="한 팀에 등록 가능한 최대 조원 수"
            )
        with col_sec2:
            chat_monitor_on = st.toggle(
                "💬 욕설 자동 탐지 알림",
                value=sec_settings.get("chat_monitor_on", True),
                help="새 욕설 메시지가 탐지되면 현황 대시보드에 경고 배너 표시"
            )
            new_team_approval = st.toggle(
                "🔒 신규 팀 등록 잠금",
                value=sec_settings.get("new_team_lock", False),
                help="ON 시 새로운 팀 등록(조장 가입)이 차단됩니다"
            )

        if st.button("💾 보안 정책 저장", type="primary"):
            _db2 = get_cached_meta()
            _db2["admin_master"]["security_settings"] = {
                "auto_kick_days": auto_kick_days,
                "max_members": max_login_attempts,
                "chat_monitor_on": chat_monitor_on,
                "new_team_lock": new_team_approval,
            }
            _db2["admin_master"].setdefault("activity_logs", []).insert(0, {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "admin": st.session_state.current_user,
                "action": "보안 정책 설정 변경",
                "target": "시스템"
            })
            save_meta_data(_db2)
            st.success("✅ 보안 정책이 저장되었습니다.")
            st.rerun()

        st.write("---")
        st.markdown("#### 📊 접속 통계")
        # 각 팀의 최근 활동 시각 파악
        stat_rows = []
        for l_id, u_info in _db.get("users_master", {}).items():
            t_id = u_info["team_id"]
            t_info = get_all_teams().get(t_id, {})
            chats = t_info.get("chats_archive", [])
            stories = t_info.get("stories", [])
            last_active = "활동 없음"
            all_times = []
            for c in chats:
                if c.get("date") and c.get("time"):
                    all_times.append(f"{c['date']} {c['time']}")
            for s in stories:
                if s.get("time"):
                    all_times.append(s["time"])
            if all_times:
                last_active = max(all_times)
            stat_rows.append({
                "조 이름": t_info.get("team_name","설정중"),
                "조장 ID": l_id,
                "마지막 활동": last_active,
                "채팅 수": len(chats),
                "스토리 수": len(stories),
            })
        if stat_rows:
            stat_df = pd.DataFrame(stat_rows).sort_values("마지막 활동", ascending=False)
            st.dataframe(stat_df, use_container_width=True)

        st.write("---")
        st.error("☣️ 위험 구역 — DB 전체 포맷")
        st.caption("이 버튼을 누르면 **모든** 팀 데이터가 영구 삭제됩니다.")
        confirm_fmt = st.checkbox("모든 책임을 지며 DB를 전체 포맷하겠습니다.")
        if st.button("⚠️ DB 전체 포맷 실행"):
            if confirm_fmt:
                _old_meta = get_cached_meta()
                reset_meta = {
                    "users_master": {},
                    "teams_index": {},
                    "admin_master": {
                        "admin_id": _old_meta["admin_master"]["admin_id"],
                        "admin_pw": _old_meta["admin_master"]["admin_pw"],
                        "system_notices": [],
                        "bug_reports": [],
                        "activity_logs": [],
                        "bad_words": _old_meta["admin_master"].get("bad_words", []),
                        "security_settings": _old_meta["admin_master"].get("security_settings", {}),
                    }
                }
                # 모든 팀 row 삭제
                for _tid in list(get_all_teams().keys()):
                    try:
                        supabase.table("startree_teams").delete().eq("id", _tid).execute()
                    except Exception:
                        pass
                save_meta_data(reset_meta)
                get_cached_team.clear()
                get_all_teams.clear()
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
        fresh = get_cached_meta()
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
                pin_notice = st.checkbox("📌 이 공지를 상단에 고정", value=False)
                if st.form_submit_button("📢 공지 게시", type="primary"):
                    if notice_text.strip():
                        file_name = "없음"
                        file_b64 = None
                        if uploaded_file:
                            raw_f = uploaded_file.read()
                            if len(raw_f) / 1024 > MAX_FILE_KB:
                                st.error(f"❌ 첨부파일이 너무 큽니다. {MAX_FILE_KB//1024}MB 이하만 업로드 가능합니다.")
                                st.stop()
                            fname_lower = uploaded_file.name.lower()
                            if fname_lower.endswith((".png", ".jpg", ".jpeg")):
                                file_b64 = compress_image_b64(raw_f)
                            else:
                                file_b64 = base64.b64encode(raw_f).decode("utf-8")
                            file_name = uploaded_file.name
                        _db2 = get_cached_team(st.session_state.current_team_id)
                        _db2.setdefault("notices", []).insert(0, {
                            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "content": notice_text,
                            "file_name": file_name,
                            "file_bytes": file_b64,
                            "pinned": pin_notice
                        })
                        save_team_data(st.session_state.current_team_id, _db2)
                        st.success("✅ 공지가 게시되었습니다.")
                        st.rerun()
        else:
            st.caption("공지사항 편집 권한은 조장 전용입니다.")

        st.write("---")

        @st.fragment(run_every=15)
        def show_notices_live():
            fresh = get_cached_team(st.session_state.current_team_id)
            fresh_team = (fresh or {})
            raw_notices = fresh_team.get("notices", [])
            if not raw_notices:
                st.caption("등록된 공지사항이 없습니다.")
                return
            # 핀 고정 공지를 앞으로
            pinned = [(i, n) for i, n in enumerate(raw_notices) if n.get("pinned")]
            unpinned = [(i, n) for i, n in enumerate(raw_notices) if not n.get("pinned")]
            sorted_notices = pinned + unpinned
            st.caption(f"📋 총 {len(raw_notices)}건 | 📌 고정 {len(pinned)}건")
            for real_idx, n in sorted_notices:
                is_pinned = n.get("pinned", False)
                with st.container(border=True):
                    col_nt, col_nd = st.columns([5, 1])
                    with col_nt:
                        pin_label = "📌 **[고정]** " if is_pinned else ""
                        st.caption(f"📅 {n['date']}")
                        st.markdown(f"{pin_label}{n['content']}")
                        if n.get("file_bytes"):
                            file_data = base64.b64decode(n["file_bytes"]) if isinstance(n["file_bytes"], str) else n["file_bytes"]
                            st.download_button(f"📎 {n['file_name']}", data=file_data, file_name=n["file_name"], key=f"notice_dl_{real_idx}")
                    with col_nd:
                        if is_leader:
                            pin_btn_label = "📌" if not is_pinned else "📍"
                            pin_btn_help = "고정" if not is_pinned else "고정 해제"
                            if st.button(pin_btn_label, key=f"pin_notice_{real_idx}", help=pin_btn_help):
                                _db2 = get_cached_team(st.session_state.current_team_id)
                                _db2["notices"][real_idx]["pinned"] = not is_pinned
                                save_team_data(st.session_state.current_team_id, _db2)
                                st.rerun()
                            if st.button("🗑️", key=f"del_notice_{real_idx}"):
                                _db2 = get_cached_team(st.session_state.current_team_id)
                                _db2["notices"].pop(real_idx)
                                save_team_data(st.session_state.current_team_id, _db2)
                                st.rerun()

        show_notices_live()

    # --- 탭: 스토리 피드 ---
    with tab_map["✨ 스토리 피드"]:
        st.subheader("📸 팀 스토리 피드")
        col_up, col_view = st.columns([2, 3])

        with col_up:
            with st.form("story_form", clear_on_submit=True):
                st_text = st.text_area("업무 피드 작성")
                st_media = st.file_uploader("미디어 첨부 (이미지 권장, 5MB 이하)", type=["png", "jpg", "jpeg", "mp4", "mp3", "wav"])
                if st.form_submit_button("📤 피드 게시") and st_text.strip():
                    media_type = None
                    media_data = None
                    if st_media:
                        raw = st_media.read()
                        fname = st_media.name.lower()
                        size_kb = len(raw) / 1024
                        if fname.endswith((".png", ".jpg", ".jpeg")):
                            media_type = "image"
                            media_data = compress_image_b64(raw)  # 자동 압축
                        elif fname.endswith(".mp4"):
                            if size_kb > MAX_VIDEO_KB:
                                st.error(f"❌ 영상 파일이 너무 큽니다. {MAX_VIDEO_KB//1000}MB 이하만 업로드 가능합니다.")
                                st.stop()
                            media_type = "video"
                            media_data = base64.b64encode(raw).decode("utf-8")
                        elif fname.endswith((".mp3", ".wav")):
                            if size_kb > MAX_AUDIO_KB:
                                st.error(f"❌ 음성 파일이 너무 큽니다. {MAX_AUDIO_KB//1000}MB 이하만 업로드 가능합니다.")
                                st.stop()
                            media_type = "audio"
                            media_data = base64.b64encode(raw).decode("utf-8")
                    _db2 = get_cached_team(st.session_state.current_team_id)
                    # 스토리 최대 개수 초과 시 오래된 것 자동 삭제
                    stories_list = _db2.setdefault("stories", [])
                    if len(stories_list) >= MAX_STORIES:
                        stories_list.pop()  # 가장 오래된 스토리 제거
                    _db2.setdefault("stories", []).insert(0, {
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
                    save_team_data(st.session_state.current_team_id, _db2)
                    st.rerun()

        with col_view:
            @st.fragment(run_every=15)
            def show_stories_live():
                fresh = get_cached_team(st.session_state.current_team_id)
                fresh_team = (fresh or {})
                for s in fresh_team.get("stories", []):
                    s_id = s.get("story_id", s.get("time", ""))
                    with st.container(border=True):
                        col_sh, col_sdel = st.columns([5, 1])
                        with col_sh:
                            st.markdown(f"**{s['user']}** · *{s['time']}*")
                        with col_sdel:
                            if is_leader or s.get("user") == my_chat_name:
                                if st.button("🗑️", key=f"del_story_{s_id}"):
                                    _db2 = get_cached_team(st.session_state.current_team_id)
                                    _db2["stories"] = [
                                        x for x in _db2.get("stories", [])
                                        if x.get("story_id") != s_id
                                    ]
                                    save_team_data(st.session_state.current_team_id, _db2)
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
                            _db2 = get_cached_team(st.session_state.current_team_id)
                            for os_ in _db2.get("stories", []):
                                if os_.get("story_id") == s_id:
                                    os_["likes"] = os_.get("likes", 0) + 1
                                    os_.setdefault("liked_by", []).append(my_chat_name)
                                    break
                            save_team_data(st.session_state.current_team_id, _db2)
                            st.rerun()

                        for cm in s.get("comments", []):
                            st.markdown(f"💬 **{cm['writer']}**: {cm['text']}")

                        with st.form(f"comment_{s_id}", clear_on_submit=True):
                            c_text = st.text_input("댓글", key=f"cm_{s_id}")
                            if st.form_submit_button("댓글 달기") and c_text.strip():
                                _db2 = get_cached_team(st.session_state.current_team_id)
                                for os_ in _db2.get("stories", []):
                                    if os_.get("story_id") == s_id:
                                        os_.setdefault("comments", []).append({"writer": my_chat_name, "text": c_text.strip()})
                                        break
                                save_team_data(st.session_state.current_team_id, _db2)
                                st.rerun()

            show_stories_live()

    # --- 탭: 기여도 ---
    with tab_map["📊 기여도"]:
        st.subheader("📊 기여도 주식 대시보드")

        if is_leader:
            with st.expander("⚙️ 기여도 수동 조정 (조장 전용)"):
                _db = get_cached_team(st.session_state.current_team_id)
                cur_stocks = (_db or {}).get("stocks", {})
                if cur_stocks:
                    adj_target = st.selectbox("조원 선택", list(cur_stocks.keys()), key="adj_stock_target")
                    adj_val = st.number_input("조정값 (양수: 증가, 음수: 감소)", value=1000, step=500, key="adj_stock_val")
                    adj_reason = st.text_input("사유", placeholder="예: 발표 준비 추가 기여", key="adj_reason")
                    if st.button("기여도 조정 적용"):
                        if not adj_reason.strip():
                            st.warning("⚠️ 사유를 입력해주세요.")
                        else:
                            _db2 = get_cached_team(st.session_state.current_team_id)
                            t = _db2
                            cur_val = t["stocks"][adj_target][-1]
                            new_val = max(0, cur_val + adj_val)
                            t["stocks"][adj_target].append(new_val)
                            t.setdefault("stock_logs", {}).setdefault(adj_target, []).append({
                                "type": "plus" if adj_val >= 0 else "minus",
                                "val": abs(adj_val),
                                "reason": adj_reason.strip()
                            })
                            save_team_data(st.session_state.current_team_id, _db2)
                            direction = f"+{adj_val:,}P" if adj_val >= 0 else f"{adj_val:,}P"
                            st.toast(f"✅ {adj_target} 기여도 조정 완료: {cur_val:,}P → {new_val:,}P ({direction})")
                            st.rerun()

        @st.fragment(run_every=15)
        def show_stocks_live():
            fresh = get_cached_team(st.session_state.current_team_id)
            fresh_team = (fresh or {})
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
            chart_tabs = st.tabs(["📊 개인 추이", "📈 전체 비교"])
            with chart_tabs[0]:
                sel_user = st.selectbox("추이 조회", list(stocks.keys()), key="stock_detail_sel")
                if sel_user and stocks.get(sel_user):
                    chart_df = pd.DataFrame({"기여도(P)": stocks[sel_user]})
                    st.line_chart(chart_df)
                    logs = fresh_team.get("stock_logs", {}).get(sel_user, [])
                    if logs:
                        st.markdown("**최근 변동 이력 (최근 10건)**")
                        log_df = pd.DataFrame(reversed(logs[-10:]))
                        st.dataframe(log_df, use_container_width=True)
            with chart_tabs[1]:
                # 전체 조원 꺾은선 비교
                max_len = max((len(v) for v in stocks.values()), default=1)
                compare_data = {}
                for name, vals in stocks.items():
                    # 짧은 히스토리는 첫값으로 앞을 채워 길이 맞춤
                    padded = ([vals[0]] * (max_len - len(vals))) + vals if len(vals) < max_len else vals
                    compare_data[name] = padded
                compare_df = pd.DataFrame(compare_data)
                compare_df.index.name = "단계"
                st.line_chart(compare_df)
                st.caption("각 선은 조원별 기여도 추이입니다. 결재/반려/수동조정 시 갱신됩니다.")

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
                    sel_date_obj = st.date_input("날짜 (범위 외도 가능)", value=date_type.today(), key="cal_sel_date")
                    sel_date = str(sel_date_obj)
                with col_r2:
                    sel_worker = st.selectbox("담당자", m_names if m_names else ["없음"], key="cal_sel_worker")
                with col_r3:
                    sel_content = st.text_input("업무 내용", key="cal_content")
                if st.button("➕ 업무 추가", type="primary"):
                    if sel_content.strip():
                        _db2 = get_cached_team(st.session_state.current_team_id)
                        cal = _db2.setdefault("calendar_events", {})
                        cal.setdefault(sel_date, []).append({
                            "id": str(uuid.uuid4()),
                            "content": sel_content.strip(),
                            "status": "⏳",
                            "worker": sel_worker
                        })
                        save_team_data(st.session_state.current_team_id, _db2)
                        st.success("✅ 업무가 추가되었습니다.")
                        st.rerun()

        st.write("---")

        @st.fragment(run_every=15)
        def show_calendar_live():
            fresh = get_cached_team(st.session_state.current_team_id)
            fresh_team = (fresh or {})
            all_cal = fresh_team.get("calendar_events", {})
            today_str = str(date_type.today())

            # 프로젝트 범위 날짜 + 범위 밖 등록된 날짜 모두 합쳐 정렬
            all_dates = sorted(set(date_strs) | set(all_cal.keys()))

            # 전체 진행률 계산
            all_evs = [ev for evs in all_cal.values() for ev in evs]
            total_ev = len(all_evs)
            done_ev = sum(1 for ev in all_evs if "✔️" in ev.get("status",""))
            pending_ev = sum(1 for ev in all_evs if "⏳" in ev.get("status","⏳"))
            if total_ev > 0:
                prog = done_ev / total_ev
                c_p1, c_p2, c_p3 = st.columns(3)
                c_p1.metric("📋 전체 업무", f"{total_ev}건")
                c_p2.metric("✅ 완료", f"{done_ev}건")
                c_p3.metric("⏳ 대기", f"{pending_ev}건")
                st.progress(prog, text=f"진행률 {prog*100:.0f}%")
                st.write("---")

            for d_str in all_dates:
                day_events = all_cal.get(d_str, [])
                is_today = (d_str == today_str)
                is_in_range = d_str in date_strs
                prefix = "🔴 " if is_today else ("📌 " if not is_in_range else "")
                suffix = "  ← 오늘" if is_today else ("  (범위 외)" if not is_in_range else "")
                header_label = f"{prefix}{d_str}{suffix}"

                if day_events:
                    with st.expander(f"{header_label}  ({len(day_events)}건)", expanded=is_today):
                        for idx, ev in enumerate(day_events):
                            c_d, c_w, c_c, c_s, c_ops = st.columns([1.5, 1.5, 4, 1.2, 1.8])
                            c_d.write(d_str)
                            c_w.write(f"👤 {ev.get('worker','?')}")
                            c_c.write(ev.get("content", ""))
                            status = ev.get("status", "⏳")
                            if "✔️" in status:
                                c_s.success("완료", icon="✔️")
                            elif "❌" in status:
                                c_s.error("반려", icon="❌")
                            else:
                                c_s.warning("대기", icon="⏳")
                            if is_leader:
                                with c_ops:
                                    b1, b2, b3 = st.columns(3)
                                    ev_id = ev.get("id", f"{d_str}_{idx}")
                                    with b1:
                                        if st.button("✔️", key=f"v_{ev_id}"):
                                            _db2 = get_cached_team(st.session_state.current_team_id)
                                            t2 = _db2
                                            for ev2 in t2.get("calendar_events", {}).get(d_str, []):
                                                if ev2.get("id") == ev_id:
                                                    ev2["status"] = "✔️"
                                                    tw = ev2["worker"]
                                                    if tw in t2.get("stocks", {}):
                                                        t2["stocks"][tw].append(t2["stocks"][tw][-1] + 3000)
                                                        t2.setdefault("stock_logs", {}).setdefault(tw, []).append({"type": "plus", "val": 3000, "reason": f"{d_str} 결재"})
                                                    break
                                            save_team_data(st.session_state.current_team_id, _db2)
                                            st.rerun()
                                    with b2:
                                        if st.button("❌", key=f"x_{ev_id}"):
                                            _db2 = get_cached_team(st.session_state.current_team_id)
                                            t2 = _db2
                                            for ev2 in t2.get("calendar_events", {}).get(d_str, []):
                                                if ev2.get("id") == ev_id:
                                                    ev2["status"] = "❌"
                                                    tw = ev2["worker"]
                                                    if tw in t2.get("stocks", {}):
                                                        t2["stocks"][tw].append(max(0, t2["stocks"][tw][-1] - 3000))
                                                        t2.setdefault("stock_logs", {}).setdefault(tw, []).append({"type": "minus", "val": 3000, "reason": f"{d_str} 반려"})
                                                    break
                                            save_team_data(st.session_state.current_team_id, _db2)
                                            st.rerun()
                                    with b3:
                                        if st.button("🗑️", key=f"del_{ev_id}"):
                                            _db2 = get_cached_team(st.session_state.current_team_id)
                                            cal = _db2.get("calendar_events", {})
                                            cal[d_str] = [x for x in cal.get(d_str, []) if x.get("id") != ev_id]
                                            save_team_data(st.session_state.current_team_id, _db2)
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
            _col_sd, _col_ed = st.columns(2)
            with _col_sd:
                try:
                    _start_def = date_type.fromisoformat(team_data.get("start_date", str(date_type.today())))
                except Exception:
                    _start_def = date_type.today()
                edit_start_d = st.date_input("📅 프로젝트 시작일", value=_start_def, key="edit_start_d")
            with _col_ed:
                try:
                    _end_def = date_type.fromisoformat(team_data.get("end_date", str(date_type.today())))
                except Exception:
                    _end_def = date_type.today()
                edit_end_d = st.date_input("📅 프로젝트 마감일", value=_end_def, key="edit_end_d")
            if st.button("💾 기본 정보 저장"):
                _db2 = get_cached_team(st.session_state.current_team_id)
                _db2["team_name"] = edit_tname.strip() or team_data.get("team_name", "우리팀")
                _db2["subject"] = edit_subj.strip()
                _db2["start_date"] = str(edit_start_d)
                _db2["end_date"] = str(edit_end_d)
                save_team_data(st.session_state.current_team_id, _db2)
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
                _db2 = get_cached_team(st.session_state.current_team_id)
                t2 = _db2
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
                save_team_data(st.session_state.current_team_id, _db2)
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
                    _db2 = get_cached_team(st.session_state.current_team_id)
                    _db2.setdefault("chat_rooms", []).append({
                        "room_id": str(uuid.uuid4()),
                        "title": room_title,
                        "members": choose_members
                    })
                    save_team_data(st.session_state.current_team_id, _db2)
                    st.success(f"✅ '{room_title}' 채팅방이 생성되었습니다!")
                    st.rerun()

        st.write("---")

        @st.fragment(run_every=4)
        def show_chat_live():
            fresh = get_cached_team(st.session_state.current_team_id)
            fresh_team = (fresh or {})
            my_rooms = [r for r in fresh_team.get("chat_rooms", []) if my_chat_name in r.get("members", [])]
            all_chats = fresh_team.get("chats_archive", [])

            col_rooms, col_chat = st.columns([1, 2])

            with col_rooms:
                st.markdown("**내 채팅방**")
                if not my_rooms:
                    st.caption("참여 중인 채팅방이 없습니다.")
                for rm in my_rooms:
                    is_active = (st.session_state.active_chat_room_id == rm["room_id"])
                    # 해당 방의 최근 메시지 미리보기
                    room_msgs = [c for c in all_chats if c.get("room_id") == rm["room_id"]]
                    last_msg = f" · {room_msgs[-1]['msg'][:10]}..." if room_msgs else ""
                    unread_count = sum(1 for c in room_msgs[-20:] if c.get("sender") != my_chat_name)
                    badge = f" 🔴{unread_count}" if unread_count > 0 and not is_active else ""
                    label = f"{'🟢 ' if is_active else '💬 '}{rm['title']} ({len(rm['members'])}명){badge}"
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
                        if is_leader:
                            new_room_name = st.text_input("방 이름 변경", value=target_room["title"], key=f"rename_{target_room['room_id']}", label_visibility="collapsed")
                            if st.button("✏️ 이름 변경", key=f"rename_btn_{target_room['room_id']}", use_container_width=True):
                                if new_room_name.strip() and new_room_name.strip() != target_room["title"]:
                                    _db2 = get_cached_team(st.session_state.current_team_id)
                                    for r in _db2.get("chat_rooms", []):
                                        if r["room_id"] == target_room["room_id"]:
                                            r["title"] = new_room_name.strip()
                                            break
                                    save_team_data(st.session_state.current_team_id, _db2)
                                    st.rerun()
                        if st.button("🚪 나가기", key=f"exit_{target_room['room_id']}", use_container_width=True):
                            _db2 = get_cached_team(st.session_state.current_team_id)
                            for r in _db2.get("chat_rooms", []):
                                if r["room_id"] == target_room["room_id"] and my_chat_name in r["members"]:
                                    r["members"].remove(my_chat_name)
                                    break
                            save_team_data(st.session_state.current_team_id, _db2)
                            st.session_state.active_chat_room_id = None
                            st.rerun()

                    msg_box = st.container(height=350)
                    with msg_box:
                        room_msgs_all = [c for c in fresh_team.get("chats_archive", []) if c.get("room_id") == target_room["room_id"]]
                        # 최근 50개만 렌더링 (랙 방지)
                        room_msgs = room_msgs_all[-50:]
                        if len(room_msgs_all) > 50:
                            st.caption(f"💬 최근 50개 메시지 표시 중 (전체 {len(room_msgs_all)}개)")
                        last_date = None
                        for chat in room_msgs:
                            chat_date = chat.get("date", "")
                            # 날짜 구분선
                            if chat_date and chat_date != last_date:
                                today_str_c = datetime.now().strftime("%Y-%m-%d")
                                label_date = "오늘" if chat_date == today_str_c else chat_date
                                st.markdown(f"<div style='text-align:center;margin:8px 0;'><span style='background:#e0e0e0;color:#555;font-size:11px;padding:2px 10px;border-radius:10px;'>{label_date}</span></div>", unsafe_allow_html=True)
                                last_date = chat_date
                            is_me = (chat["sender"] == my_chat_name)
                            time_label = chat["time"]
                            attach_html = ""
                            if chat.get("file_name") and chat.get("file_name") != "없음":
                                attach_html = f"<br>📎 <i>{chat['file_name']}</i>"
                            if is_me:
                                st.markdown(
                                    f"<div style='text-align:right;margin-bottom:6px;'>"
                                    f"<span style='background:#ffe600;color:black;padding:5px 10px;border-radius:12px;display:inline-block;max-width:70%;text-align:left;'>"
                                    f"<b>나 ({my_chat_name})</b><br>{chat['msg']}{attach_html}"
                                    f"<br><small style='color:gray;font-size:10px;'>{time_label}</small></span></div>",
                                    unsafe_allow_html=True
                                )
                            else:
                                st.markdown(
                                    f"<div style='text-align:left;margin-bottom:6px;'>"
                                    f"<span style='background:#f1f1f1;color:black;padding:5px 10px;border-radius:12px;display:inline-block;max-width:70%;'>"
                                    f"<b>{chat['sender']}</b><br>{chat['msg']}{attach_html}"
                                    f"<br><small style='color:gray;font-size:10px;'>{time_label}</small></span></div>",
                                    unsafe_allow_html=True
                                )
                            # 첨부파일 다운로드 버튼 (이미지면 인라인 표시)
                            if chat.get("file_bytes") and chat.get("file_name") and chat["file_name"] != "없음":
                                raw_file = base64.b64decode(chat["file_bytes"]) if isinstance(chat["file_bytes"], str) else chat["file_bytes"]
                                fname_lower = chat["file_name"].lower()
                                if any(fname_lower.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]):
                                    st.image(raw_file, caption=chat["file_name"], width=240)
                                else:
                                    st.download_button(
                                        f"📥 {chat['file_name']} 다운로드",
                                        data=raw_file,
                                        file_name=chat["file_name"],
                                        key=f"dl_{chat.get('time','')}_{chat.get('sender','')}_{chat.get('file_name','')}"
                                    )

                    with st.form(f"chat_form_{target_room['room_id']}", clear_on_submit=True):
                        msg_in = st.text_input("메시지 입력", placeholder="메시지를 입력하세요")
                        chat_file = st.file_uploader(
                            "📎 파일 첨부 (선택, 최대 800KB)",
                            type=["png", "jpg", "jpeg", "gif", "pdf", "docx", "xlsx", "pptx", "txt", "zip", "mp3", "wav"],
                            key=f"chat_file_{target_room['room_id']}"
                        )
                        if st.form_submit_button("전송 →"):
                            if msg_in.strip() or chat_file is not None:
                                file_b64 = None
                                file_name = "없음"
                                if chat_file is not None:
                                    raw_chat_file = chat_file.read()
                                    if len(raw_chat_file) / 1024 > MAX_FILE_KB:
                                        st.error(f"❌ 파일 크기가 {MAX_FILE_KB}KB를 초과합니다.")
                                    else:
                                        # 이미지는 압축 후 저장
                                        if chat_file.name.lower().endswith((".png", ".jpg", ".jpeg")):
                                            file_b64 = compress_image_b64(raw_chat_file, MAX_IMAGE_KB)
                                        else:
                                            file_b64 = base64.b64encode(raw_chat_file).decode("utf-8")
                                        file_name = chat_file.name
                                _db2 = get_cached_team(st.session_state.current_team_id)
                                _db2.setdefault("chats_archive", []).append({
                                    "room_id": target_room["room_id"],
                                    "sender": my_chat_name,
                                    "msg": msg_in.strip() if msg_in.strip() else f"📎 파일 전송: {file_name}",
                                    "time": datetime.now().strftime("%H:%M"),
                                    "date": datetime.now().strftime("%Y-%m-%d"),
                                    "file_name": file_name,
                                    "file_bytes": file_b64,
                                })
                                save_team_data(st.session_state.current_team_id, _db2)
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
                        _db2 = get_cached_meta()
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
                        save_meta_data(_db2)
                        st.success("✅ 관리자에게 전송되었습니다!")
                        st.rerun()

        with col_s2:
            st.markdown("#### 📬 내 문의 처리 현황")

            @st.fragment(run_every=10)
            def show_sos_status():
                fresh = get_cached_meta()
                all_reports = fresh["admin_master"].get("bug_reports", [])
                my_reports_with_idx = [(i, r) for i, r in enumerate(all_reports)
                                       if r["team_id"] == st.session_state.current_team_id]
                if not my_reports_with_idx:
                    st.caption("접수한 문의가 없습니다.")
                    return
                for true_idx, rep in reversed(my_reports_with_idx):
                    with st.container(border=True):
                        done = rep["status"] == "✔️ 처리완료"
                        col_sh, col_sdel = st.columns([5, 1])
                        with col_sh:
                            st.markdown(f"**{'🟢 처리완료' if done else '⏳ 검토중'}** | {rep['time']}")
                            st.write(rep["content"])
                            if rep.get("reply"):
                                st.info(f"👑 **관리자 답변:** {rep['reply']}")
                            else:
                                st.caption("관리자 답변 대기 중...")
                        with col_sdel:
                            # 대기중인 문의만 취소 가능
                            if not done:
                                if st.button("❌ 취소", key=f"cancel_sos_{rep['report_id']}", help="대기중인 문의 취소"):
                                    _db2 = get_cached_meta()
                                    _db2["admin_master"]["bug_reports"].pop(true_idx)
                                    save_meta_data(_db2)
                                    st.success("✅ 문의가 취소되었습니다.")
                                    st.rerun()

            show_sos_status()
