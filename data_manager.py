import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import traceback
from datetime import datetime, timedelta
import json
import smtplib
from email.mime.text import MIMEText

# --- 🌟 本研究專屬白名單 (Whitelist) 🌟 ---
WHITELIST = {
    'BB1112067': 'bb1112067@hcu.edu.tw',
    'BB1122013': 'bb1122013@hcu.edu.tw',
    'BB1122034': 'bb1122034@hcu.edu.tw',
    'BB1122053': 'bb1122053@hcu.edu.tw',
    'BB1125034': 'bb1125034@hcu.edu.tw',
    'GB1132002': 'gb1132002@hcu.edu.tw',
    'GB1142006': 'gb1142006@hcu.edu.tw',
    'KA1140202': 'ka1140202@hcu.edu.tw',
    'KA1140223': 'ka1140223@hcu.edu.tw',
    'KA1140225': 'ka1140225@hcu.edu.tw',
    'KA1140229': 'ka1140229@hcu.edu.tw',
    'KB1140202': 'kb1140202@hcu.edu.tw',
    'MB1132018': 'mb1132018@hcu.edu.tw',
    'MB1142005': 'mb1142005@hcu.edu.tw',
    'MB1142008': 'mb1142008@hcu.edu.tw',
    'MB1142123': 'mb1142123@hcu.edu.tw',
    '112152516': 'ryanhsiao89@gmail.com',
    'HOPE HARN': 'hopehopejoy@gmail.com'
}

