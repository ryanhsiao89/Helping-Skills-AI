import streamlit as st
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
import personas
import data_manager
import time
import random
import smtplib
from email.mime.text import MIMEText
from datetime import datetime

st.set_page_config(page_title="AI 團體諮商模擬器", page_icon="🎭", layout="wide")

# --- 🌟 本研究專屬白名單 (Whitelist) ---
WHITELIST = {
    'BB1092033': 'joychen0614@gmail.com',
    'BB1102066': 'bb1102066@hcu.edu.tw',
    'BB1122004': 'bb1122004@hcu.edu.tw',
    'BB1122014': 'chienchiye@gmail.com',
    'BB1122015': 'bb1122015@hcu.edu.tw',
    'BB1122017': 'bb1122017@hcu.edu.tw',
    'BB1122021': 'bb1122021@hcu.edu.tw',
    'BB1122022': 'bb1122022@hcu.edu.tw',
    'BB1122024': 'bb1122024@hcu.edu.tw',
    'BB1122025': 'jason745726@gmail.com',
    'BB1122026': '940104lin@gmail.com',
    'BB1122028': 'bb1122028@hcu.edu.tw',
    'BB1122032': 'a02577koy@gmail.com',
    'BB1122034': 'bb1122034@hcu.edu.tw',
    'BB1122040': 'bb1122040@hcu.edu.tw',
    'BB1122041': 'chenjay0116@gmail.com',
    'BB1122053': 'jasminehu0711@gmail.com',
    'BB1125025': 'bb1125025@hcu.edu.tw',
    'BB1125034': 'bb1125034@hcu.edu.tw',
    'TA1140202': 'ta1140202@hcu.edu.tw',
    'TA1140203': 'ta1140203@hcu.edu.tw',
    'KA1130107': 'si847452195@gmail.com',
    '112152516': 'ryanhsiao89@gmail.com',
    'HOPE HARN': 'hopehopejoy@gmail.com',
}

# --- 寄送 OTP 驗證信模組 ---
def send_otp_email(receiver_email, otp):
    """透過 Gmail 發送 6 位數驗證碼"""
    try:
        sender_email = st.secrets["email"]["sender_email"]
        app_password = st.secrets["email"]["app_password"]
        
        msg = MIMEText(f"您好：\n\n歡迎參與本研究並使用「團體諮商 AI 模擬演練系統」。\n\n您的本次登入驗證碼為：【 {otp} 】\n\n請將此驗證碼輸入系統以開始演練。\n若非您本人操作，請忽略此信件。", 'plain', 'utf-8')
        msg['Subject'] = "團體諮商 AI 模擬系統 - 登入驗證碼"
        msg['From'] = sender_email
        msg['To'] = receiver_email
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, app_password)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"寄信失敗: {e}")
        return False

# --- 初始化 Session State ---
if "otp_verified" not in st.session_state: st.session_state.otp_verified = False
if "generated_otp" not in st.session_state: st.session_state.generated_otp = None
if "student_id" not in st.session_state: st.session_state.student_id = ""
if "chat_history" not in st.session_state: st.session_state.chat_history = []

# --- 側邊欄 (基本說明) ---
with st.sidebar:
    st.markdown("### ℹ️ 說明")
    st.info("本系統對話紀錄將自動存入雲端資料庫，作為教學與研究分析使用。")
    st.caption("請盡情演練，無需擔心紀錄遺失。")

# --- 階段 1：登入與雙重驗證 (OTP) ---
if not st.session_state.otp_verified:
    st.title("🛡️ 團體諮商 AI 模擬系統")
    st.info("本系統為專屬演練平台。為確保研究資料正確性，請先進行身分驗證。")
    
    st.markdown("### 🧑‍🤝‍🧑 步驟一：輸入學號獲取驗證碼")
    student_id_input = st.text_input("請輸入您的學號/ID：", placeholder="例如：BB1112067")
    
    if st.button("📧 發送驗證碼"):
        if not student_id_input.strip():
            st.error("❌ 學號/ID 不能為空！")
        else:
            student_id_clean = student_id_input.strip().upper() 
            if student_id_input.strip() in WHITELIST:
                student_id_clean = student_id_input.strip()
                
            if student_id_clean not in WHITELIST:
                st.error("❌ 查無此學號/ID，請確認您是否具備本研究之參與資格。")
            else:
                target_email = WHITELIST[student_id_clean]
                masked_email = target_email[:4] + "****" + target_email[target_email.find("@"):]
                
                with st.spinner("正在發送驗證信，請稍候..."):
                    otp = str(random.randint(100000, 999999))
                    if send_otp_email(target_email, otp):
                        st.session_state.generated_otp = otp
                        st.session_state.student_id = student_id_clean
                        st.success(f"✅ 驗證碼已發送至您的專屬信箱 ({masked_email})！請檢查收件匣（若無請檢查垃圾郵件）。")
                    else:
                        st.error("❌ 寄信失敗，請向研究者確認系統後台信箱設定。")
    
    if st.session_state.generated_otp:
        st.markdown("### 🔐 步驟二：輸入驗證碼")
        user_otp = st.text_input("請輸入您信箱收到的 6 位數驗證碼：", type="password")
        if st.button("🚀 驗證並前往劇本設定"):
            if user_otp == st.session_state.generated_otp:
                st.session_state.otp_verified = True
                st.rerun()
            else:
                st.error("❌ 驗證碼錯誤，請重新輸入。")

