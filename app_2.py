import streamlit as st
import google.generativeai as genai
from google.generativeai.types import GenerationConfig
import time
import re
import random
import json
from datetime import datetime

# 🌟 從資料庫中匯入功能與變數
from data_manager import (
    WHITELIST,
    CASES,
    SUPERVISOR_PROMPT,
    send_otp_email,
    save_to_google_sheets,
)

# =========================================================
# 系統設定
# =========================================================
MODEL_NAME = "gemini-2.5-flash"
TEMPERATURE = 0.0

st.set_page_config(page_title="優勢本位 AI 模擬個案 (DBR 研究版)", layout="wide")


# =========================================================
# Session State 初始化
# =========================================================
def init_session_state():
    defaults = {
        "otp_verified": False,
        "generated_otp": None,
        "student_id": "",
        "api_keys": [],
        "current_key_index": 0,
        "history": [],  # 僅存真實對話歷史：user / model
        "chat_session": None,
        "start_time": None,
        "is_ended": False,
        "supervisor_feedback": "",
        "selected_case_key": "",
        "export_text": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_session_state()


# =========================================================
# 工具函式
# =========================================================
def parse_api_keys(raw_text: str) -> list[str]:
    """將使用者輸入的 API Key 文字切成 list。"""
    if not raw_text:
        return []
    return [k.strip() for k in re.split(r"[\n,]+", raw_text) if k.strip()]


def get_current_api_key() -> str:
    if not st.session_state.api_keys:
        raise RuntimeError("尚未輸入任何 API Key。")
    return st.session_state.api_keys[st.session_state.current_key_index]


def get_case_system_instruction(case_key: str) -> str:
    """
    將個案 prompt 放進 system_instruction，而不是放進對話 history，
    這樣重建 chat session 時比較不會角色漂移。
    """
    base_prompt = CASES[case_key]["prompt"].strip()

    role_guard = """
【固定角色規則】
1. 你永遠是「模擬個案」，不是助人者、諮商師、督導、老師、系統管理員，也不是旁白。
2. 你只能用「個案第一人稱」回應，不可切換成諮商師視角提供建議、分析、教學或示範。
3. 你必須回應助人者剛剛說的話，不能替助人者說話，也不能代替助人者總結。
4. 若助人者表達同理、提問、重述或情感反映，你要以「個案」身分自然回應。
5. 不可輸出類似以下口吻：
   -「作為諮商師，我建議……」
   -「你可以這樣回應個案……」
   -「身為助人者，你應該……」
6. 若你一時角色混亂，請立即回到「模擬個案」身分繼續對話。
7. 回應應保持真實、貼近個案主訴與情緒狀態，不要突然變成專家講解。
"""
    return f"{base_prompt}\n\n{role_guard}"


def build_dialog_model(api_key: str, case_key: str):
    """建立用於『模擬個案對話』的模型。"""
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(
        model_name=MODEL_NAME,
        generation_config=GenerationConfig(temperature=TEMPERATURE),
        system_instruction=get_case_system_instruction(case_key),
    )


def build_supervisor_model(api_key: str):
    """建立用於『督導評分』的模型。"""
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(
        model_name=MODEL_NAME,
        generation_config=GenerationConfig(temperature=TEMPERATURE),
    )


def history_to_gemini_format(exclude_last_user: bool = False) -> list[dict]:
    """
    將 st.session_state.history 轉成 Gemini start_chat 可吃的 history 格式。
    若 exclude_last_user=True，代表目前最後一句 user 訊息尚未成功送達模型，
    重建 session 時要先排除，之後再重新 send_message。
    """
    hist = st.session_state.history
    if exclude_last_user and hist and hist[-1]["role"] == "user":
        hist = hist[:-1]

    formatted = []
    for msg in hist:
        content = msg["parts"][0] if "parts" in msg else msg.get("content", "")
        role = "model" if msg["role"] == "model" else "user"
        formatted.append({"role": role, "parts": [content]})
    return formatted


def rebuild_chat_session(exclude_last_user: bool = False):
    """
    依目前 case + 真實歷史重建 chat session。
    這裡不再把 client_prompt 當成 fake user history。
    """
    api_key = get_current_api_key()
    case_key = st.session_state.selected_case_key
    model = build_dialog_model(api_key, case_key)
    rebuilt_history = history_to_gemini_format(exclude_last_user=exclude_last_user)
    st.session_state.chat_session = model.start_chat(history=rebuilt_history)


def ensure_chat_session():
    """若 chat_session 遺失，就依現有 history 重建。"""
    if st.session_state.chat_session is None and st.session_state.selected_case_key:
        rebuild_chat_session(exclude_last_user=False)


def switch_to_next_key() -> bool:
    """切換到下一把 API Key。成功回傳 True，否則 False。"""
    next_index = st.session_state.current_key_index + 1
    if next_index < len(st.session_state.api_keys):
        st.session_state.current_key_index = next_index
        return True
    return False


def send_dialog_message_with_failover(user_input: str) -> str:
    """
    傳送對話訊息給模擬個案。
    遇到 429 / Quota 時自動切 key，並重建 chat session 後重試。
    """
    if not st.session_state.api_keys:
        raise RuntimeError("尚未輸入任何 API Key。")

    ensure_chat_session()
    waited_once = False

    while True:
        try:
            response = st.session_state.chat_session.send_message(user_input)
            return response.text

        except Exception as e:
            err_text = str(e)

            if "429" in err_text or "Quota" in err_text:
                if switch_to_next_key():
                    st.toast(
                        f"🔄 第 {st.session_state.current_key_index + 1} 組 API Key 已接手繼續運作...",
                        icon="🛡️"
                    )
                    # 重建時排除最後一句尚未成功送出的 user 訊息
                    rebuild_chat_session(exclude_last_user=True)
                    continue

                if not waited_once:
                    waited_once = True
                    st.warning("⏳ 所有備用 API 額度皆暫時滿載，系統自動倒數 20 秒緩衝中...")
                    time.sleep(20)
                    rebuild_chat_session(exclude_last_user=True)
                    continue

            raise e


def generate_supervisor_feedback_with_failover(final_prompt: str) -> str:
    """
    產生督導評分報告。
    遇到 429 / Quota 時自動切 key 或等待後重試。
    """
    if not st.session_state.api_keys:
        raise RuntimeError("尚未輸入任何 API Key。")

    waited_once = False

    while True:
        try:
            supervisor_model = build_supervisor_model(get_current_api_key())
            feedback_resp = supervisor_model.generate_content(final_prompt)
            return feedback_resp.text

        except Exception as e:
            err_text = str(e)

            if "429" in err_text or "Quota" in err_text:
                if switch_to_next_key():
                    continue

                if not waited_once:
                    waited_once = True
                    st.info("⏳ 督導評分：所有 API 額度暫時滿載，系統自動倒數 20 秒...")
                    time.sleep(20)
                    continue

            raise e


def extract_scores_from_report(report: str) -> dict:
    score_patterns = {
        "專注": r"專注.*?\[(\d)\]\s*分",
        "傾聽": r"傾聽.*?\[(\d)\]\s*分",
        "開放式探問": r"開放式探問.*?\[(\d)\]\s*分",
        "重述": r"重述.*?\[(\d)\]\s*分",
        "情感反映": r"情感反映.*?\[(\d)\]\s*分",
        "優勢本位探問": r"優勢本位探問.*?\[(\d)\]\s*分",
    }

    scores = {}
    for key, pattern in score_patterns.items():
        match = re.search(pattern, report)
        scores[key] = int(match.group(1)) if match else 0
    return scores


# =========================================================
# 側邊欄
# =========================================================
st.sidebar.title("⚙️ 系統設定")

api_input = st.sidebar.text_area(
    "🔑 輸入 Gemini API Key\n(可輸入 2-3 組，請用逗號或換行隔開以防斷線)",
    value="\n".join(st.session_state.api_keys),
)
st.session_state.api_keys = parse_api_keys(api_input)

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**📝 演練提示**\n"
    "1. 這是**初次晤談**，火力集中在「探索階段」。\n"
    "2. 務必使用 **`( )`** 描述非口語行為。\n"
    "3. 目標時間：30-45分鐘。"
)


