import streamlit as st
import google.generativeai as genai
from google.generativeai.types import GenerationConfig
import time
import re
import random
import json
from datetime import datetime
# 🌟 從資料庫中匯入功能與變數
from data_manager import WHITELIST, CASES, SUPERVISOR_PROMPT, send_otp_email, save_to_google_sheets

# --- 系統與頁面設定 ---
st.set_page_config(page_title="優勢本位 AI 模擬個案 (DBR 研究版)", layout="wide")

# --- 初始化 Session State ---
if "otp_verified" not in st.session_state: st.session_state.otp_verified = False
if "generated_otp" not in st.session_state: st.session_state.generated_otp = None
if "student_id" not in st.session_state: st.session_state.student_id = ""
if "api_keys" not in st.session_state: st.session_state.api_keys = [] # 🌟 改為存放多組 Key 的陣列
if "current_key_index" not in st.session_state: st.session_state.current_key_index = 0 # 🌟 紀錄目前用到第幾把 Key
if "history" not in st.session_state: st.session_state.history = []
if "chat_session" not in st.session_state: st.session_state.chat_session = None
if "start_time" not in st.session_state: st.session_state.start_time = None
if "is_ended" not in st.session_state: st.session_state.is_ended = False
if "supervisor_feedback" not in st.session_state: st.session_state.supervisor_feedback = ""
if "selected_case_key" not in st.session_state: st.session_state.selected_case_key = ""
if "export_text" not in st.session_state: st.session_state.export_text = ""

# --- 側邊欄 ---
st.sidebar.title("⚙️ 系統設定")
# 🌟 允許輸入多組 API Key
api_input = st.sidebar.text_area("🔑 輸入 Gemini API Key\n(可輸入2-3組，請用逗號或換行隔開以防斷線)", value="\n".join(st.session_state.api_keys))
if api_input: 
    # 將輸入的字串用逗號或換行切割，並清除空白
    parsed_keys = [k.strip() for k in re.split(r'[\n,]+', api_input) if k.strip()]
    st.session_state.api_keys = parsed_keys

st.sidebar.markdown("---")
st.sidebar.markdown("**📝 演練提示**\n1. 這是**初次晤談**，火力集中在「探索階段」。\n2. 務必使用 **`( )`** 描述非口語行為。\n3. 目標時間：10-15分鐘。")

# --- 畫面 1：登入與雙重驗證 (OTP) ---
if not st.session_state.otp_verified:
    st.title("🛡️ 助人技巧模擬演練系統")
    st.info("本系統為「助人歷程與技巧」課程專屬演練平台。為確保研究資料正確性，請進行身分驗證。")
    
    st.markdown("### 🧑‍🤝‍🧑 步驟一：選擇個案與基本資料")
    selected_case = st.selectbox("可選個案列表：", list(CASES.keys()))
    
    col1, col2 = st.columns([1, 1])
    with col1:
        student_id_input = st.text_input("請輸入您的學號/ID：", placeholder="例如：BB1112067")
    
    if st.button("📧 發送驗證碼"):
        if not st.session_state.api_keys:
            st.error("❌ 請先在左側欄輸入至少一組 API Key！")
        elif not student_id_input.strip():
            st.error("❌ 學號/ID 不能為空！")
        else:
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
                        st.session_state.selected_case_key = selected_case
                        st.success(f"✅ 驗證碼已發送至您的專屬信箱 ({masked_email})！")
                    else:
                        st.error("❌ 寄信失敗，請向研究者確認系統後台信箱設定。")
    
    if st.session_state.generated_otp:
        st.markdown("### 🔐 步驟二：輸入驗證碼")
        user_otp = st.text_input("請輸入您信箱收到的 6 位數驗證碼：", type="password")
        if st.button("🚀 驗證並進入演練"):
            if user_otp == st.session_state.generated_otp:
                st.session_state.otp_verified = True
                st.session_state.start_time = datetime.now()
                
                # 🌟 初始化第一把 API Key
                st.session_state.current_key_index = 0
                genai.configure(api_key=st.session_state.api_keys[0])
                model = genai.GenerativeModel(model_name="gemini-2.5-flash", generation_config=GenerationConfig(temperature=0.0))
                client_prompt = CASES[st.session_state.selected_case_key]["prompt"]
                st.session_state.chat_session = model.start_chat(history=[
                    {"role": "user", "parts": [client_prompt]},
                    {"role": "model", "parts": ["我準備好了，請助人者開始。"]}
                ])
                st.rerun()
            else:
                st.error("❌ 驗證碼錯誤，請重新輸入。")
    st.stop()

