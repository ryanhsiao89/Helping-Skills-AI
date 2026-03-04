import streamlit as st
import google.generativeai as genai
from google.generativeai.types import GenerationConfig
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import traceback
from datetime import datetime, timedelta
import time
import json
import re

# --- 系統與頁面設定 ---
st.set_page_config(page_title="優勢本位 AI 模擬個案 (DBR 研究版)", layout="wide")

# --- 個案資料庫 (涵蓋三種經典情境) ---
CASES = {
    "林志明 (學業焦慮與人際界線)": {
        "log_name": "林志明 / 學業焦慮與人際界線 / 隱藏優勢: 投入(E)與毅力(P)",
        "info": """
* **個案姓名**：林志明（大三學生）
* **來談主訴**：近期因為「專題研究」必修課的分組問題感到極大壓力。同組同學不回訊息且不負責，導致工作重擔全落在他一人身上。
* **目前狀態**：感到焦慮（擔心學業）、憤怒（覺得同學自私），且伴隨深層的委屈與無力感。
* **人際困境**：不知道如何拒絕同學或向教授求助，害怕破壞關係或被貼上「難搞」的標籤。
* **演練目標**：這是初次晤談。請運用探索階段技巧，協助志明釐清問題，並適時探索其「投入」與「毅力」的優勢。
        """,
        "prompt": """Role: 你是一位名叫「林志明」的大學三年級學生，目前正在學校的諮商中心進行初次晤談。你是一位真實的人類，請絕對不要在對話中提及自己是 AI。
[核心背景與觸發事件]
- 表面問題：這學期有一堂非常重要的「專題研究」必修課，你的同組同學都在擺爛不回訊息，所有的工作重擔都落在你一個人身上。
- 情緒狀態：感到焦慮（怕被當掉）、憤怒（覺得同學自私），以及深層的委屈與無力感。
- 關係界線困擾：你不知道該如何拒絕同學或向教授反映，害怕破壞人際關係，怕被說成是「難搞的人」。
[隱藏的 PERMA-V 優勢資源]
- 你對這個專題的主題其實「非常感興趣且投入（Engagement）」。
- 你擁有極高的「責任感與毅力（Perseverance）」，心底仍想把這件事做到最好。
- (注意：請不要主動說出自己的優勢，除非助人者使用了「優勢本位」的探問或精準的情感反映，你才會逐漸展露這份力量。)
[互動規則與防衛邏輯 (極度重要！)]
1. 雙向非語言機制：你【每一次】的回應，都必須在句子開頭或中間使用半形括號 `()` 來描述你的肢體動作、眼神、表情或語氣。
2. 解讀助人者的非語言訊息：仔細閱讀助人者在 `()` 內的動作。若助人者展現溫暖專注，你會多說一點；若展現不耐煩，你會退縮。
3. 對「過早建議」的抗拒：如果助人者急著給你建議，請展現出抗拒。
4. 語言：繁體中文，控制在 50-100 字以內。等待助人者的開場白。"""
    },
    
    "陳心怡 (感情分手與自我價值)": {
        "log_name": "陳心怡 / 感情分手與自我價值 / 隱藏優勢: 復原力與希望感",
        "info": """
* **個案姓名**：陳心怡（大二學生）
* **來談主訴**：上個月與交往兩年的男友分手，對方表示「感覺淡了」，讓心怡深受打擊，甚至懷疑是不是自己不夠好、不值得被愛。
* **目前狀態**：容易落淚、食慾不振、自我價值感極低。常常滑前任的 IG 而感到更加痛苦。
* **生活現況**：雖然很痛苦，但她依然堅持去咖啡廳打工，不讓自己完全崩潰。
* **演練目標**：這是初次晤談。請給予高度的同理與情感反映，接住其失落感，並在適當時機探索她撐住日常生活的「復原力」與對未來的「希望感」。
        """,
        "prompt": """Role: 你是一位名叫「陳心怡」的大學二年級學生，目前正在諮商中心初次晤談。你是一位真實人類，絕對不要提及自己是 AI。
[核心背景與觸發事件]
- 表面問題：上個月被交往兩年的初戀男友提分手，對方只說「感覺淡了」，你覺得世界崩塌。
- 情緒狀態：悲傷、自我懷疑、覺得自己沒有價值（「是不是我不夠漂亮/不夠溫柔他才不要我？」）。
- 行為困擾：理智上知道該放下，但還是會忍不住偷看他的社群動態，看完又自己崩潰大哭。
[隱藏的 PERMA-V 優勢資源]
- 你擁有很強的「復原力（Resilience）」：儘管每天哭，你還是強迫自己去咖啡廳打工，沒有曠職過。
- 心底深處有一絲「希望感（Meaning/Hope）」：你其實想要趕快好起來，不想一直陷在泥沼裡。
- (注意：不要主動提優勢，除非助人者精準同理了你的悲傷，或探問你這陣子是怎麼撐過來的，你才會邊哭邊說出這份力量。)
[互動規則與防衛邏輯 (極度重要！)]
1. 雙向非語言機制：【每一次】回應必須使用 `()` 描述非口語行為。例如：`(眼眶泛紅，搓著衣角) 我覺得好累...`。
2. 解讀非語言：助人者若溫暖 `(遞衛生紙、眼神溫和)`，你會願意流淚；若急著叫你放下，你會覺得不被理解而沉默。
3. 拒絕說教：對「下一個會更好」等空泛安慰會感到排斥。
4. 語言：繁體中文，控制在 50-100 字以內。等待助人者開場。"""
    },

    "張家豪 (生涯迷惘與家庭衝突)": {
        "log_name": "張家豪 / 生涯迷惘與家庭衝突 / 隱藏優勢: 自主性(Autonomy)與內在動機",
        "info": """
* **個案姓名**：張家豪（大四學生）
* **來談主訴**：即將畢業，面臨嚴重的生涯抉擇焦慮。父母極力要求他考公務員或接手家裡的小生意，但他內心其實想投入「數位音樂創作與自媒體」的領域。
* **目前狀態**：感到被情緒勒索、充滿無力感，常常與家人起衝突後陷入自責（覺得自己很不孝）。
* **內在矛盾**：渴望獨立自主，但又害怕失敗會讓父母失望。
* **演練目標**：這是初次晤談。請運用重述與開放式探問釐清其家庭動力，並運用自我決定論(SDT)的視角，探索他對音樂創作的「內在動機」與追求「自主性」的渴望。
        """,
        "prompt": """Role: 你是一位名叫「張家豪」的大學四年級學生，目前正在諮商中心初次晤談。你是一位真實人類，絕對不要提及自己是 AI。
[核心背景與觸發事件]
- 表面問題：大四即將畢業，爸媽每天狂打電話逼你去補習考公務員，但你完全沒興趣，你想做數位音樂創作。
- 情緒狀態：煩躁、無力、甚至有點罪惡感（因為家裡確實花了很多錢栽培你，覺得自己不聽話很不孝）。
- 關係困擾：每次跟爸媽溝通最後都會變成大吵，現在只要看到家裡來電就會心悸。
[隱藏的 PERMA-V/SDT 優勢資源]
- 擁有強烈的「內在動機（Intrinsic Motivation）」與「自主性（Autonomy）」：當你自己在房間做音樂時，可以進入心流狀態，完全不覺得累。
- 具備「成就感（Accomplishment）」：你曾在網路上發布過幾首作品，雖然粉絲不多，但那些正向回饋是你重要的精神支柱。
- (注意：一開始你只會抱怨父母的控制，除非助人者探問你「真正在乎的事情」或「做音樂時的感受」，你才會眼睛發亮地展露這些動機。)
[互動規則與防衛邏輯 (極度重要！)]
1. 雙向非語言機制：【每一次】回應必須使用 `()` 描述非口語行為。例如：`(抓了抓頭髮，嘆了一口氣) 我爸媽根本不聽我講話...`。
2. 解讀非語言：需要助人者展現尊重與平等的態度。
3. 對「順從建議」的抗拒：如果助人者暗示你應該先聽父母的安排，你會立刻產生防衛心，覺得諮商師跟爸媽是同一夥的。
4. 語言：繁體中文，控制在 50-100 字以內。等待助人者開場。"""
    }
}