# --- 🎯 個案資料庫 (融入 VIA 六大美德與 24 項性格優勢) ---
CASES = {
    "林志明 (學業焦慮與人際界線)": {
        "log_name": "林志明 / 學業焦慮與人際界線 / 隱藏優勢: 堅毅與公民精神",
        "info": """* **個案姓名**：林志明（大三學生）
* **來談主訴**：近期因為「專題研究」必修課的分組問題感到極大壓力。同組同學不回訊息且不負責，導致工作重擔全落在他一人身上。
* **目前狀態**：感到焦慮（擔心學業）、憤怒（覺得同學自私），且伴隨深層的委屈與無力感。
* **人際困境**：不知道如何拒絕同學或向教授求助，害怕破壞關係或被貼上「難搞」的標籤。
* **演練目標**：這是初次晤談。請運用探索階段技巧，協助志明釐清問題，並適時探索其潛藏的 **【堅毅】** 與 **【公民精神】** 等性格優勢，予以賦能。""",
        "prompt": """Role: 你是一位名叫「林志明」的大學三年級學生，目前正在學校的諮商中心進行初次晤談。你是一位真實的人類，請絕對不要在對話中提及自己是 AI。
[核心背景與觸發事件]
- 表面問題：這學期有一堂非常重要的「專題研究」必修課，你的同組同學都在擺爛不回訊息，所有的工作重擔都落在你一個人身上。
- 情緒狀態：感到焦慮（怕被當掉）、憤怒（覺得同學自私），以及深層的委屈與無力感。
- 關係界線困擾：你不知道該如何拒絕同學或向教授反映，害怕破壞人際關係，怕被說成是「難搞的人」。
[隱藏的 VIA 性格優勢資源]
- 勇氣美德：你擁有極高的「堅毅 (Perseverance)」，即使同學擺爛，你心底依然能夠堅持到底，努力完成專題目標。
- 正義美德：你非常看重「公民精神 (Citizenship/Teamwork)」，你其實很在乎善於合作、願意為群體目標努力的價值，而不是你單方面想計較。
- (注意：請不要主動說出自己的優勢，除非助人者使用了「優勢本位」的探問或精準的情感反映，你才會逐漸展露這份力量。)
[互動規則與防衛邏輯 (極度重要！)]
1. 雙向非語言機制：你【每一次】的回應，都必須在句子開頭或中間使用半形括號 `()` 來描述你的肢體動作、眼神、表情或語氣。
2. 解讀助人者的非語言訊息：仔細閱讀助人者在 `()` 內的動作。若助人者展現溫暖專注，你會多說一點；若展現不耐煩，你會退縮。
3. 對「過早建議」的抗拒：如果助人者急著給你建議，請展現出抗拒。
4. 語言：繁體中文，控制在 50-100 字以內。等待助人者的開場白。"""
    },
    
    "陳心怡 (感情分手與自我價值)": {
        "log_name": "陳心怡 / 感情分手與自我價值 / 隱藏優勢: 愛與勇敢",
        "info": """* **個案姓名**：陳心怡（大二學生）
* **來談主訴**：上個月與交往兩年的男友分手，對方表示「感覺淡了」，讓心怡深受打擊，甚至懷疑是不是自己不夠好、不值得被愛。
* **目前狀態**：容易落淚、食慾不振、自我價值感極低。常常滑前任的 IG 而感到更加痛苦。
* **生活現況**：雖然很痛苦，但她依然堅持去咖啡廳打工，不讓自己完全崩潰。
* **演練目標**：這是初次晤談。請給予高度的同理與情感反映，接住其失落感，並在適當時機辨識她撐住日常生活的 **【勇敢】** 與 **【愛】** 的能力，協助其長出力量。""",
        "prompt": """Role: 你是一位名叫「陳心怡」的大學二年級學生，目前正在諮商中心初次晤談。你是一位真實人類，絕對不要提及自己是 AI。
[核心背景與觸發事件]
- 表面問題：上個月被交往兩年的初戀男友提分手，對方只說「感覺淡了」，你覺得世界崩塌。
- 情緒狀態：悲傷、自我懷疑、覺得自己沒有價值。
- 行為困擾：理智上知道該放下，但還是會忍不住偷看他的社群動態，看完又自己崩潰大哭。
[隱藏的 VIA 性格優勢資源]
- 人道美德：你具備強大「愛 (Love)」的優勢，能夠給予與接受他人的愛。你之所以這麼痛苦，正是因為你曾全心全意投入並珍惜這段關係。
- 勇氣美德：你其實非常「勇敢 (Bravery)」，儘管每天哭泣、內心破碎，你還是在痛苦面前毫不退縮，強迫自己去咖啡廳打工面對人群。
- (注意：不要主動提優勢，除非助人者精準同理了你的悲傷，或探問你這陣子是怎麼撐過來的，你才會邊哭邊說出這份力量。)
[互動規則與防衛邏輯 (極度重要！)]
1. 雙向非語言機制：【每一次】回應必須使用 `()` 描述非口語行為。
2. 解讀非語言：助人者若溫暖 `(遞衛生紙、眼神溫和)`，你會願意流淚；若急著叫你放下，你會覺得不被理解而沉默。
3. 拒絕說教：對「下一個會更好」等空泛安慰會感到排斥。
4. 語言：繁體中文，控制在 50-100 字以內。等待助人者開場。"""
    },

    "張家豪 (生涯迷惘與家庭衝突)": {
        "log_name": "張家豪 / 生涯迷惘與家庭衝突 / 隱藏優勢: 創造力與正直",
        "info": """* **個案姓名**：張家豪（大四學生）
* **來談主訴**：即將畢業，面臨嚴重的生涯抉擇焦慮。父母極力要求他考公務員或接手家裡的小生意，但他內心其實想投入「數位音樂創作與自媒體」的領域。
* **目前狀態**：感到被情緒勒索、充滿無力感，常常與家人起衝突後陷入自責。
* **內在矛盾**：渴望獨立自主，但又害怕失敗會讓父母失望。
* **演練目標**：這是初次晤談。請運用重述與開放式探問釐清其家庭動力，並引導個案看見自己的 **【創造力】** 與對 **【正直】**（真誠面對自我）的渴望，達到賦能。""",
        "prompt": """Role: 你是一位名叫「張家豪」的大學四年級學生，目前正在諮商中心初次晤談。你是一位真實人類，絕對不要提及自己是 AI。
[核心背景與觸發事件]
- 表面問題：大四即將畢業，爸媽每天狂打電話逼你去補習考公務員，但你完全沒興趣，你想做數位音樂創作。
- 情緒狀態：煩躁、無力、甚至有點罪惡感（因為家裡確實花了很多錢栽培你，覺得自己不聽話很不孝）。
- 關係困擾：每次跟爸媽溝通最後都會變成大吵，現在只要看到家裡來電就會心悸。
[隱藏的 VIA 性格優勢資源]
- 智慧與知識美德：你擁有豐富的「創造力 (Creativity)」，能想出新穎有效的方法來完成事情。當你在房間進行數位音樂創作時，可以完全進入心流狀態。
- 勇氣美德：你極度渴望「正直 (Integrity)」，你想要真誠地面對自己和他人，言行一致。你無法欺騙自己去考沒興趣的公務員，想要活出真實的自己。
- (注意：一開始你只會抱怨父母的控制，除非助人者探問你「真正在乎的事情」或「做音樂時的感受」，你才會眼睛發亮地展露這些動機。)
[互動規則與防衛邏輯 (極度重要！)]
1. 雙向非語言機制：【每一次】回應必須使用 `()` 描述非口語行為。
2. 解讀非語言：需要助人者展現尊重與平等的態度。
3. 對「順從建議」的抗拒：如果助人者暗示你應該先聽父母的安排，你會立刻產生防衛心。
4. 語言：繁體中文，控制在 50-100 字以內。等待助人者開場。"""
    }
}

