import streamlit as st
import google.generativeai as genai
from google.generativeai.types import GenerationConfig
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import time
import json
import re

# --- 系統與頁面設定 ---
st.set_page_config(page_title="優勢本位 AI 模擬個案 (DBR 研究版)", layout="wide")

# --- Google Sheets 自動上傳模組 ---
def save_to_google_sheets(is_final=False, feedback_report="", scores_json="{}"):
    """將對話與評分紀錄寫入 Google Sheets"""
    if not st.session_state.history:
        return False
        
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open("2026助人技巧DBR研究數據").worksheet("Simulator_Logs")
        
        tw_fix = timedelta(hours=8)
        start_t = st.session_state.start_time
        login_str = (start_t + tw_fix).strftime("%Y-%m-%d %H:%M:%S")
        logout_str = (datetime.now() + tw_fix).strftime("%Y-%m-%d %H:%M:%S")
        duration_mins = round((datetime.now() - start_t).total_seconds() / 60, 2)
        
        # 標記未授權的 ID
        student_id = st.session_state.student_id
        if not st.session_state.consent_given:
            student_id = f"{student_id}_[未授權]"
            
        # 計算對話回合數 (使用者發話次數)
        rounds = sum(1 for msg in st.session_state.history if msg["role"] == "user")
        
        # 整理對話文本
        full_conversation = ""
        for msg in st.session_state.history:
            role = "【助人者】" if msg["role"] == "user" else "【個案】"
            content = msg["parts"][0] if "parts" in msg else msg["content"]
            full_conversation += f"{role}: {content}\n\n"
            
        persona_setting = "林志明 / 學業焦慮與人際界線 / 隱藏優勢: 投入(E)與毅力(P)"
        data_row = [login_str, logout_str, student_id, duration_mins, rounds, full_conversation, feedback_report, scores_json, persona_setting]

        # 簡單邏輯：根據 login_str 尋找是否已有該筆紀錄，有則更新，無則新增
        col_logins = sheet.col_values(1)
        if login_str in col_logins:
            row_idx = col_logins.index(login_str) + 1
            sheet.update(values=[data_row], range_name=f'A{row_idx}:I{row_idx}')
        else:
            sheet.append_row(data_row)
            
        return True
    except Exception as e:
        st.error(f"寫入 Google Sheets 失敗: {e}")
        return False

# --- 第一層：個案靈魂 Prompt ---
CLIENT_PROMPT = """
Role: 你是一位名叫「林志明」的大學三年級學生，目前正在學校的諮商中心進行初次晤談。你是一位真實的人類，請絕對不要在對話中提及自己是 AI。

[核心背景與觸發事件]
- 表面問題：這學期有一堂非常重要的「專題研究」必修課，你的同組同學都在擺爛不回訊息，所有的工作重擔都落在你一個人身上。
- 情緒狀態：感到焦慮（怕被當掉）、憤怒（覺得同學自私），以及深層的委屈與無力感。
- 關係界線困擾：你不知道該如何拒絕同學或向教授反映，害怕破壞人際關係，怕被說成是「難搞的人」。

[隱藏的 PERMA-V 優勢資源]
- 你對這個專題的主題其實「非常感興趣且投入（Engagement）」。
- 你擁有極高的「責任感與毅力（Perseverance）」，心底仍想把這件事做到最好。
- (注意：請不要主動說出自己的優勢，除非助人者使用了「優勢本位」的探問或精準的情感反映，你才會逐漸展露這份力量。)

[互動規則與防衛邏輯 (極度重要！)]
1. 雙向非語言機制：你【每一次】的回應，都必須在句子開頭或中間使用半形括號 `()` 來描述你的肢體動作、眼神、表情或語氣。例如：`(低著頭，語氣微微顫抖) 我真的不知道該怎麼辦...`
2. 解讀助人者的非語言訊息：仔細閱讀助人者在 `()` 內的動作。若助人者展現溫暖專注 `(身體前傾)`，你會感到安全並多說一點；若助人者展現不耐煩或分心 `(看手錶)`，你會立刻退縮，回應帶有防衛心。
3. 對「過早建議」的抗拒：如果助人者急著給你建議（如「你應該直接去跟教授說」），請展現出抗拒：`(皺眉，身體往後傾) 事情哪有你想的那麼簡單... 你根本不懂我的處境。`
4. 對「高階微技巧」的敞開：當助人者精準使用「重述」、「情感反映」或「優勢探問」時，你會感到被深深理解，並願意吐露更深層的矛盾感受。

[輸出限制]
- 語言：繁體中文，使用符合台灣大學生日常口語的表達方式。
- 長度：每次回應控制在 50-100 字以內。
- 現在請等待助人者的開場白。
"""