# --- 階段 2：劇本與參數設定 ---
elif "current_session_id" not in st.session_state:
    st.title("🎭 團體諮商模擬系統")
    st.markdown(f"##### 👤 歡迎，**{st.session_state.student_id}**！請完成演練設定")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🔑 系統設定")
        api_key_input = st.text_input("Google API Key", type="password")
        user_role = st.radio("👉 您的角色", 
                             ["團體帶領者 (Leader)", "團體成員 (Member)"])
    
    with col2:
        st.markdown("### ⚙️ 劇本設定")
        
        group_type_options = [
            "大學生生涯探索團體", "人際關係成長團體", "情緒支持團體",
            "壓力調適與自我照顧團體", "憤怒情緒管理團體", "哀傷與失落輔導團體",     
            "職場/學校溝通技巧團體", "其他 (請自訂)"
        ]
        
        selected_type = st.selectbox("團體類型", group_type_options)
        
        custom_type = ""
        if selected_type == "其他 (請自訂)":
            custom_type = st.text_input("請輸入自訂的團體名稱/性質")
            final_group_type = custom_type
        else:
            final_group_type = selected_type

        session_num = st.slider("現在是第幾次團體？", 1, 10, 1)
        
        context_input = st.text_area(
            "前情提要 / 團體氣氛 (Context) 🎲", 
            value="",
            placeholder="請輸入情境。若留白，系統將自動隨機抽取一個溫和安全的狀況讓您練習！"
        )

    if st.button("開始演練", type="primary"):
        if api_key_input and final_group_type:
            
            if context_input.strip() == "":
                random_contexts = [
                    "【溫和破冰】這是第一次團體，成員們態度都很友善，但稍微有些害羞。大家面帶微笑看著帶領者，等待您給予明確的指示或有趣的破冰小活動。",
                    "【建立共鳴】剛剛有成員提到最近對於『未來發展』和『課業』感到一點點迷惘，其他幾個人聽了頻頻點頭。這是一個建立『普遍性 (Universality)』，讓大家知道彼此都有同感的好時機。",
                    "【正向支持】目前氣氛很溫暖。有成員主動分享了最近生活中一件微小但開心的事情（例如發掘了自己的某個小優勢或興趣），非常適合帶領者與其他成員練習給予肯定與支持。",
                    "【目標探索】成員們對於『團體諮商』感到好奇，雖然不太確定具體要怎麼運作，但大家展現出高度的參與意願，很適合在這裡一起討論並建立團體的共同目標。",
                    "【溫和沉默】大家目前情緒很平穩，只是靜靜地坐著。氣氛並不緊張或抗拒，只是單純不知道該說什麼。這時只要帶領者拋出一個簡單、低威脅性的問題（例如：今天出門前心情怎麼樣？），大家就很願意回答。"
                ]
                final_context = random.choice(random_contexts)
            else:
                final_context = context_input

            session_id = data_manager.start_session(st.session_state.student_id, user_role, final_group_type, session_num)
            
            st.session_state.current_session_id = session_id
            st.session_state.api_key = api_key_input
            st.session_state.user_role = user_role
            st.session_state.group_context = {
                "type": final_group_type, 
                "session": session_num, 
                "atmosphere": final_context 
            }
            
            # 確保達成「一 Leader + 三成員」的四選三出場機制
            if user_role == "團體帶領者 (Leader)":
                full_pool = personas.get_mixed_participants(count=5, include_leader=False)
                members_only = [p for p in full_pool if "Leader" not in p['name']]
                st.session_state.participants = random.sample(members_only, min(3, len(members_only)))
                
                st.session_state.user_avatar = "🧑‍🏫"
                st.session_state.user_name = "Leader"
                st.session_state.chat_history = [] 
            else:
                full_pool = personas.get_mixed_participants(count=5, include_leader=True)
                ai_leader = [p for p in full_pool if "Leader" in p['name']]
                members_only = [p for p in full_pool if "Leader" not in p['name']]
                
                selected_members = random.sample(members_only, min(3, len(members_only)))
                st.session_state.participants = ai_leader + selected_members
                
                st.session_state.user_avatar = "🙋"
                st.session_state.user_name = "Member"
                
                welcome_msg = f"大家好，歡迎大家來到這次的「{final_group_type}」。今天是我們的第 {session_num} 次聚會，有人想先分享一下最近的心情，或是帶著什麼期待來嗎？"
                st.session_state.chat_history = [{"role": "Dr. AI (Leader)", "content": welcome_msg}]
                data_manager.log_message(session_id, st.session_state.student_id, "Dr. AI (Leader)", welcome_msg)
            
            st.rerun()
        else:
            st.warning("請輸入 API Key 並確認團體資訊")

