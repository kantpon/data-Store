import streamlit as st
import cloudinary
import cloudinary.uploader
import io
import datetime
import time
import gspread
from google.oauth2.service_account import Credentials
from PIL import Image, ImageOps


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="อัพโหลดใบเสร็จ",
    page_icon="🧾",
    layout="centered"
)


# =========================================================
# CSS
# =========================================================

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Sarabun', sans-serif;
    }

    .stApp {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        min-height: 100vh;
    }

    .block-container {
        background: white;
        border-radius: 20px;
        padding: 2.5rem 2rem !important;
        margin-top: 2rem;
        box-shadow: 0 20px 60px rgba(0,0,0,0.15);
        max-width: 680px;
    }

    h1 {
        color: #1a1a2e !important;
        font-weight: 700 !important;
        text-align: center;
    }

    .subtitle {
        text-align: center;
        color: #6b7280;
        margin-top: -0.5rem;
        margin-bottom: 1.5rem;
        font-size: 1rem;
    }

    .stButton > button {
        background: linear-gradient(135deg, #667eea, #764ba2) !important;
        color: white !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 0.75rem 2rem !important;
        font-size: 1.1rem !important;
        font-weight: 600 !important;
        width: 100%;
    }

    .success-box {
        background: #f0fdf4;
        border: 2px solid #86efac;
        border-radius: 14px;
        padding: 1.2rem 1.5rem;
        color: #166534;
        margin-top: 1rem;
    }

    .error-box {
        background: #fef2f2;
        border: 2px solid #fca5a5;
        border-radius: 14px;
        padding: 1.2rem 1.5rem;
        color: #991b1b;
        margin-top: 1rem;
        text-align: center;
    }

    .warning-box {
        background: #fffbeb;
        border: 2px solid #fcd34d;
        border-radius: 14px;
        padding: 1.2rem 1.5rem;
        color: #92400e;
        margin-top: 1rem;
    }

    .branch-box {
        background: #eef2ff;
        border: 2px solid #c7d2fe;
        border-radius: 14px;
        padding: 1rem 1.2rem;
        color: #3730a3;
        margin-top: 0.6rem;
    }

    .guide-box {
        background: #fffbeb;
        border: 2px solid #fcd34d;
        border-radius: 14px;
        padding: 1.2rem 1.4rem;
        color: #92400e;
        margin: 1rem 0;
        line-height: 1.7;
    }

    .divider {
        border: none;
        border-top: 1.5px solid #f3f4f6;
        margin: 1.5rem 0;
    }
</style>
""", unsafe_allow_html=True)


# =========================================================
# CLOUDINARY
# =========================================================

@st.cache_resource
def setup_cloudinary():

    cloudinary.config(
        cloud_name=st.secrets["cloudinary"]["cloud_name"],
        api_key=st.secrets["cloudinary"]["api_key"],
        api_secret=st.secrets["cloudinary"]["api_secret"],
        secure=True
    )


# =========================================================
# GOOGLE SHEET CLIENT
# =========================================================

@st.cache_resource
def get_gsheet_client():

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=scopes
    )

    return gspread.authorize(creds)


# =========================================================
# GOOGLE SHEET
# =========================================================

def setup_gsheet():

    client = get_gsheet_client()

    sheet = client.open_by_url(
        st.secrets["gsheet"]["sheet_url"]
    )

    worksheet = sheet.worksheet(
        st.secrets["gsheet"].get(
            "worksheet_name",
            "receipts"
        )
    )

    return worksheet


# =========================================================
# LOAD BRANCH LIST
# =========================================================

@st.cache_data(ttl=300)
def load_branch_list():

    try:

        client = get_gsheet_client()

        sheet_url = st.secrets["gsheet"].get(
            "branch_sheet_url",
            st.secrets["gsheet"]["sheet_url"]
        )

        sheet = client.open_by_url(sheet_url)

        ws_name = st.secrets["gsheet"].get(
            "branch_worksheet_name",
            "รายชื่อสาขา"
        )

        worksheet = sheet.worksheet(ws_name)

        records = worksheet.get_all_records()

        branches = []

        for r in records:

            code = str(
                r.get("รหัส", "")
            ).strip()

            name = str(
                r.get("รายชื่อสาขา", "")
            ).strip()

            zone = str(
                r.get("zone", "")
            ).strip()

            if name:

                branches.append({
                    "code": code,
                    "name": name,
                    "zone": zone
                })

        return branches, ""

    except Exception as e:

        return [], str(e)


# =========================================================
# WRITE GOOGLE SHEET
# =========================================================

def log_to_sheet(
    reporter,
    branch,
    zone,
    status,
    reason="",
    filename="",
    url=""
):

    try:

        worksheet = setup_gsheet()

        ts = datetime.datetime.now().strftime(
            "%d/%m/%Y %H:%M:%S"
        )

        worksheet.append_row(
            [
                ts,
                reporter,
                branch,
                zone,
                status,
                reason,
                filename,
                url
            ],
            value_input_option="USER_ENTERED"
        )

        return True, ""

    except Exception as e:

        return False, str(e)


# =========================================================
# GOOGLE SHEET RETRY
# =========================================================

def log_to_sheet_with_retry(
    reporter,
    branch,
    zone,
    status,
    reason="",
    filename="",
    url="",
    max_retries=3
):

    last_error = ""

    for attempt in range(
        1,
        max_retries + 1
    ):

        success, error = log_to_sheet(
            reporter=reporter,
            branch=branch,
            zone=zone,
            status=status,
            reason=reason,
            filename=filename,
            url=url
        )

        if success:

            return True, "", attempt

        last_error = error

        # ถ้ายังเหลือรอบให้ลองใหม่
        if attempt < max_retries:

            time.sleep(
                2 * attempt
            )

    return (
        False,
        last_error,
        max_retries
    )


# =========================================================
# IMAGE ORIENTATION
# =========================================================

def fix_orientation(
    file,
    thumb_side=500,
    extra_rotation=0
):

    img = Image.open(file)

    img = ImageOps.exif_transpose(img)

    if extra_rotation:

        img = img.rotate(
            -extra_rotation,
            expand=True
        )

    img.thumbnail(
        (
            thumb_side,
            thumb_side
        ),
        Image.LANCZOS
    )

    return img


# =========================================================
# COMPRESS IMAGE
# =========================================================

def compress_image(
    file,
    max_side=1280,
    quality=78,
    extra_rotation=0
):

    img = Image.open(file)

    img = ImageOps.exif_transpose(img)

    if extra_rotation:

        img = img.rotate(
            -extra_rotation,
            expand=True
        )

    if img.mode in (
        "RGBA",
        "P"
    ):

        img = img.convert("RGB")

    w, h = img.size

    if max(w, h) > max_side:

        scale = (
            max_side
            / max(w, h)
        )

        img = img.resize(
            (
                int(w * scale),
                int(h * scale)
            ),
            Image.LANCZOS
        )

    buf = io.BytesIO()

    img.save(
        buf,
        format="JPEG",
        quality=quality,
        optimize=True
    )

    return (
        buf.getvalue(),
        img.width,
        img.height
    )


# =========================================================
# CLOUDINARY UPLOAD
# =========================================================

def upload_to_cloudinary(
    image_bytes,
    filename
):

    result = cloudinary.uploader.upload(
        image_bytes,
        folder="branch",
        public_id=filename,
        resource_type="image",
        overwrite=False,
    )

    secure_url = result.get(
        "secure_url",
        ""
    )

    if not secure_url:

        raise Exception(
            "Cloudinary ไม่ได้ส่ง secure_url กลับมา"
        )

    return secure_url


# =========================================================
# INIT
# =========================================================

setup_cloudinary()


if "show_sent_dialog" not in st.session_state:

    st.session_state.show_sent_dialog = False


if "sent_count" not in st.session_state:

    st.session_state.sent_count = 0


# =========================================================
# SUCCESS DIALOG
# =========================================================

@st.dialog("✅ ส่งข้อมูลสำเร็จ")
def show_success_dialog():

    st.markdown(
        "### คุณส่งแล้ว"
    )

    st.write(
        f"อัพโหลดใบเสร็จ "
        f"{st.session_state.sent_count} รูป "
        f"และบันทึกข้อมูลเรียบร้อยแล้ว"
    )

    if st.button(
        "ตกลง",
        use_container_width=True
    ):

        st.session_state.show_sent_dialog = False

        st.rerun()


# =========================================================
# HEADER
# =========================================================

st.markdown(
    "# 🧾 อัพโหลดใบเสร็จ"
)

st.markdown(
    '<p class="subtitle">'
    'รูปจะถูกส่งเข้า Cloudinary โดยตรง · ปลอดภัย'
    '</p>',
    unsafe_allow_html=True
)

st.markdown(
    '<hr class="divider">',
    unsafe_allow_html=True
)


# =========================================================
# NUMBER OF RECEIPTS
# =========================================================

st.markdown(
    "#### 📋 จำนวนใบเสร็จในรูป"
)

mode = st.radio(
    "โหมด",
    ["2 ใบเสร็จ"],
    label_visibility="collapsed"
)

num_receipts = int(
    mode[0]
)


# =========================================================
# REPORTER
# =========================================================

st.markdown(
    '<hr class="divider">',
    unsafe_allow_html=True
)

st.markdown(
    "#### 🙋 ชื่อผู้กรอก"
)

reporter_name = st.text_input(
    "ชื่อผู้กรอก",
    placeholder="พิมพ์ชื่อผู้กรอกข้อมูล",
    label_visibility="collapsed",
)


# =========================================================
# BRANCH
# =========================================================

st.markdown(
    '<hr class="divider">',
    unsafe_allow_html=True
)

st.markdown(
    "#### 🏢 เลือกสาขา"
)


branches, branch_err = load_branch_list()


if branch_err:

    st.markdown(
        f'<div class="error-box">'
        f'❌ โหลดรายชื่อสาขาไม่สำเร็จ'
        f'</div>',
        unsafe_allow_html=True
    )

    sender_name = ""
    zone = ""


elif not branches:

    st.markdown(
        '<div class="error-box">'
        '⚠️ ยังไม่มีรายชื่อสาขาในชีท'
        '</div>',
        unsafe_allow_html=True
    )

    sender_name = ""
    zone = ""


else:

    st.caption(
        "📍 ขั้นที่ 1: เลือก Zone"
    )

    zone_list = sorted({
        b["zone"]
        for b in branches
        if b["zone"]
    })

    zone_options = [
        "ทั้งหมด (ทุก Zone)"
    ] + zone_list

    picked_zone = st.selectbox(
        "เลือก Zone",
        zone_options,
        label_visibility="collapsed",
    )


    if picked_zone == "ทั้งหมด (ทุก Zone)":

        filtered_branches = branches

    else:

        filtered_branches = [
            b
            for b in branches
            if b["zone"] == picked_zone
        ]


    st.caption(
        f"🔎 ขั้นที่ 2: เลือกสาขา "
        f"({len(filtered_branches)} สาขา)"
    )


    def display_label(b):

        if b["code"]:

            return (
                f'{b["code"]} | '
                f'{b["name"]}'
            )

        return b["name"]


    branch_options = [
        "-- กรุณาเลือกสาขา --"
    ] + [
        display_label(b)
        for b in filtered_branches
    ]


    picked = st.selectbox(
        "เลือกสาขา",
        branch_options,
        label_visibility="collapsed",
        key=f"branch_select_{picked_zone}",
    )


    if picked != "-- กรุณาเลือกสาขา --":

        matched = next(
            (
                b
                for b in filtered_branches
                if display_label(b) == picked
            ),
            None
        )

    else:

        matched = None


    if matched:

        sender_name = matched["name"]

        zone = matched["zone"]

        st.markdown(
            f'<div class="branch-box">'
            f'🏪 <strong>'
            f'{matched["name"]}'
            f'</strong>'
            f' &nbsp;·&nbsp; Zone '
            f'{matched["zone"] or "-"}'
            f'</div>',
            unsafe_allow_html=True
        )

    else:

        sender_name = ""
        zone = ""


# =========================================================
# COMPLETENESS
# =========================================================

st.markdown(
    '<hr class="divider">',
    unsafe_allow_html=True
)

st.markdown(
    "#### 📦 เครื่องที่ขาด"
)

st.caption(
    'เลือก "ครบ" หรือเลือกเครื่องที่ขาดได้หลายเครื่อง'
)


def _enforce_completeness_exclusive():

    prev = st.session_state.get(
        "_prev_completeness_sel",
        []
    )

    cur = st.session_state.completeness_sel

    added = [
        x
        for x in cur
        if x not in prev
    ]

    if added:

        new_item = added[0]

        if new_item == "ครบ":

            st.session_state.completeness_sel = [
                "ครบ"
            ]

        elif "ครบ" in cur:

            st.session_state.completeness_sel = [
                x
                for x in cur
                if x != "ครบ"
            ]

    st.session_state[
        "_prev_completeness_sel"
    ] = (
        st.session_state.completeness_sel
    )


completeness_sel = st.multiselect(
    "เครื่องที่ขาด",
    [
        "ครบ",
        "ขาดเครื่องที่ 1",
        "ขาดเครื่องที่ 2",
        "ขาดเครื่องที่ 3",
        "ขาดเครื่องที่ 4"
    ],
    label_visibility="collapsed",
    key="completeness_sel",
    on_change=_enforce_completeness_exclusive,
)


if "ครบ" in completeness_sel:

    completeness = "ครบ"

elif completeness_sel:

    completeness = "ไม่ครบ"

else:

    completeness = "-- กรุณาเลือก --"


incomplete_reason = ", ".join(
    [
        x
        for x in completeness_sel
        if x != "ครบ"
    ]
)


# =========================================================
# FILE UPLOAD
# =========================================================

st.markdown(
    '<hr class="divider">',
    unsafe_allow_html=True
)

st.markdown(
    "#### 📷 เลือกรูปภาพ"
)

st.caption(
    "💡 กด Ctrl ค้างไว้แล้วคลิกเลือกหลายรูปพร้อมกัน"
)


uploaded_files = st.file_uploader(
    "เลือกไฟล์",
    type=[
        "jpg",
        "jpeg",
        "png",
        "webp"
    ],
    accept_multiple_files=True,
    label_visibility="collapsed",
)


# =========================================================
# PREVIEW
# =========================================================

if uploaded_files:

    st.markdown(
        '<hr class="divider">',
        unsafe_allow_html=True
    )

    st.markdown(
        f"#### 🔍 ตรวจสอบรูปก่อนส่ง "
        f"({len(uploaded_files)} รูป)"
    )


    st.markdown(
        '<div class="guide-box">'
        '📸 <strong>โปรดถ่ายบิลให้ถูกต้อง</strong>'
        '<br><br>'
        '1. ภาพชัดให้อ่านค่าได้<br>'
        '2. มีระยะห่างจากกันระหว่างบิล<br>'
        '3. ภาพเป็นแนวตั้ง '
        '(หากเป็นแนวนอนสามารถปรับหมุนได้)'
        '</div>',
        unsafe_allow_html=True
    )


    if "rotations" not in st.session_state:

        st.session_state.rotations = {}


    for i, f in enumerate(
        uploaded_files
    ):

        rot_key = (
            f"{f.name}_"
            f"{f.size}_"
            f"{i}"
        )

        current_rot = (
            st.session_state.rotations.get(
                rot_key,
                0
            )
        )


        preview_img = fix_orientation(
            f,
            thumb_side=1000,
            extra_rotation=current_rot
        )


        st.image(
            preview_img,
            caption=f.name,
            use_container_width=True
        )


        c1, c2, c3 = st.columns(3)


        with c1:

            if st.button(
                "↺ หมุนซ้าย",
                key=f"rotate_left_{rot_key}",
                use_container_width=True
            ):

                st.session_state.rotations[
                    rot_key
                ] = (
                    current_rot - 90
                ) % 360

                st.rerun()


        with c2:

            if st.button(
                "↻ หมุนขวา",
                key=f"rotate_right_{rot_key}",
                use_container_width=True
            ):

                st.session_state.rotations[
                    rot_key
                ] = (
                    current_rot + 90
                ) % 360

                st.rerun()


        with c3:

            if st.button(
                "🔃 กลับหัว",
                key=f"rotate_flip_{rot_key}",
                use_container_width=True
            ):

                st.session_state.rotations[
                    rot_key
                ] = (
                    current_rot + 180
                ) % 360

                st.rerun()


        st.markdown(
            '<hr class="divider">',
            unsafe_allow_html=True
        )


    st.info(
        f"จะบันทึกในโฟลเดอร์ branch "
        f"ทั้ง {len(uploaded_files)} รูป"
    )


    st.markdown(
        '<hr class="divider">',
        unsafe_allow_html=True
    )


    # =====================================================
    # UPLOAD BUTTON
    # =====================================================

    if st.button(
        f"☁️ อัพโหลดทั้งหมด "
        f"({len(uploaded_files)} รูป)"
    ):


        # =================================================
        # VALIDATE
        # =================================================

        missing = []


        if not reporter_name.strip():

            missing.append(
                "ชื่อผู้กรอก"
            )


        if not sender_name.strip():

            missing.append(
                "สาขา"
            )


        if completeness == "-- กรุณาเลือก --":

            missing.append(
                "เครื่องที่ขาด"
            )


        if missing:

            items = "".join(
                [
                    f"<br>• {m}"
                    for m in missing
                ]
            )


            st.markdown(
                f'<div class="error-box">'
                f'⚠️ กรุณากรอกข้อมูลให้ครบก่อนอัพโหลด:'
                f'{items}'
                f'</div>',
                unsafe_allow_html=True
            )


        else:

            # =============================================
            # START UPLOAD
            # =============================================

            safe_sender = (
                sender_name
                .strip()
                .replace("/", "-")
                .replace("\\", "-")
            )


            results = []


            prog = st.progress(
                0,
                text="กำลังอัพโหลด..."
            )


            # =============================================
            # LOOP FILES
            # =============================================

            for idx, f in enumerate(
                uploaded_files
            ):


                result = {

                    "filename": f.name,

                    "cloud_ok": False,

                    "sheet_ok": False,

                    "cloud_url": "",

                    "error": "",

                    "retry": 0
                }


                try:

                    # -------------------------------------
                    # ROTATION
                    # -------------------------------------

                    rot_key = (
                        f"{f.name}_"
                        f"{f.size}_"
                        f"{idx}"
                    )


                    extra_rot = (
                        st.session_state
                        .get(
                            "rotations",
                            {}
                        )
                        .get(
                            rot_key,
                            0
                        )
                    )


                    # -------------------------------------
                    # COMPRESS
                    # -------------------------------------

                    (
                        img_bytes,
                        new_w,
                        new_h
                    ) = compress_image(
                        f,
                        max_side=1280,
                        quality=78,
                        extra_rotation=extra_rot
                    )


                    # -------------------------------------
                    # UNIQUE FILE NAME
                    # -------------------------------------

                    ts_file = (
                        datetime.datetime
                        .now()
                        .strftime(
                            "%Y%m%d_%H%M%S_%f"
                        )
                    )


                    fname = (
                        f"{safe_sender}_"
                        f"{ts_file}_"
                        f"{idx + 1}"
                    )


                    result["filename"] = (
                        f"{fname}.jpg"
                    )


                    # =====================================
                    # CLOUDINARY
                    # =====================================

                    secure_url = (
                        upload_to_cloudinary(
                            img_bytes,
                            fname
                        )
                    )


                    result["cloud_ok"] = True

                    result["cloud_url"] = (
                        secure_url
                    )


                    # =====================================
                    # GOOGLE SHEET
                    # =====================================

                    status_label = (
                        "ครบ"
                        if completeness == "ครบ"
                        else "ไม่ครบ"
                    )


                    (
                        log_ok,
                        log_err,
                        retry_count
                    ) = log_to_sheet_with_retry(

                        reporter=(
                            reporter_name
                            .strip()
                        ),

                        branch=(
                            sender_name
                            .strip()
                        ),

                        zone=(
                            zone
                            .strip()
                        ),

                        status=status_label,

                        reason=(
                            incomplete_reason
                            .strip()
                        ),

                        filename=(
                            f"{fname}.jpg"
                        ),

                        url=secure_url,

                        max_retries=3
                    )


                    # =====================================
                    # SHEET RESULT
                    # =====================================

                    result["sheet_ok"] = (
                        log_ok
                    )

                    result["retry"] = (
                        retry_count
                    )

                    result["error"] = (
                        log_err
                    )


                except Exception as e:

                    result["error"] = str(e)


                results.append(result)


                # =========================================
                # PROGRESS
                # =========================================

                prog.progress(
                    (idx + 1)
                    / len(uploaded_files),

                    text=(
                        f"กำลังอัพโหลด "
                        f"{idx + 1}/"
                        f"{len(uploaded_files)}..."
                    )
                )


            prog.empty()


            # =================================================
            # CHECK RESULTS
            # =================================================

            total = len(results)


            cloud_success = [
                r
                for r in results
                if r["cloud_ok"]
            ]


            sheet_success = [
                r
                for r in results
                if (
                    r["cloud_ok"]
                    and r["sheet_ok"]
                )
            ]


            failed = [
                r
                for r in results
                if not (
                    r["cloud_ok"]
                    and r["sheet_ok"]
                )
            ]


            # =================================================
            # ALL SUCCESS
            # =================================================

            if (
                len(cloud_success) == total
                and len(sheet_success) == total
            ):

                st.session_state.sent_count = (
                    total
                )

                st.session_state.show_sent_dialog = (
                    True
                )

                st.rerun()


            # =================================================
            # REJECT
            # =================================================

            else:

                st.markdown(
                    '<div class="error-box">'
                    '<strong>'
                    '❌ ขออภัย โปรดส่งใหม่อีกครั้ง'
                    '</strong>'
                    '</div>',
                    unsafe_allow_html=True
                )


                # =================================================
                # DEBUG สำหรับเจ้าของระบบ
                # =================================================
                # ไม่แสดงรายละเอียด Error ให้ผู้ใช้
                # แต่สามารถดูใน terminal/log ได้

                for r in failed:

                    print(
                        "UPLOAD FAILED:",
                        r
                    )


# =========================================================
# SUCCESS DIALOG
# =========================================================

if st.session_state.show_sent_dialog:

    show_success_dialog()


# =========================================================
# FOOTER
# =========================================================

st.markdown(
    '<hr class="divider">',
    unsafe_allow_html=True
)

st.markdown(
    '<p style="text-align:center;'
    'color:#d1d5db;'
    'font-size:0.8rem;">'
    'รูปทั้งหมดจะถูกส่งเข้าบัญชี '
    'Cloudinary ของเจ้าของระบบเท่านั้น'
    '</p>',
    unsafe_allow_html=True
)