# =========================================================
# 畫面 1：登入與 OTP 驗證
# =========================================================
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
                st.session_state.current_key_index = 0
                st.session_state.history = []
                st.session_state.chat_session = None
                st.session_state.is_ended = False
                st.session_state.supervisor_feedback = ""
                st.session_state.export_text = ""
                st.session_state.generated_otp = None

                rebuild_chat_session(exclude_last_user=False)
                st.rerun()
            else:
                st.error("❌ 驗證碼錯誤，請重新輸入。")

    st.stop()


# =========================================================
# 畫面 2 & 3：對話演練與督導回饋
# =========================================================
ensure_chat_session()

current_case_key = st.session_state.selected_case_key
case_name_display = current_case_key.split(" ")[0] if current_case_key else ""
st.title(f"🗣️ 模擬晤談中 (個案：{case_name_display})")

with st.expander("📄 個案基本資料與來談主訴 (點擊可收合/展開)", expanded=True):
    st.markdown(CASES[current_case_key]["info"])


# 顯示歷史訊息
for msg in st.session_state.history:
    role = "assistant" if msg["role"] == "model" else "user"
    content = msg["parts"][0] if "parts" in msg else msg.get("content", "")
    with st.chat_message(role):
        st.write(content)


# =========================================================
# 對話進行中
# =========================================================
if not st.session_state.is_ended:
    user_input = st.chat_input("請輸入你的回應 (記得加上括號描述非語言行為喔)...")

    if user_input:
        if "(" not in user_input and "（" not in user_input:
            st.toast("⚠️ 溫馨提醒：你似乎忘了使用 ( ) 描述非口語行為喔！", icon="💡")

        # 先把學生訊息放進顯示歷史
        st.session_state.history.append({"role": "user", "parts": [user_input]})

        with st.chat_message("user"):
            st.write(user_input)

        with st.spinner("個案思考中..."):
            time.sleep(1.5)

            try:
                response_text = send_dialog_message_with_failover(user_input)

                # 成功後才把 AI 回應放進歷史
                st.session_state.history.append({"role": "model", "parts": [response_text]})
                save_to_google_sheets()
                st.rerun()

            except Exception as e:
                # 若真的失敗，移除剛剛那句尚未完成的 user 訊息，避免歷史失衡
                if st.session_state.history and st.session_state.history[-1]["role"] == "user":
                    st.session_state.history.pop()
                st.error(f"發生未預期的錯誤：{e}")

    st.markdown("---")
    col1, col2 = st.columns([8, 2])
    with col2:
        if st.button("🛑 結束晤談並獲取督導回饋", type="primary", use_container_width=True):
            st.session_state.is_ended = True
            st.rerun()