# --- 第二層：督導評分 Prompt ---
SUPERVISOR_PROMPT = """
Role: 你是一位資深的心理諮商臨床督導。你精通 Clara Hill 的助人技巧三階段模式（特別是探索階段）以及 PERMA-V 優勢本位取向。

[任務說明]
請閱讀以下提供的【助人者與個案的完整對話紀錄】。依據「5+1 助人微技巧行為錨定評分表」，對助人者的表現進行盲評。
評分標準 (1-5分)：1分=不適當/具破壞性/未使用；3分=基本達標/堪用；5分=高度熟練/自然流暢且精準。

[輸出格式要求]
請嚴格依照以下 Markdown 格式輸出回饋報告：

### 🎯 總體表現摘要
（用 3-4 句話總結該學生的整體晤談氛圍、優勢以及最大的盲點。）

### 📊 5+1 微技巧量化評分與證據
請針對以下 6 個向度給分（格式務必精確為 `[X] 分`，例如 `[4] 分`），並引用對話紀錄中的具體字句（含括號內的非口語行為）作為證據。

**【非語言訊息技巧】**
* **1. 專注 (Attending)：[X] 分**
    * *行為證據：* (引用學生的括號內容說明)
* **2. 傾聽 (Listening)：[X] 分**
    * *行為證據：* (引用學生的括號內容說明語氣節奏)

**【語言訊息技巧 (探索階段)】**
* **3. 開放式探問 (Open Questions)：[X] 分**
    * *行為證據：* (是否避免了封閉式問句並有效引導)
* **4. 重述 (Restatement)：[X] 分**
    * *行為證據：* (是否準准确擷取事實認知內容)
* **5. 情感反映 (Reflection of Feelings)：[X] 分**
    * *行為證據：* (是否精準辨識出情緒)

**【整合精神】**
* **+1. 優勢本位探問 (Strengths-Based/PERMA-V)：[X] 分**
    * *行為證據：* (是否嘗試探索其韌性、投入等正向資源)

### 💡 督導的具體建議與示範
（指出該學生最常犯的一個錯誤，並提供 2 句「如果當時這樣說會更好」的替代句示範，務必包含非口語括號。）
"""

# --- 初始化 Session State ---
if "student_id" not in st.session_state: st.session_state.student_id = ""
if "consent_given" not in st.session_state: st.session_state.consent_given = False
if "api_key" not in st.session_state: st.session_state.api_key = ""
if "history" not in st.session_state: st.session_state.history = []
if "chat_session" not in st.session_state: st.session_state.chat_session = None
if "start_time" not in st.session_state: st.session_state.start_time = None
if "is_ended" not in st.session_state: st.session_state.is_ended = False
if "supervisor_feedback" not in st.session_state: st.session_state.supervisor_feedback = ""

# --- 側邊欄：API 與資訊 ---
st.sidebar.title("⚙️ 系統設定")
api_input = st.sidebar.text_input("🔑 輸入 Gemini API Key", type="password", value=st.session_state.api_key)
if api_input:
    st.session_state.api_key = api_input

st.sidebar.markdown("---")
st.sidebar.markdown("""
**📝 演練提示**
1. 這是**初次晤談**，請將火力集中在「探索階段」。
2. 請務必使用 **`( )`** 來描述你的非口語行為（如語氣、表情），例如：
   `(身體前傾，語氣溫和) 聽起來你承受了很大的壓力。`
3. 目標時間：10-15分鐘 (約 8-12 回合)。
""")

# --- 畫面 1：登入與研究同意書 ---
if not st.session_state.student_id:
    st.title("🛡️ 助人技巧模擬演練系統")
    st.info("本系統為「助人歷程與技巧」課程專屬演練平台。")
    
    st.markdown("### 📋 研究參與同意書")
    st.markdown("""
    本演練系統結合「設計本位研究 (DBR)」，您的對話紀錄與客觀評分將作為研究分析之用。
    * **資料去識別化**：所有文本將被妥善保護，不會出現您的真實姓名。
    * **自由意願**：若您不同意參與研究，仍可完整使用本系統進行演練，您的資料將不會被納入最終論文分析。
    """)
    
    consent = st.checkbox("我已閱讀並同意將本次演練紀錄授權作為學術研究使用。")
    student_id_input = st.text_input("請輸入您的學號/編號：", placeholder="例如：1120001")
    
    if st.button("🚀 進入演練"):
        if not st.session_state.api_key:
            st.error("❌ 請先在左側欄輸入 API Key！")
        elif not student_id_input.strip():
            st.error("❌ 學號/編號不能為空！")
        else:
            st.session_state.student_id = student_id_input
            st.session_state.consent_given = consent
            st.session_state.start_time = datetime.now()
            
            genai.configure(api_key=st.session_state.api_key)
            model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                generation_config=GenerationConfig(temperature=0.0)
            )
            st.session_state.chat_session = model.start_chat(history=[
                {"role": "user", "parts": [CLIENT_PROMPT]},
                {"role": "model", "parts": ["我準備好了，請助人者開始。"]}
            ])
            st.rerun()
    st.stop()