# --- 畫面 2 & 3：對話演練與督導回饋 ---
current_case_key = st.session_state.selected_case_key
case_name_display = current_case_key.split(" ")[0] 
st.title(f"🗣️ 模擬晤談中 (個案：{case_name_display})")

with st.expander("📄 個案基本資料與來談主訴 (點擊可收合/展開)", expanded=True):
    st.markdown(CASES[current_case_key]["info"])

for msg in st.session_state.history:
    role = "assistant" if msg["role"] == "model" else "user"
    with st.chat_message(role):
        st.write(msg["content"] if "content" in msg else msg["parts"][0])

if not st.session_state.is_ended:
    user_input = st.chat_input("請輸入你的回應 (記得加上括號描述非語言行為喔)...")
    if user_input:
        if "(" not in user_input and "（" not in user_input:
            st.toast("⚠️ 溫馨提醒：你似乎忘了使用 ( ) 描述非口語行為喔！", icon="💡")
        
        st.session_state.history.append({"role": "user", "parts": [user_input]})
        with st.chat_message("user"): st.write(user_input)
            
        with st.spinner("個案思考中..."):
            time.sleep(2)
            
            # 🌟 自動切換 API Key 的核心邏輯迴圈
            max_attempts = len(st.session_state.api_keys)
            response_text = None
            
            for attempt in range(max_attempts):
                try:
                    response = st.session_state.chat_session.send_message(user_input)
                    response_text = response.text
                    break # 成功取得回覆，跳出迴圈
                except Exception as e:
                    if "429" in str(e) or "Quota" in str(e):
                        next_index = st.session_state.current_key_index + 1
                        if next_index < len(st.session_state.api_keys):
                            # 切換下一把 Key
                            st.session_state.current_key_index = next_index
                            new_key = st.session_state.api_keys[next_index]
                            genai.configure(api_key=new_key)
                            st.toast(f"🔄 第 {next_index} 組額度已滿，自動切換至備用 Key 繼續運作...", icon="🛡️")
                            
                            # 重新建構帶有歷史記憶的 Chat Session 
                            model = genai.GenerativeModel(model_name="gemini-2.5-flash", generation_config=GenerationConfig(temperature=0.0))
                            
                            # 🌟 [修復角色錯亂]：將「個案初始設定檔」與「扣除最後一句失敗的歷史紀錄」重新合併
                            client_prompt = CASES[st.session_state.selected_case_key]["prompt"]
                            base_history = [
                                {"role": "user", "parts": [client_prompt]},
                                {"role": "model", "parts": ["我準備好了，請助人者開始。"]}
                            ]
                            old_history = st.session_state.history[:-1] 
                            full_history = base_history + old_history
                            
                            st.session_state.chat_session = model.start_chat(history=full_history)
                            # 迴圈會繼續下一次嘗試
                        else:
                            # 所有 Key 都用光了，終極防護：等 20 秒
                            st.warning("⏳ 所有備用 API 額度皆暫時滿載，系統自動倒數 20 秒緩衝中...")
                            time.sleep(20)
                            response = st.session_state.chat_session.send_message(user_input)
                            response_text = response.text
                            break
                    else:
                        st.error(f"發生未預期的錯誤：{e}")
                        break
            
            if response_text:
                st.session_state.history.append({"role": "model", "parts": [response_text]})
                save_to_google_sheets()
                st.rerun()

    st.markdown("---")
    col1, col2 = st.columns([8, 2])
    with col2:
        if st.button("🛑 結束晤談並獲取督導回饋", type="primary", use_container_width=True):
            st.session_state.is_ended = True
            st.rerun()

