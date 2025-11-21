import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, date
from collections import Counter

st.set_page_config(
    page_title="文化祭ポテト会計",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ===== 基本設定 =====
BASE_PRICE = 300  # 通常価格
SEMINAR_PRICE = 200 # 講演会価格
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# ===== Streamlit Secrets から設定を読み込む =====
SERVICE_ACCOUNT_INFO = st.secrets["google_service_account"]
SPREADSHEET_ID = SERVICE_ACCOUNT_INFO["SPREADSHEET_ID"]
DISCOUNT_PASSWORD = SERVICE_ACCOUNT_INFO["DISCOUNT_PASSWORD"]


@st.cache_resource
def get_gsheet_client():
    """
    Google Sheets クライアント（Cloud 専用）
    """
    creds = Credentials.from_service_account_info(
        SERVICE_ACCOUNT_INFO,
        scopes=SCOPES
    )
    client = gspread.authorize(creds)
    return client


def get_today_worksheet():
    client = get_gsheet_client()
    sh = client.open_by_key(SPREADSHEET_ID)
    sheet_name = date.today().isoformat()  # "2025-11-21" みたいな形式

    try:
        ws = sh.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        # なければ新規作成してヘッダー行を入れる
        ws = sh.add_worksheet(title=sheet_name, rows="1000", cols="5")
        ws.append_row(["timestamp", "date", "count", "amount", "detail"])
    return ws


# ===== 売上集計 =====
def get_today_stats():
    ws = get_today_worksheet()
    values = ws.get_all_values()
    if len(values) <= 1:
        # ヘッダーしかない
        return 0, 0

    total_count = 0
    total_amount = 0
    for row in values[1:]:
        try:
            c = int(row[2])  # count
            a = int(row[3])  # amount
            total_count += c
            total_amount += a
        except (ValueError, IndexError):
            continue
    return total_count, total_amount

def get_last_n_days_stats(n=3):
    """
    直近 n 日分（シート名が YYYY-MM-DD のもの）の
    売上個数・売上金額の合計を返す
    """
    client = get_gsheet_client()
    sh = client.open_by_key(SPREADSHEET_ID)

    date_sheets = []
    for ws in sh.worksheets():
        title = ws.title
        try:
            d = date.fromisoformat(title)  # "2025-11-21" みたいなシートだけ対象
            date_sheets.append((d, ws))
        except ValueError:
            # 日付じゃないシートは無視
            continue

    if not date_sheets:
        return 0, 0, None, None

    # 日付でソートして直近 n 日を取る
    date_sheets.sort(key=lambda x: x[0])
    last = date_sheets[-n:]

    total_count = 0
    total_amount = 0

    for _, ws in last:
        values = ws.get_all_values()
        if len(values) <= 1:
            continue
        for row in values[1:]:
            try:
                c = int(row[2])
                a = int(row[3])
                total_count += c
                total_amount += a
            except (ValueError, IndexError):
                continue

    start_date = last[0][0].isoformat()
    end_date = last[-1][0].isoformat()

    return total_count, total_amount, start_date, end_date

# ===== 直前の会計を取り消し =====
def cancel_last_transaction():
    ws = get_today_worksheet()
    values = ws.get_all_values()
    if len(values) <= 1:
        st.warning("まだ会計データがありません。")
        return
    last_row = len(values)
    ws.delete_rows(last_row)
    st.success("直前の会計を取り消しました。")


# ===== 取引の保存 =====
def save_transaction(basket):
    """
    basket: [300, 300, 200, ...] みたいな価格のリスト
    """
    if not basket:
        st.warning("カゴが空です。")
        return

    ws = get_today_worksheet()

    now = datetime.now()
    ts = now.strftime("%H:%M:%S")
    d = now.date().isoformat()

    count = len(basket)
    amount = sum(basket)

    counter = Counter(basket)
    detail_parts = []
    for price, cnt in sorted(counter.items()):
        detail_parts.append(f"{price}円×{cnt}")
    detail = ", ".join(detail_parts)

    # 1取引＝1行として書き込み
    ws.append_row([ts, d, count, amount, detail])
    st.success(f"会計を保存しました：{count}個 / {amount}円")


# ===== Streamlit UI =====
def main():
    st.title("文化祭ポテト会計アプリ 🥔")

    # セッション状態の初期化（カゴ）
    if "basket" not in st.session_state:
        st.session_state.basket = []

    # サイドバーに今日の売上サマリ
    st.sidebar.header("本日の売上")
    count, amount = get_today_stats()
    st.sidebar.metric("売上個数", f"{count} 個")
    st.sidebar.metric("売上金額", f"{amount} 円")

    st.sidebar.markdown("---")

    # 直近N日間の合計（ここでは5日）
    c3, a3, start, end = get_last_n_days_stats(5)
    st.sidebar.header("期間中合計")
    st.sidebar.metric("合計個数", f"{c3} 個")
    st.sidebar.metric("合計金額", f"{a3} 円")
    if start and end:
        st.sidebar.caption(f"期間: {start} 〜 {end}")

    # 👇 カゴ表示エリアの「場所」だけ先に確保しておく
    basket_container = st.container()

    # =====================
    # ② ポテトを追加
    # =====================
    st.subheader("② ポテトを追加")

    # 上段：通常価格 & 期間中値下げ価格
    col_base,col_seminar, col_sale = st.columns(3)

    # 通常価格ボタン（300円）
    with col_base:
        st.caption("通常価格")
        if st.button(f"ポテト {BASE_PRICE}円 をカゴに追加", key="btn_base"):
            st.session_state.basket.append(BASE_PRICE)

    with col_seminar:
        st.caption("講演会価格")
        if st.button(f"ポテト {SEMINAR_PRICE}円 をカゴに追加", key="btn_semi"):
            st.session_state.basket.append(SEMINAR_PRICE)

    # 期間中値下げ価格ボタン
    with col_sale:
        st.caption("期間中の値下げ価格")
        sale_price = st.number_input(
            "値下げ後の価格（円）",
            min_value=0,
            max_value=10000,
            value=250,      # デフォルトの値下げ価格
            step=10,
            key="sale_price",
        )
        if st.button("ポテト（値下げ価格）をカゴに追加", key="btn_sale"):
            # sale_price は number_input の戻り値をそのまま使う
            st.session_state.basket.append(int(sale_price))

    # 下段：特別な割引（パスワード制）
    with st.expander("特別な割引で追加（要パスワード）"):
        pwd = st.text_input("パスワード", type="password", key="pwd_special")
        if pwd == DISCOUNT_PASSWORD:
            discount_price = st.number_input(
                "特別割引の1個あたり価格（円）",
                min_value=0,
                max_value=10000,
                value=200,
                step=10,
                key="special_discount_price",
            )
            if st.button("特別割引のポテトをカゴに追加", key="btn_special"):
                st.session_state.basket.append(int(discount_price))
        elif pwd != "":
            st.error("パスワードが違います。")

    # =====================
    # ③ 会計操作
    # =====================
        st.subheader("③ 会計操作")

    col1, col2, col3 = st.columns(3)

    # カゴをリセット
    with col1:
        if st.button("カゴをリセット", key="btn_reset_main"):
            st.session_state.basket = []
            st.info("カゴを空にしました。")

    # 会計を確定して保存
    with col2:
        if st.button("会計を確定して保存", key="btn_confirm_main"):
            if st.session_state.basket:
                save_transaction(st.session_state.basket)
                st.session_state.basket = []  # 会計後にカゴを空にする
                st.success("会計を保存しました。")
            else:
                st.warning("カゴが空です。")

    # 直前の会計を取り消す
    with col3:
        if st.button("直前の会計を取り消す", key="btn_cancel_main"):
            cancel_last_transaction()
            st.info("直前の会計を取り消しました。")

    # =====================
    # ① カゴの中身（最後に描画）
    # =====================
    with basket_container:
        st.subheader("① カゴの中身")

        if st.session_state.basket:
            counter = Counter(st.session_state.basket)
            lines = []
            for price, cnt in sorted(counter.items()):
                lines.append(f"{price}円 × {cnt}個")
            st.write(" / ".join(lines))
            st.write(f"合計個数：**{len(st.session_state.basket)} 個**")
            st.write(f"合計金額：**{sum(st.session_state.basket)} 円**")
        else:
            st.write("カゴは空です。")

   


if __name__ == "__main__":
    main()