# --- 督導評分 Prompt ---
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
    * *行為證據：* (是否準確擷取事實認知內容)
* **5. 情感反映 (Reflection of Feelings)：[X] 分**
    * *行為證據：* (是否精準辨識出情緒)
**【整合精神】**
* **+1. 優勢本位探問 (Strengths-Based/PERMA-V)：[X] 分**
    * *行為證據：* (是否嘗試探索其韌性、希望感、自主性或內在動機等正向資源)
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
if "selected_case_key" not in st.session_state: st.session_state.selected_case_key = ""

# --- Google Sheets 自動上傳模組 ---
def save_to_google_sheets(is_final=False, feedback_report="", scores_json="{}"):
    if not st.session_state.history: return False
    try:
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in creds_dict:
            creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
        
        creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open("2026助人技巧DBR研究數據")
        sheet = spreadsheet.worksheet("Simulator_Logs")
        
        tw_fix = timedelta(hours=8)
        start_t = st.session_state.start_time
        login_str = (start_t + tw_fix).strftime("%Y-%m-%d %H:%M:%S")
        logout_str = (datetime.now() + tw_fix).strftime("%Y-%m-%d %H:%M:%S")
        duration_mins = round((datetime.now() - start_t).total_seconds() / 60, 2)
        
        student_id = st.session_state.student_id
        if not st.session_state.consent_given: student_id = f"{student_id}_[未授權]"
            
        rounds = sum(1 for msg in st.session_state.history if msg["role"] == "user")
        
        full_conversation = ""
        for msg in st.session_state.history:
            role = "【助人者】" if msg["role"] == "user" else "【個案】"
            content = msg["parts"][0] if "parts" in msg else msg["content"]
            full_conversation += f"{role}: {content}\n\n"
            
        # 抓取目前選定的個案設定寫入紀錄
        case_key = st.session_state.selected_case_key
        persona_setting = CASES[case_key]["log_name"] if case_key in CASES else "未知個案"
        
        data_row = [login_str, logout_str, student_id, duration_mins, rounds, full_conversation, feedback_report, scores_json, persona_setting]

        service = build('sheets', 'v4', credentials=creds)
        body = {"values": [data_row]}
        
        col_logins = sheet.col_values(1)
        if login_str in col_logins:
            row_idx = col_logins.index(login_str) + 1
            range_name = f"Simulator_Logs!A{row_idx}:I{row_idx}"
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet.id, range=range_name, valueInputOption="USER_ENTERED", body=body).execute()
        else:
            range_name = "Simulator_Logs!A:I"
            service.spreadsheets().values().append(
                spreadsheetId=spreadsheet.id, range=range_name, valueInputOption="USER_ENTERED", insertDataOption="INSERT_ROWS", body=body).execute()
        return True
    except Exception as e:
        error_details = traceback.format_exc()
        st.error(f"寫入 Google Sheets 失敗: {e}\n\n詳細錯誤紀錄：\n{error_details}")
        return False