# =========================================================
# 晤談結束後：督導回饋與下載
# =========================================================
else:
    if not st.session_state.supervisor_feedback:
        st.markdown("---")
        with st.spinner("👨‍🏫 臨床督導正在審閱你的對話紀錄，進行 5+1 技巧評分... (約需 10-20 秒)"):
            log_text = ""
            for msg in st.session_state.history:
                role_str = "助人者" if msg["role"] == "user" else "個案"
                content = msg["parts"][0] if "parts" in msg else msg.get("content", "")
                log_text += f"{role_str}: {content}\n"

            final_prompt = f"{SUPERVISOR_PROMPT}\n\n[待評估的對話紀錄如下]\n{log_text}"

            try:
                report = generate_supervisor_feedback_with_failover(final_prompt)
                st.session_state.supervisor_feedback = report

                scores = extract_scores_from_report(report)

                save_to_google_sheets(
                    is_final=True,
                    feedback_report=report,
                    scores_json=json.dumps(scores, ensure_ascii=False),
                )

                export_text = "【助人技巧 AI 模擬演練紀錄】\n"
                export_text += f"演練時間：{st.session_state.start_time.strftime('%Y-%m-%d %H:%M')}\n"
                export_text += f"演練學號：{st.session_state.student_id}\n"
                export_text += f"個案情境：{st.session_state.selected_case_key}\n"
                export_text += "=" * 40 + "\n\n"
                export_text += "【對話逐字稿】\n"

                for msg in st.session_state.history:
                    role_str = "助人者" if msg["role"] == "user" else "個案"
                    content = msg["parts"][0] if "parts" in msg else msg.get("content", "")
                    export_text += f"{role_str}：{content}\n\n"

                export_text += "=" * 40 + "\n\n"
                export_text += "【督導回饋報告】\n"
                export_text += report

                st.session_state.export_text = export_text
                st.rerun()

            except Exception as e:
                st.error(f"督導評分系統發生錯誤：{e}")

    if st.session_state.supervisor_feedback:
        st.success("✅ 晤談紀錄與評分已成功自動上傳至研究資料庫！")
        st.markdown("## 📋 督導回饋報告")
        st.markdown(st.session_state.supervisor_feedback)

        col3, col4 = st.columns([1, 1])

        with col3:
            st.download_button(
                label="📥 下載本次對話紀錄與督導評分 (txt檔)",
                data=st.session_state.export_text.encode("utf-8-sig"),
                file_name=f"晤談紀錄_{st.session_state.student_id}_{datetime.now().strftime('%Y%m%d%H%M')}.txt",
                mime="text/plain",
                use_container_width=True,
            )

        with col4:
            if st.button("🔄 返回首頁 / 選擇其他個案", use_container_width=True):
                keep_keys = {"api_keys"}
                for key in list(st.session_state.keys()):
                    if key not in keep_keys:
                        del st.session_state[key]
                st.rerun()
