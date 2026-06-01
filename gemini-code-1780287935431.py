import streamlit as st
import pandas as pd
import os
import pickle
from datetime import datetime, timedelta

st.set_page_config(page_title="스타트리 (Startree)", page_icon="🌳", layout="wide")

DB_FILE = "startree_data_v3.pkl"

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
            "stories": [],  
            "stocks": {}    
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
                for m in data["members"]:
                    if m["이름"]:
                        data["stocks"][m["이름"]] = [10000]
                data["step"] = 6
                save_data(data)
                st.rerun()

else:
    m_names = [m["이름"] if m["이름"] else f"조원 {idx+1}" for idx, m in enumerate(data["members"])]
    if not m_names:
        m_names = ["등록된 조원 없음"]
        
    leader_name = data["members"][data["leader_idx"]]["이름"] if data["members"] else "없음"
    
    st.title(f"🌳 {data['team_name']} 워크스페이스")
    st.markdown(f"**🎯 주제:** {data['subject']} | **👑 조장:** {leader_name}")
    
    st.write("---")
    st.markdown("### 📸 상단 스토리 하이라이트")
    if data["stories"]:
        num_stories = len(data["stories"])
        story_cols = st.columns(max(num_stories, 5))
        for s_idx, s in enumerate(data["stories"]):
            with story_cols[s_idx % 5]:
                st.markdown(f"🔴 **{s['user']}**")
                st.caption(f"❤️ {s.get('likes', 0)}개 | 💬 {len(s.get('comments', []))}개")
    else:
        st.caption("아직 등록된 스토리가 없습니다.")
    st.write("---")

    # [수정] 탭 구성 변경 및 중복 선언 버그 수정
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📢 홈 및 공지게시판", "✨ 인스타 감성 스토리 피드", "📊 팀플 기여도 주식 차트", "📅 달력 일정 관리", "👥 조원 및 DM 대화방"])
    
    # 탭 1: 홈 및 공지사항
    with tab1:
        st.subheader("📌 팀 공지사항 게시판")
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
        st.markdown("#### 📋 등록된 공지 목록")
        for n in data["notices"]:
            st.info(f"📅 {n['date']}\n\n{n['content']}\n\n📎 파일: {n['file']}")

    # [신규 기능 적용] 탭 2: 인스타 감성 스토리 피드 (멀티미디어 업로드, 좋아요, 댓글 기능)
    with tab2:
        st.subheader("📸 팀플 스토리 업로드 및 소통 광장")
        
        col_up, col_view = st.columns([2, 3])
        
        with col_up:
            st.markdown("#### 📤 나의 팀플 상황 인증하기")
            with st.form("story_upload_form", clear_on_submit=True):
                st_user = st.selectbox("인증할 조원", m_names, key="st_u_box")
                st_text = st.text_area("오늘 수행한 팀플 내용 한줄 요약")
                
                st_media = st.file_uploader("미디어 업로드 (이미지, 동영상, 오디오 음악 지원)", type=["png", "jpg", "jpeg", "mp4", "mp3", "wav"])
                
                submit_story = st.form_submit_button("스토리 피드에 게시")
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
                        "user": st_user,
                        "content": st_text,
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "media_type": media_type,
                        "media_data": media_data,
                        "media_name": media_name,
                        "likes": 0,
                        "liked_users": [],
                        "comments": []
                    })
                    save_data(data)
                    st.success("스토리가 성공적으로 게시되었습니다!")
                    st.rerun()
                    
        with col_view:
            st.markdown("#### 📱 실시간 스토리 피드 목록")
            if not data["stories"]:
                st.caption("아직 올라온 실시간 인증 피드가 없습니다.")
            else:
                for idx, s in enumerate(data["stories"]):
                    with st.container(border=True):
                        st.markdown(f"🔴 **{s['user']}** 조원 | *{s['time']}*")
                        st.write(s["content"])
                        
                        # 멀티미디어 렌더링 검사 및 재생
                        if s.get("media_type") == "image":
                            st.image(s["media_data"], caption=s["media_name"], use_container_width=True)
                        elif s.get("media_type") == "video":
                            st.video(s["media_data"])
                        elif s.get("media_type") == "audio":
                            st.audio(s["media_data"])
                        elif s.get("media_name"):
                            st.caption(f"📎 첨부파일: {s['media_name']}")
                            
                        # 하트 좋아요 기능
                        like_col, comment_count_col = st.columns([1, 4])
                        with like_col:
                            if st.button(f"❤️ {s.get('likes', 0)}", key=f"like_btn_{idx}"):
                                s["likes"] = s.get("likes", 0) + 1
                                save_data(data)
                                st.rerun()
                                
                        # 댓글 기능 구현
                        st.markdown("---")
                        st.caption("💬 댓글 목록")
                        for cm in s.get("comments", []):
                            st.markdown(f"**{cm['writer']}**: {cm['text']} *({cm['time']})*")
                            
                        # 댓글 작성 폼
                        with st.form(f"comment_form_{idx}", clear_on_submit=True):
                            c_writer = st.selectbox("작성자", m_names, key=f"cm_w_{idx}")
                            c_text = st.text_input("댓글 쓰기", key=f"cm_t_{idx}", placeholder="응원의 댓글을 달아주세요.")
                            if st.form_submit_button("댓글 등록") and c_text.strip():
                                s["comments"].append({
                                    "writer": c_writer,
                                    "text": c_text,
                                    "time": datetime.now().strftime("%H:%M")
                                })
                                save_data(data)
                                st.rerun()

    # 탭 3: 팀플 기여도 주식 차트 (인원수 에러 완벽 수정)
    with tab3:
        st.subheader("📈 실시간 팀플 기여도 주식 차트")
        
        # [에러 해결]: 데이터가 비어있거나 조원이 매칭 안 될 때 예외 처리 추가
        valid_stocks = {k: v for k, v in data["stocks"].items() if k in m_names}
        
        if not valid_stocks:
            # 기본 데이터가 꼬였을 경우 실시간 보정 강제 적용
            for name in m_names:
                if name != "등록된 조원 없음":
                    data["stocks"][name] = [10000]
            valid_stocks = {k: v for k, v in data["stocks"].items() if k in m_names}
            save_data(data)
            
        if valid_stocks:
            stock_df = pd.DataFrame(dict([ (k, pd.Series(v)) for k, v in valid_stocks.items() ]))
            st.line_chart(stock_df)
            
            st.markdown("#### 💰 조원별 현재 기여도 주가 현황")
            num_cols = len(valid_stocks)
            
            # [에러 해결]: 스크린샷 2026-06-01 140156.png의 st.columns(len) 인자 전달 방식의 유효성 보장
            if num_cols > 0:
                rank_cols = st.columns(num_cols)
                for r_idx, (name, prices) in enumerate(valid_stocks.items()):
                    with rank_cols[r_idx]:
                        current_price = prices[-1] if len(prices) > 0 else 10000
                        prev_price = prices[-2] if len(prices) > 1 else 10000
                        diff = current_price - prev_price
                        st.metric(label=f"{name} 주가", value=f"{current_price:,} 원", delta=f"{diff:,} 원")
        else:
            st.info("초기화 후 팀원 정보 세팅이 필요합니다.")

    # 탭 4: 달력 일정 관리
    with tab4:
        st.subheader("📅 맞춤형 대시보드 달력")
        
        start, end = data["start_date"], data["end_date"]
        date_list = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        date_strs = [str(d) for d in date_list]
        
        selected_date_str = st.selectbox("🗓️ 조회하거나 할 일을 입력할 날짜 선택", date_strs)
        
        current_event = data["calendar_events"].get(selected_date_str, {"content": "등록된 일이 없습니다.", "status": "❌", "worker": m_names[0]})
        
        col_ev1, col_ev2 = st.columns(2)
        with col_ev1:
            event_input = st.text_input(f"[{selected_date_str}] 할 일 입력", value=current_event["content"])
        with col_ev2:
            worker_input = st.selectbox(f"[{selected_date_str}] 담당 조원 지정", m_names, index=m_names.index(current_event.get("worker", m_names[0])) if current_event.get("worker") in m_names else 0)
            
        if st.button("일정 및 담당자 저장"):
            data["calendar_events"][selected_date_str] = {
                "content": event_input,
                "status": current_event.get("status", "❌"),
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
                    if ev["content"] != "등록된 일이 없습니다.":
                        new_status = "❌" if is_done else "✔️"
                        data["calendar_events"][d_str]["status"] = new_status
                        
                        target_worker = ev["worker"]
                        if target_worker in data["stocks"]:
                            current_p = data["stocks"][target_worker][-1]
                            if new_status == "✔️":
                                data["stocks"][target_worker].append(current_p + 3000)
                            else:
                                data["stocks"][target_worker].append(max(1000, current_p - 3000))
                            
                        save_data(data)
                        st.rerun()

    # 탭 5: 조원 관리 및 단체 DM 채팅방
    with tab5:
        st.subheader("👥 팀원 명부 및 실시간 DM 인프라")
        
        col_m_edit, col_dm = st.columns([1, 1])
        
        with col_m_edit:
            st.markdown("#### 👥 조원 정보 관리 (언제든 추가 및 수정 가능)")
            edit_team_name = st.text_input("조 이름 변경", value=data["team_name"])
            edit_subject = st.text_input("주제 변경", value=data["subject"])
            if st.button("팀 정보 수정완료"):
                data["team_name"] = edit_team_name
                data["subject"] = edit_subject
                save_data(data)
                st.success("기본 정보 변경 성공")
                st.rerun()
                
            for i in range(len(data["members"])):
                is_l = " (👑 조장)" if i == data["leader_idx"] else ""
                st.markdown(f"**조원 {i+1}{is_l}**")
                data["members"][i]["이름"] = st.text_input(f"이름", value=data["members"][i]["이름"], key=f"ed_n_final_{i}")
                data["members"][i]["연락처"] = st.text_input(f"연락처", value=data["members"][i]["연락처"], key=f"ed_p_final_{i}")
                data["members"][i]["역할"] = st.text_input(f"역할", value=data["members"][i]["역할"], key=f"ed_r_final_{i}")
            
            if st.button("조원 명단 최종 저장"):
                for m in data["members"]:
                    if m["이름"] and m["이름"] not in data["stocks"]:
                        data["stocks"][m["이름"]] = [10000]
                save_data(data)
                st.success("수정이 안전하게 저장되었습니다.")
                st.rerun()
                
        with col_dm:
            # 마감 알림 경보 분석
            today_str = str(datetime.today().date())
            today_event = data["calendar_events"].get(today_str, {"status": "❌", "content": "등록된 일이 없습니다."})
            is_emergency = today_event["content"] != "등록된 일이 없습니다." and today_event["status"] == "❌"
            
            if is_emergency:
                st.error(f"🚨 긴급 경보: 오늘 마감 과제 [{today_event['content']}] 미완료! 디엠창 사이렌 가동")
                
            chat_h1, chat_h2 = st.columns([7, 3])
            with chat_h1:
                st.markdown(f"### 📱 {data['team_name']} 단체 DM")
            with chat_h2:
                if st.button("📞 보이스콜 연결", help="인스타 피드 상단 통화 기능"):
                    st.toast("🎵 조원들에게 그룹 전화를 연결 중입니다... (가상 기능)", icon="📞")
            
            st.write("---")
            chat_box = st.container(height=300)
            with chat_box:
                for c in data["chats"]:
                    st.markdown(f"**[{c['sender']}]** *{c['time']}*")
                    st.info(c["msg"])
                    
            with st.form("chat_form_final", clear_on_submit=True):
                c_sender = st.selectbox("보내는 이", m_names, key="chat_s_final")
                c_msg = st.text_input("디엠 보내기...", placeholder="메시지를 입력하세요.")
                submit_c = st.form_submit_button("전송")
                if submit_c and c_msg.strip():
                    data["chats"].append({
                        "sender": c_sender,
                        "msg": c_msg,
                        "time": datetime.now().strftime("%H:%M")
                    })
                    save_data(data)
                    st.rerun()