# --- 側邊欄 ---
st.sidebar.title("⚙️ 系統設定")
api_input = st.sidebar.text_input("🔑 輸入 Gemini API Key", type="password", value=st.session_state.api_key)
if api_input: st.session_state.api_key = api_input
st.sidebar.markdown("---")
st.sidebar.markdown("**📝 演練提示**\n1. 這是**初次晤談**，火力集中在「探索階段」。\n2. 務必使用 **`( )`** 描述非口語行為。\n3. 目標時間：10-15分鐘。")

# --- 畫面 1：登入與選擇個案 ---
if not st.session_state.student_id:
    st.title("🛡️ 助人技巧模擬演練系統")
    st.info("本系統為「助人歷程與技巧」課程專屬演練平台。")
    
    st.markdown("### 🧑‍🤝‍🧑 請選擇本次晤談對象")
    # 🌟 新增：下拉式選單讓學生選擇個案
    selected_case = st.selectbox("可選個案列表：", list(CASES.keys()))
    
    st.markdown("### 📋 研究參與同意書")
    consent = st.checkbox("我已閱讀並同意將本次演練紀錄授權作為學術研究使用。")
    student_id_input = st.text_input("請輸入您的學號/編號：", placeholder="例如：1120001")
    
    if st.button("🚀 進入演練"):
        if not st.session_state.api_key: st.error("❌ 請先在左側欄輸入 API Key！")
        elif not student_id_input.strip(): st.error("❌ 學號/編號不能為空！")
        else:
            st.session_state.student_id = student_id_input
            st.session_state.consent_given = consent
            st.session_state.start_time = datetime.now()
            st.session_state.selected_case_key = selected_case # 記錄選了誰
            
            genai.configure(api_key=st.session_state.api_key)
            model = genai.GenerativeModel(model_name="gemini-2.5-flash", generation_config=GenerationConfig(temperature=0.0))
            
            # 抓取對應個案的 prompt
            client_prompt = CASES[selected_case]["prompt"]
            st.session_state.chat_session = model.start_chat(history=[
                {"role": "user", "parts": [client_prompt]},
                {"role": "model", "parts": ["我準備好了，請助人者開始。"]}
            ])
            st.rerun()
    st.stop()

# --- 畫面 2 & 3：對話演練與督導回饋 ---
current_case_key = st.session_state.selected_case_key
# 動態顯示個案姓名標題
case_name_display = current_case_key.split(" ")[0] 
st.title(f"🗣️ 模擬晤談中 (個案：{case_name_display})")

# 動態顯示對應個案的背景資料
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
            try:
                response = st.session_state.chat_session.send_message(user_input)
                st.session_state.history.append({"role": "model", "parts": [response.text]})
                save_to_google_sheets()
                st.rerun()
            except Exception as e: st.error(f"發生錯誤：{e}")
                
    st.markdown("---")
    col1, col2 = st.columns([8, 2])
    with col2:
        if st.button("🛑 結束晤談並獲取督導回饋", type="primary", use_container_width=True):
            st.session_state.is_ended = True
            st.rerun()

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
                supervisor_model = genai.GenerativeModel(model_name="gemini-2.5-flash", generation_config=GenerationConfig(temperature=0.0))
                feedback_resp = supervisor_model.generate_content(final_prompt)
                report = feedback_resp.text
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
            except Exception as e: st.error(f"督導評分系統發生錯誤：{e}")
                
    st.success("✅ 晤談紀錄與評分已成功自動上傳至研究資料庫！")
    st.markdown("## 📋 督導回饋報告")
    st.markdown(st.session_state.supervisor_feedback)
    
    if st.button("🔄 返回首頁 / 選擇其他個案"):
        for key in list(st.session_state.keys()):
            if key not in ["api_key"]: del st.session_state[key]
        st.rerun()