else:
    # --- 晤談結束後的督導與下載區塊 ---
    if not st.session_state.supervisor_feedback:
        st.markdown("---")
        with st.spinner("👨‍🏫 臨床督導正在審閱你的對話紀錄，進行 5+1 技巧評分... (約需 10-20 秒)"):
            log_text = ""
            for msg in st.session_state.history:
                role_str = "助人者" if msg["role"] == "user" else "個案"
                content = msg["parts"][0] if "parts" in msg else msg["content"]
                log_text += f"{role_str}: {content}\n"
            
            final_prompt = f"{SUPERVISOR_PROMPT}\n\n[待評估的對話紀錄如下]\n{log_text}"
            
            # 🌟 督導評分一樣具備自動切換 API Key 的能力
            max_attempts = len(st.session_state.api_keys)
            report = ""
            for attempt in range(max_attempts):
                try:
                    supervisor_model = genai.GenerativeModel(model_name="gemini-2.5-flash", generation_config=GenerationConfig(temperature=0.0))
                    feedback_resp = supervisor_model.generate_content(final_prompt)
                    report = feedback_resp.text
                    break
                except Exception as e:
                    if "429" in str(e) or "Quota" in str(e):
                        next_index = st.session_state.current_key_index + 1
                        if next_index < len(st.session_state.api_keys):
                            st.session_state.current_key_index = next_index
                            genai.configure(api_key=st.session_state.api_keys[next_index])
                        else:
                            st.info("⏳ 督導評分：所有 API 額度暫時滿載，系統自動倒數 20 秒...")
                            time.sleep(20)
                            supervisor_model = genai.GenerativeModel(model_name="gemini-2.5-flash", generation_config=GenerationConfig(temperature=0.0))
                            feedback_resp = supervisor_model.generate_content(final_prompt)
                            report = feedback_resp.text
                            break
                    else:
                        st.error(f"督導評分系統發生錯誤：{e}")
                        break
            
            if report:
                st.session_state.supervisor_feedback = report
                
                scores = {}
                score_patterns = {
                    "專注": r"專注.*?\[(\d)\]\s*分", "傾聽": r"傾聽.*?\[(\d)\]\s*分",
                    "開放式探問": r"開放式探問.*?\[(\d)\]\s*分", "重述": r"重述.*?\[(\d)\]\s*分",
                    "情感反映": r"情感反映.*?\[(\d)\]\s*分", "優勢本位探問": r"優勢本位探問.*?\[(\d)\]\s*分"
                }
                for key, pattern in score_patterns.items():
                    match = re.search(pattern, report)
                    scores[key] = int(match.group(1)) if match else 0
                
                save_to_google_sheets(is_final=True, feedback_report=report, scores_json=json.dumps(scores, ensure_ascii=False))
                
                export_text = f"【助人技巧 AI 模擬演練紀錄】\n"
                export_text += f"演練時間：{st.session_state.start_time.strftime('%Y-%m-%d %H:%M')}\n"
                export_text += f"演練學號：{st.session_state.student_id}\n"
                export_text += f"個案情境：{st.session_state.selected_case_key}\n"
                export_text += "="*40 + "\n\n"
                export_text += "【對話逐字稿】\n"
                for msg in st.session_state.history:
                    role_str = "助人者" if msg["role"] == "user" else "個案"
                    content = msg["parts"][0] if "parts" in msg else msg["content"]
                    export_text += f"{role_str}：{content}\n\n"
                export_text += "="*40 + "\n\n"
                export_text += "【督導回饋報告】\n"
                export_text += report
                
                st.session_state.export_text = export_text
                st.rerun()

    if st.session_state.supervisor_feedback:
        st.success("✅ 晤談紀錄與評分已成功自動上傳至研究資料庫！")
        st.markdown("## 📋 督導回饋報告")
        st.markdown(st.session_state.supervisor_feedback)
        
        col3, col4 = st.columns([1, 1])
        with col3:
            st.download_button(
                label="📥 下載本次對話紀錄與督導評分 (txt檔)",
                data=st.session_state.export_text.encode('utf-8-sig'),
                file_name=f"晤談紀錄_{st.session_state.student_id}_{datetime.now().strftime('%Y%m%d%H%M')}.txt",
                mime="text/plain",
                use_container_width=True
            )
        with col4:
            if st.button("🔄 返回首頁 / 選擇其他個案", use_container_width=True):
                for key in list(st.session_state.keys()):
                    # 清除狀態時，保留已經輸入的 api_keys，這樣學生回首頁不用重新輸入
                    if key not in ["api_keys"]: del st.session_state[key]
                st.rerun()