# --- 畫面 2 & 3：對話演練與督導回饋 ---
st.title(f"🗣️ 模擬晤談中 (個案：林志明)")

# 🌟 新增：個案基本資料與來談主訴介面
with st.expander("📄 個案基本資料與來談主訴 (點擊可收合/展開)", expanded=True):
    st.markdown("""
    * **個案姓名**：林志明（大三學生）
    * **來談主訴**：近期因為「專題研究」必修課的分組問題感到極大壓力。同組同學不回訊息且不負責，導致工作重擔全落在他一人身上。
    * **目前狀態**：感到焦慮（擔心學業）、憤怒（覺得同學自私），且伴隨深層的委屈與無力感。
    * **人際困境**：不知道如何拒絕同學或向教授求助，害怕破壞關係或被貼上「難搞」的標籤。
    * **演練目標**：這是你們的**初次晤談**。請運用專注、傾聽、開放式探問、重述與情感反映等探索階段技巧，協助志明釐清目前的問題與感受。
    """)

# 顯示對話歷史
for msg in st.session_state.history:
    role = "assistant" if msg["role"] == "model" else "user"
    with st.chat_message(role):
        st.write(msg["content"] if "content" in msg else msg["parts"][0])

# 如果晤談尚未結束
if not st.session_state.is_ended:
    user_input = st.chat_input("請輸入你的回應 (記得加上括號描述非語言行為喔)...")
    
    if user_input:
        if "(" not in user_input and "（" not in user_input:
            st.toast("⚠️ 溫馨提醒：你似乎忘了使用 ( ) 描述非口語行為喔！", icon="💡")
            
        st.session_state.history.append({"role": "user", "parts": [user_input]})
        with st.chat_message("user"):
            st.write(user_input)
            
        with st.spinner("個案思考中..."):
            time.sleep(2)
            try:
                response = st.session_state.chat_session.send_message(user_input)
                st.session_state.history.append({"role": "model", "parts": [response.text]})
                save_to_google_sheets()
                st.rerun()
            except Exception as e:
                st.error(f"發生錯誤：{e}")
                
    st.markdown("---")
    col1, col2 = st.columns([8, 2])
    with col2:
        if st.button("🛑 結束晤談並獲取督導回饋", type="primary", use_container_width=True):
            st.session_state.is_ended = True
            st.rerun()

# 如果晤談已結束：呼叫第二層評分引擎
else:
    if not st.session_state.supervisor_feedback:
        st.markdown("---")
        with st.spinner("👨‍🏫 臨床督導正在審閱你的對話紀錄，進行 5+1 技巧評分... (約需 10-20 秒)"):
            try:
                log_text = ""
                for msg in st.session_state.history:
                    role_str = "助人者" if msg["role"] == "user" else "個案"
                    content = msg["parts"][0] if "parts" in msg else msg["content"]
                    log_text += f"{role_str}: {content}\n"
                
                final_prompt = f"{SUPERVISOR_PROMPT}\n\n[待評估的對話紀錄如下]\n{log_text}"
                
                supervisor_model = genai.GenerativeModel(
                    model_name="gemini-2.5-flash",
                    generation_config=GenerationConfig(temperature=0.0)
                )
                feedback_resp = supervisor_model.generate_content(final_prompt)
                report = feedback_resp.text
                st.session_state.supervisor_feedback = report
                
                scores = {}
                score_patterns = {
                    "專注": r"專注.*?\[(\d)\]\s*分",
                    "傾聽": r"傾聽.*?\[(\d)\]\s*分",
                    "開放式探問": r"開放式探問.*?\[(\d)\]\s*分",
                    "重述": r"重述.*?\[(\d)\]\s*分",
                    "情感反映": r"情感反映.*?\[(\d)\]\s*分",
                    "優勢本位探問": r"優勢本位探問.*?\[(\d)\]\s*分"
                }
                for key, pattern in score_patterns.items():
                    match = re.search(pattern, report)
                    scores[key] = int(match.group(1)) if match else 0
                
                scores_json_str = json.dumps(scores, ensure_ascii=False)
                save_to_google_sheets(is_final=True, feedback_report=report, scores_json=scores_json_str)
                
            except Exception as e:
                st.error(f"督導評分系統發生錯誤：{e}")
                
    st.success("✅ 晤談紀錄與評分已成功自動上傳至研究資料庫！")
    st.markdown("## 📋 督導回饋報告")
    st.markdown(st.session_state.supervisor_feedback)
    
    if st.button("🔄 重新開始新的演練"):
        for key in list(st.session_state.keys()):
            if key not in ["api_key"]:
                del st.session_state[key]
        st.rerun()