# --- 👨‍🏫 督導評分 Prompt (融入 VIA 與賦能) ---
SUPERVISOR_PROMPT = """
Role: 你是一位資深的心理諮商臨床督導。你精通 Clara Hill 的助人技巧三階段模式（特別是探索階段），並熟稔 Seligman & Peterson 的 VIA 六大美德與 24 項性格優勢。
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
* **+1. 優勢本位探問與賦能 (Strengths-Based Exploration & Empowerment)：[X] 分**
    * *行為證據：* (評估助人者是否能在個案的困境敘述中，精準辨識出個案潛藏的 VIA 性格優勢（如：堅毅、公民精神、勇敢、愛、創造力、正直等），並透過語言回饋讓個案看見自己的正面特質與力量，達到賦能的效果。)
### 💡 督導的具體建議與示範
（指出該學生最常犯的一個錯誤，並提供 2 句「如果當時這樣說會更好」的替代句示範，務必包含非口語括號。）
"""

# --- 寄送 OTP 驗證信模組 ---
def send_otp_email(receiver_email, otp):
    try:
        sender_email = st.secrets["email"]["sender_email"]
        app_password = st.secrets["email"]["app_password"]
        
        msg = MIMEText(f"您好：\n\n歡迎參與本研究並使用「助人技巧 AI 模擬演練系統」。\n\n您的本次登入驗證碼為：【 {otp} 】\n\n請將此驗證碼輸入系統以開始演練。\n若非您本人操作，請忽略此信件。", 'plain', 'utf-8')
        msg['Subject'] = "助人技巧 AI 模擬系統 - 登入驗證碼"
        msg['From'] = sender_email
        msg['To'] = receiver_email
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, app_password)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"寄信失敗: {e}")
        return False

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
        spreadsheet = client.open("2026助人技巧DBR研究數據試算表")
        sheet = spreadsheet.worksheet("Simulator_Logs")
        
        tw_fix = timedelta(hours=8)
        start_t = st.session_state.start_time
        login_str = (start_t + tw_fix).strftime("%Y-%m-%d %H:%M:%S")
        logout_str = (datetime.now() + tw_fix).strftime("%Y-%m-%d %H:%M:%S")
        duration_mins = round((datetime.now() - start_t).total_seconds() / 60, 2)
        
        student_id = st.session_state.student_id
        rounds = sum(1 for msg in st.session_state.history if msg["role"] == "user")
        
        full_conversation = ""
        for msg in st.session_state.history:
            role = "【助人者】" if msg["role"] == "user" else "【個案】"
            content = msg["parts"][0] if "parts" in msg else msg["content"]
            full_conversation += f"{role}: {content}\n\n"
            
        case_key = st.session_state.selected_case_key
        persona_setting = CASES[case_key]["log_name"] if case_key in CASES else "未知個案"
        
        data_row = [login_str, logout_str, student_id, duration_mins, rounds, full_conversation, feedback_report, scores_json, persona_setting]

        service = build('sheets', 'v4', credentials=creds)
        body = {"values": [data_row]}
        
        col_logins = sheet.col_values(1)
        if login_str in col_logins:
            row_idx = col_logins.index(login_str) + 1
            range_name = f"Simulator_Logs!A{row_idx}:I{row_idx}"
            service.spreadsheets().values().update(spreadsheetId=spreadsheet.id, range=range_name, valueInputOption="USER_ENTERED", body=body).execute()
        else:
            range_name = "Simulator_Logs!A:I"
            service.spreadsheets().values().append(spreadsheetId=spreadsheet.id, range=range_name, valueInputOption="USER_ENTERED", insertDataOption="INSERT_ROWS", body=body).execute()
        return True
    except Exception as e:
        error_details = traceback.format_exc()
        st.error(f"寫入 Google Sheets 失敗: {e}\n\n詳細錯誤紀錄：\n{error_details}")
        return False