# --- 階段 3：聊天室 ---
else:
    ctx = st.session_state.group_context
    st.subheader(f"💬 {ctx['type']} (第 {ctx['session']} 次)")
    
    st.success(f"🎬 **當前情境設定：** {ctx['atmosphere']}")
    
    cols = st.columns(len(st.session_state.participants))
    for idx, p in enumerate(st.session_state.participants):
        with cols[idx]:
            st.info(f"{p['avatar']} {p['name']}\n\n{p['type']}")

    # ⏬ 新增：防呆 UX 側邊欄設計 (將下載與登出整合)
    with st.sidebar:
        st.markdown("---")
        st.markdown("### 📝 演練結束區")
        
        # 準備逐字稿內容
        transcript = f"【團體諮商模擬演練逐字稿】\n學號：{st.session_state.student_id}\n匯出時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        for msg in st.session_state.chat_history:
            transcript += f"{msg['role']}： {msg['content']}\n\n"
            
        # 按鈕 1：醒目的下載按鈕 (加上 utf-8-sig 解決 iPad/Mac 亂碼問題)
        st.download_button(
            label="📥 1. 先下載本次逐字稿",
            data=transcript.encode('utf-8-sig'),  # 👈 修正：強制加入 BOM 防止亂碼
            file_name=f"GroupLog_{st.session_state.student_id}_{datetime.now().strftime('%m%d_%H%M')}.txt",
            mime="text/plain",
            use_container_width=True,
            type="primary"
        )
        
        # 加上防呆警告
        st.warning("⚠️ 離開前請務必確認已下載逐字稿。")
        
        # 按鈕 2：登出按鈕
        if st.button("🚪 2. 結束並登出系統", use_container_width=True):
            for key in list(st.session_state.keys()): del st.session_state[key]
            st.rerun()

    # 顯示訊息
    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            with st.chat_message("user", avatar=st.session_state.user_avatar):
                st.write(f"**{st.session_state.user_name}:** {msg['content']}")
        else:
            member = next((p for p in st.session_state.participants if p['name'] == msg['role']), None)
            avatar = member['avatar'] if member else "🤖"
            with st.chat_message("assistant", avatar=avatar):
                st.write(f"**{msg['role']}:** {msg['content']}")
        
    # 輸入框
    if user_input := st.chat_input("請輸入..."):
        st.chat_message("user", avatar=st.session_state.user_avatar).write(user_input)
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        data_manager.log_message(st.session_state.current_session_id, st.session_state.student_id, "User", user_input)

        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash", 
            google_api_key=st.session_state.api_key,
            temperature=0
        )
        
        error_shown = False
        
        # ⏬ 動態發言機制 (降低 API 負荷)
        active_speakers = []
        for p in st.session_state.participants:
            if "Leader" in p['name']:
                if random.random() < 0.80:
                    active_speakers.append(p)
            else:
                if random.random() < 0.40:
                    active_speakers.append(p)
                    
        # 防冷場機制
        if not active_speakers:
            active_speakers = [random.choice(st.session_state.participants)]
            
        random.shuffle(active_speakers)
        
        for participant in active_speakers:
            with st.spinner(f"{participant['name']} 思考中..."):
                context_prompt = f"""
                [DYNAMIC CONTEXT]
                Group Type: {ctx['type']}
                Session Number: {ctx['session']}
                Atmosphere: {ctx['atmosphere']}
                Your Role: {participant['system_prompt']}
                User Role: {st.session_state.user_role}
                
                INSTRUCTION: 
                Respond naturally according to your persona.
                """
                
                messages = [SystemMessage(content=context_prompt)]
                for history_msg in st.session_state.chat_history:
                    role = history_msg["role"]
                    content = history_msg["content"]
                    if role == "user":
                        messages.append(HumanMessage(content=f"User: {content}"))
                    else:
                        prefix = "You" if role == participant['name'] else role
                        messages.append(HumanMessage(content=f"{prefix}: {content}"))
                
                try:
                    response = llm.invoke(messages)
                    content = response.content
                    if len(content.strip()) > 1:
                        st.chat_message("assistant", avatar=participant['avatar']).write(f"**{participant['name']}:** {content}")
                        st.session_state.chat_history.append({"role": participant['name'], "content": content})
                        data_manager.log_message(st.session_state.current_session_id, st.session_state.student_id, participant['name'], content)
                    
                    time.sleep(2.5)
                    
                except Exception as e:
                    if not error_shown and ("429" in str(e) or "quota" in str(e).lower() or "exhausted" in str(e).lower()):
                        st.warning("⏳ 系統提示：伺服器稍微有點塞車，請稍等約 20 秒後再發言。")
                        error_shown = True
